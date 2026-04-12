/**
 * OpenClaw Agent Dashboard - 插件入口
 * 仅在 Gateway 进程内自动启动 FastAPI 后端（检测 OPENCLAW_GATEWAY_PORT）
 *
 * 启动条件：OPENCLAW_GATEWAY_PORT 已设置（即 Gateway 进程）且 autoStart !== false
 *
 * 端口配置优先级（高到低）：
 * 1. 环境变量 DASHBOARD_PORT
 * 2. ~/.openclaw-agent-dashboard/config.json（或 OPENCLAW_AGENT_DASHBOARD_DATA/config.json）
 * 3. openclaw.json 中 plugins.entries.openclaw-agent-dashboard.config.port
 * 4. 默认 38271
 *
 * 启动前：若首选端口被占用且 /api/version 确认为本插件 Dashboard，则在 Unix 上结束旧进程
 * （SIGTERM → 必要时 SIGKILL；无 lsof 时 Linux 可试 fuser），尽量仍在 38271 起新实例。
 *
 * 热重载恢复（评审文档 FR-1~FR-9）：
 * - activeStartId 所有权互斥 + 世代号防止并发双起与 stop 后仍 spawn（FR-7/FR-9）
 * - stop 带超时等待子进程退出（FR-1）
 * - 启动重试 + 探测 + 回收循环（FR-2/FR-3/FR-5）
 * - spawn 后就绪探测（FR-9）
 * - PID 文件辅助孤儿发现（FR-8）
 */
const path = require('path');
const os = require('os');
const fs = require('fs');
const net = require('net');
const http = require('http');
const { spawn, execFileSync } = require('child_process');

// ── 模块级状态 ──────────────────────────────────────────────────────────────
let dashboardProcess = null;

/** 世代号：每次进入异步启动链时递增，stop 时 bump，用于作废旧的异步链 */
let generation = 0;
/** 中止标志：stop 时置 true，start 入口时重置为 false */
let aborted = false;

/**
 * 互斥锁：保证全局最多一条「选口→spawn→就绪确认」的启动链在途。
 * 采用所有权语义：值为本次启动的 generation（非零），0 表示空闲。
 * 仅持有该 generation 的 IIFE 可在 finally 中释放（比较 activeStartId === myId），
 * stop() 和其他链不得修改此值——避免旧链误清新链的锁。
 *
 * 残余窗口：stop() 后、旧链 finally 执行前 activeStartId !== 0，
 * 新的 startDashboard() 会「启动链已在进行中, 跳过」。若宿主不会再次调用
 * startDashboard，理论上存在极短窗口内「看起来没自动拉起」；但旧链会在
 * 下一个 await 边界因 generation/aborted 快速退出并释放锁。
 * 若需更强保证（宿主仅调一次 start），可在锁释放后自动重试（后续增强）。
 */
let activeStartId = 0;

// ── 常量 / 可通过环境变量覆盖 ────────────────────────────────────────────────
const DEFAULT_PORT = 38271;
const MAX_START_RETRIES = parseInt(process.env.DASHBOARD_START_MAX_RETRIES, 10) || 5;
const TOTAL_RETRY_TIMEOUT_MS = parseInt(process.env.DASHBOARD_START_TOTAL_TIMEOUT_MS, 10) || 15000;
const BACKOFF_BASE_MS = 500;
const STOP_SIGTERM_TIMEOUT_MS = 5000;
const STOP_SIGKILL_TIMEOUT_MS = 3000;
const READY_CHECK_TIMEOUT_MS = 8000;
const READY_CHECK_INTERVAL_MS = 500;
const PID_FILENAME = 'dashboard-runtime.json';

const LOG_PREFIX = '[OpenClaw-Dashboard]';

// ── 工具函数 ────────────────────────────────────────────────────────────────

function log(...args) { console.log(LOG_PREFIX, ...args); }
function logWarn(...args) { console.warn(LOG_PREFIX, ...args); }
function logError(...args) { console.error(LOG_PREFIX, ...args); }

function sleepMs(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** 解析系统 Python（Linux/macOS 多为 python3，Windows 多为 python） */
function resolveSystemPython() {
  if (process.env.PYTHON_CMD) {
    return process.env.PYTHON_CMD;
  }
  for (const cmd of ['python3', 'python']) {
    try {
      execFileSync(cmd, ['-c', 'import sys'], { stdio: 'ignore', timeout: 3000 });
      return cmd;
    } catch (_) {
      /* try next */
    }
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function getOpenClawHome() {
  return process.env.OPENCLAW_HOME || path.join(os.homedir(), '.openclaw');
}

/** Dashboard 数据目录 */
function getDashboardDataDir() {
  return process.env.OPENCLAW_AGENT_DASHBOARD_DATA || path.join(os.homedir(), '.openclaw-agent-dashboard');
}

function getDashboardDir() {
  return path.join(__dirname, 'dashboard');
}

/** 兼容旧路径：若存在旧 config.json 则迁移到新目录 */
function migrateLegacyConfigIfNeeded() {
  const openclawHome = getOpenClawHome();
  const newDir = getDashboardDataDir();
  const newPath = path.join(newDir, 'config.json');
  if (fs.existsSync(newPath)) return;
  const legacyPaths = [
    path.join(openclawHome, 'dashboard', 'config.json'),
    path.join(os.homedir(), '.openclaw-dashboard', 'config.json'),
  ];
  for (const legacyPath of legacyPaths) {
    if (!fs.existsSync(legacyPath)) continue;
    try {
      if (!fs.existsSync(newDir)) fs.mkdirSync(newDir, { recursive: true });
      fs.copyFileSync(legacyPath, newPath);
    } catch (_) {}
    return;
  }
}

/**
 * 加载配置，优先级：env > 用户 config.json（新路径 > 旧路径）> api.pluginConfig > 默认
 */
function loadConfig(apiPluginConfig = {}) {
  let config = { port: DEFAULT_PORT, autoStart: true };

  if (apiPluginConfig && typeof apiPluginConfig.port === 'number') {
    config.port = apiPluginConfig.port;
  }
  if (apiPluginConfig && typeof apiPluginConfig.autoStart === 'boolean') {
    config.autoStart = apiPluginConfig.autoStart;
  }

  const projectConfigPath = path.join(getDashboardDir(), 'config.json');
  if (fs.existsSync(projectConfigPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(projectConfigPath, 'utf8'));
      if (typeof data.port === 'number') config.port = data.port;
    } catch (_) {}
  }

  migrateLegacyConfigIfNeeded();
  const userConfigPath = path.join(getDashboardDataDir(), 'config.json');
  const legacyUserConfigPath = path.join(getOpenClawHome(), 'dashboard', 'config.json');
  const prevUserConfigPath = path.join(os.homedir(), '.openclaw-dashboard', 'config.json');
  const pathToRead = fs.existsSync(userConfigPath) ? userConfigPath
    : (fs.existsSync(prevUserConfigPath) ? prevUserConfigPath : legacyUserConfigPath);
  if (pathToRead && fs.existsSync(pathToRead)) {
    try {
      const data = JSON.parse(fs.readFileSync(pathToRead, 'utf8'));
      if (typeof data.port === 'number') config.port = data.port;
    } catch (_) {}
  }

  const envPort = process.env.DASHBOARD_PORT;
  if (envPort) {
    const p = parseInt(envPort, 10);
    if (!isNaN(p) && p > 0) config.port = p;
  }

  return config;
}

// ── 端口检测 ────────────────────────────────────────────────────────────────

/** 检测端口是否可用 */
function isPortAvailable(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(false));
    server.once('listening', () => {
      server.close(() => resolve(true));
    });
    server.listen(port, '0.0.0.0');
  });
}

/** 检测端口是否已被占用 */
function isPortInUse(port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once('error', () => resolve(true));
    server.once('listening', () => {
      server.close(() => resolve(false));
    });
    server.listen(port, '127.0.0.1');
  });
}

/** 找到可用端口，从 basePort 开始尝试 */
async function findAvailablePort(basePort, maxAttempts = 10) {
  for (let i = 0; i < maxAttempts; i++) {
    const port = basePort + i;
    if (await isPortAvailable(port)) return port;
  }
  return basePort;
}

// ── 探测与回收 ──────────────────────────────────────────────────────────────

/** 与 Python 端 VersionInfo.name 一致 */
function getExpectedDashboardApiName() {
  try {
    const manifestPath = path.join(__dirname, 'openclaw.plugin.json');
    if (fs.existsSync(manifestPath)) {
      const j = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
      if (j && typeof j.name === 'string' && j.name.trim()) return j.name.trim();
      if (j && typeof j.id === 'string' && j.id.trim()) return j.id.trim();
    }
  } catch (_) {}
  return 'openclaw-agent-dashboard';
}

/**
 * 探测本机 port 上是否为当前插件的 Dashboard（FastAPI /api/version）
 */
function probeOurDashboardListening(port) {
  const expected = getExpectedDashboardApiName();
  return new Promise((resolve) => {
    const req = http.get(
      `http://127.0.0.1:${port}/api/version`,
      { timeout: 2500 },
      (res) => {
        let raw = '';
        res.on('data', (c) => { raw += c; });
        res.on('end', () => {
          try {
            const data = JSON.parse(raw);
            resolve(typeof data.name === 'string' && data.name.trim() === expected);
          } catch (_) {
            resolve(false);
          }
        });
      }
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
  });
}

/**
 * 获取在 port 上 LISTEN 的进程 PID（Unix）。Windows 暂不支持，返回空数组。
 */
function getListenPidsOnPort(port) {
  if (process.platform === 'win32') {
    return [];
  }
  const tryLsof = (args) => {
    try {
      const out = execFileSync('lsof', args, { encoding: 'utf8', timeout: 5000 });
      return out
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map((s) => parseInt(s, 10))
        .filter((n) => !Number.isNaN(n) && n > 0);
    } catch (_) {
      return [];
    }
  };
  let pids = tryLsof(['-iTCP:' + port, '-sTCP:LISTEN', '-t']);
  if (pids.length === 0) {
    pids = tryLsof(['-ti', ':' + port]);
  }
  return [...new Set(pids)];
}

/**
 * Linux：无 lsof PID 时尝试 fuser 释放监听该 TCP 端口的进程。
 * 仅在已确认 /api/version 为本插件后调用。
 */
function tryFuserKillTcpPort(port) {
  if (process.platform !== 'linux') return;
  try {
    execFileSync('fuser', ['-k', `${port}/tcp`], { stdio: 'ignore', timeout: 8000 });
  } catch (_) {
    /* fuser 不可用或端口已释放 */
  }
}

/**
 * 单轮回收：尝试结束占用 port 的本插件 Dashboard 进程。
 *
 * 前提：调用方必须已通过 probeOurDashboardListening 确认端口上为本插件 Dashboard，
 *       本函数不做二次 probe（与 tryFuserKillTcpPort 约定一致）。
 *
 * 返回 true 表示本轮执行了 kill / fuser 操作。
 */
function reclaimOneRound(port) {
  const pids = getListenPidsOnPort(port);
  if (pids.length > 0) {
    for (const pid of pids) {
      try {
        process.kill(pid, 'SIGTERM');
      } catch (_) {}
    }
    log(`回收端口 ${port}: 已向 PID ${pids.join(', ')} 发送 SIGTERM`);
    return true;
  }

  /* 有 lsof 但拿不到 PID（极少见），或 Windows 无 PID 手段 */
  if (process.platform === 'linux') {
    log(`回收端口 ${port}: 无 lsof PID, 尝试 fuser`);
    tryFuserKillTcpPort(port);
    return true;
  }

  if (process.platform === 'win32') {
    logWarn(`回收端口 ${port}: Windows 无 PID 手段, 跳过 reclaim (将走备用端口或告警)`);
  }
  return false;
}

/**
 * Gateway 重启/升级后旧 Dashboard 常仍占用首选端口。
 * 若占用者为本插件 Dashboard（/api/version 校验），则多轮结束旧进程后再启动。
 */
async function reclaimStaleOurDashboardPort(port) {
  const maxPasses = 4;
  for (let pass = 0; pass < maxPasses; pass++) {
    if (await isPortAvailable(port)) {
      return;
    }

    const ours = await probeOurDashboardListening(port);
    if (!ours) {
      return;
    }

    const pids = getListenPidsOnPort(port);
    if (pids.length > 0) {
      const sig = pass === 0 ? 'SIGTERM' : 'SIGKILL';
      log(
        `端口 ${port} 被上一实例 Dashboard 占用 (PID: ${pids.join(', ')}), ${sig} 以便在 ${port} 启动新实例`
      );
      for (const pid of pids) {
        try {
          process.kill(pid, sig);
        } catch (e) {
          logWarn(`无法向 PID ${pid} 发送 ${sig}:`, e.message || e);
        }
      }
      await sleepMs(pass === 0 ? 1200 : 800);
      continue;
    }

    if (process.platform === 'linux' && pass >= maxPasses - 2) {
      log(`端口 ${port} 上为本插件 Dashboard, 尝试 fuser 释放（建议安装 lsof）`);
      tryFuserKillTcpPort(port);
      await sleepMs(700);
      continue;
    }

    if (pass === 0) {
      log(`端口 ${port} 上检测到本插件 Dashboard, 但无法解析占用进程（可安装 lsof）, 稍后重试或换端口`);
    }
    await sleepMs(500);
  }
}

// ── PID 文件（FR-8）────────────────────────────────────────────────────────

function getPidFilePath() {
  return path.join(getDashboardDataDir(), PID_FILENAME);
}

function writePidFile(childPid, port) {
  try {
    const dir = getDashboardDataDir();
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    const data = {
      gatewayPid: process.pid,
      childPid,
      port,
      startedAt: new Date().toISOString(),
    };
    fs.writeFileSync(getPidFilePath(), JSON.stringify(data, null, 2), 'utf8');
  } catch (_) {}
}

function removePidFile() {
  try {
    const p = getPidFilePath();
    if (fs.existsSync(p)) fs.unlinkSync(p);
  } catch (_) {}
}

/**
 * 读取旧 PID 文件，若端口被占且为本插件则执行 reclaim。
 * PID 文件仅作辅助线索，实际 kill 前仍须 /api/version 二次确认。
 *
 * 返回 true 表示回收成功（端口已释放或本来就是空的）；
 * 返回 false 表示端口仍被占用（可能是本插件但回收失败，也可能是其他服务）。
 */
async function reclaimFromPidFile(basePort) {
  try {
    const p = getPidFilePath();
    if (!fs.existsSync(p)) return true;
    const data = JSON.parse(fs.readFileSync(p, 'utf8'));
    if (!data || typeof data.port !== 'number') {
      removePidFile();
      return true;
    }

    const port = data.port;

    if (!(await isPortInUse(port))) {
      // 端口已空闲，旧实例已退出，清理文件
      removePidFile();
      return true;
    }

    const ours = await probeOurDashboardListening(port);
    if (!ours) {
      // 非本插件占用，不动，保留 PID 文件供后续参考
      log(`PID 文件记录端口 ${port}, 但 /api/version 表明非本插件, 保留文件`);
      return false;
    }

    log(`PID 文件发现旧实例占用端口 ${port} (旧 childPid: ${data.childPid}), 执行回收`);
    await reclaimStaleOurDashboardPort(port);

    // 仅在确认端口已释放时才删文件，否则保留供下次启动再试
    if (await isPortAvailable(port)) {
      removePidFile();
      return true;
    }

    logWarn(`PID 文件旧实例回收后端口 ${port} 仍被占用, 保留 PID 文件`);
    return false;
  } catch (_) {
    return true;
  }
}

// ── 就绪探测（FR-9）────────────────────────────────────────────────────────

/**
 * spawn 后轮询 /api/version 直至就绪或超时。
 * 返回 true 表示 Dashboard 已就绪；false 表示超时或世代失配。
 */
async function waitForReady(port, startGen, timeoutMs = READY_CHECK_TIMEOUT_MS) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (generation !== startGen || aborted) {
      return false;
    }
    const ready = await probeOurDashboardListening(port);
    if (ready) {
      return true;
    }
    await sleepMs(READY_CHECK_INTERVAL_MS);
  }
  return false;
}

// ── 核心：stop / start ─────────────────────────────────────────────────────

/**
 * FR-1: 停止 Dashboard 子进程，带后台超时等待。
 * stop() 本身保持同步（不阻塞调用方），子进程退出等待异步进行。
 */
function stopDashboard() {
  // FR-7: bump generation + set aborted
  // 注意：不修改 activeStartId——旧链会因 generation !== startGen 自行退出，
  // 其 finally 中只有 activeStartId === myId 时才会清锁，不会误清新链。
  generation++;
  aborted = true;

  const child = dashboardProcess;
  dashboardProcess = null;

  if (!child || child.killed) {
    removePidFile();
    return;
  }

  // 发送 SIGTERM
  try {
    child.kill('SIGTERM');
  } catch (_) {}
  log('服务停止中 (SIGTERM)');

  // 后台异步等待退出（不阻塞 stop 调用方）
  let settled = false;
  let sigtermTimer = null;
  let sigkillTimer = null;

  const settle = (exited) => {
    if (settled) return;
    settled = true;
    if (sigtermTimer) clearTimeout(sigtermTimer);
    if (sigkillTimer) clearTimeout(sigkillTimer);
    removePidFile();
    if (exited) {
      log('服务已停止, 子进程已退出');
    } else {
      logWarn('服务停止超时, 子进程可能仍在运行');
    }
  };

  child.once('exit', () => {
    settle(true);
  });

  // T1 超时后 SIGKILL
  sigtermTimer = setTimeout(() => {
    if (settled) return;
    try {
      if (!child.killed) {
        child.kill('SIGKILL');
        logWarn('子进程未在 SIGTERM 超时内退出, 已发送 SIGKILL');
      }
    } catch (_) {}

    // T2: SIGKILL 后最终超时
    sigkillTimer = setTimeout(() => {
      settle(false);
    }, STOP_SIGKILL_TIMEOUT_MS);
  }, STOP_SIGTERM_TIMEOUT_MS);
}

/**
 * FR-9 辅助: spawn + 就绪探测。
 * 调用前必须已持有 activeStartId 锁（activeStartId === startGen）。
 * 返回 true 表示成功启动并就绪。
 */
async function spawnAndReadyCheck(port, startGen, env, dashboardDir, pythonCmd, args) {
  if (generation !== startGen || aborted) return false;
  // activeStartId 锁已由调用方保证，直接 spawn
  const child = spawn(pythonCmd, args, {
    env,
    cwd: dashboardDir,
    stdio: ['ignore', 'ignore', 'ignore'],
  });

  child.on('error', (err) => {
    logError('启动失败:', err.message);
    if (dashboardProcess === child) dashboardProcess = null;
  });

  child.on('exit', (code, signal) => {
    if (dashboardProcess === child) dashboardProcess = null;
    if (code !== 0 && code !== null) {
      log(`进程退出 code=${code} signal=${signal}`);
    }
  });

  // 立即占位 dashboardProcess（spawn 原子赋值，JS 单线程无竞态）
  dashboardProcess = child;

  // FR-9: 就绪探测
  const ready = await waitForReady(port, startGen);
  if (!ready) {
    // 就绪超时或世代失配 → kill 该子进程
    try { child.kill('SIGKILL'); } catch (_) {}
    if (dashboardProcess === child) dashboardProcess = null;
    return false;
  }

  // 就绪成功 → 写 PID 文件（FR-8）
  writePidFile(child.pid, port);
  return true;
}

/**
 * FR-2/FR-3/FR-5: 带退避重试的启动循环。
 * 调用前必须已持有 activeStartId 锁（activeStartId === startGen）。
 * 锁由外层 IIFE 的 finally 释放，本函数不操作 activeStartId。
 */
async function startWithRetry(port, isExplicitPort, startGen) {
  const startTime = Date.now();
  let currentPort = port;

  for (let attempt = 1; attempt <= MAX_START_RETRIES; attempt++) {
    // 世代校验
    if (generation !== startGen || aborted) {
      log(`启动链已作废 (世代 ${startGen} → ${generation})`);
      return;
    }

    const elapsed = Date.now() - startTime;
    if (elapsed >= TOTAL_RETRY_TIMEOUT_MS) {
      logError(`启动失败: 重试总超时 (${TOTAL_RETRY_TIMEOUT_MS}ms), 端口 ${currentPort}`);
      return;
    }

    // ── 端口可用 → spawn ──
    const portAvailable = await isPortAvailable(currentPort);
    if (portAvailable) {
      const env = {
        ...process.env,
        OPENCLAW_HOME: getOpenClawHome(),
        DASHBOARD_PORT: String(currentPort),
      };

      const pythonCmd = resolvePythonCmd();
      const args = ['-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', String(currentPort)];

      if (!isExplicitPort && currentPort !== port) {
        log(`端口 ${port} 被占用, 尝试 ${currentPort} (${attempt}/${MAX_START_RETRIES})`);
      } else {
        log(`尝试启动 (${attempt}/${MAX_START_RETRIES}), 端口 ${currentPort}`);
      }

      const ok = await spawnAndReadyCheck(currentPort, startGen, env, getDashboardDir(), pythonCmd, args);

      if (ok) {
        log(`插件服务已启动`);
        log(`访问地址: http://localhost:${currentPort}`);
        return;
      }

      // spawn 或就绪失败 → 退避重试
      const backoff = BACKOFF_BASE_MS * attempt;
      logWarn(`端口 ${currentPort} spawn/就绪失败, ${backoff}ms 后重试 (${attempt}/${MAX_START_RETRIES})`);
      await sleepMs(backoff);
      continue;
    }

    // ── 端口被占用 → 探测 + 决策 ──
    const ours = await probeOurDashboardListening(currentPort);

    if (ours) {
      // FR-3: 本插件旧实例 → 回收
      log(`[ours] 端口 ${currentPort} 被本插件旧实例占用, 执行回收 (${attempt}/${MAX_START_RETRIES})`);
      reclaimOneRound(currentPort);
      const backoff = BACKOFF_BASE_MS * attempt;
      await sleepMs(backoff);
      continue;
    }

    // 非本插件占用
    if (isExplicitPort) {
      // FR-5: 显式固定端口 → 不误杀，重试 + 告警
      logWarn(
        `[other] 端口 ${currentPort} 被非本插件服务占用, 不可回收, 重试中 (${attempt}/${MAX_START_RETRIES})`
      );
      const backoff = BACKOFF_BASE_MS * attempt;
      await sleepMs(backoff);
      continue;
    }

    // FR-4: 非显式端口 → 尝试备用端口
    const altPort = await findAvailablePort(currentPort + 1);
    if (altPort !== currentPort) {
      log(`[other] 端口 ${currentPort} 被占用, 切换到备用端口 ${altPort}`);
      currentPort = altPort;
      continue;
    }

    // 无可用备用端口
    logWarn(
      `[unknown] 端口 ${currentPort} 被占用且无备用端口, 重试中 (${attempt}/${MAX_START_RETRIES})`
    );
    const backoff = BACKOFF_BASE_MS * attempt;
    await sleepMs(backoff);
  }

  logError(
    `启动失败: 重试耗尽 (${MAX_START_RETRIES} 次), 最后尝试端口 ${currentPort}`
  );
}

/**
 * 解析 Python 命令（venv 优先 → 系统 Python）
 */
function resolvePythonCmd() {
  const dashboardDir = getDashboardDir();
  const venvPythonUnix = path.join(dashboardDir, '.venv', 'bin', 'python');
  const venvPythonWin = path.join(dashboardDir, '.venv', 'Scripts', 'python.exe');

  if (process.env.PYTHON_CMD) return process.env.PYTHON_CMD;

  const venvPython = fs.existsSync(venvPythonUnix) ? venvPythonUnix
    : (fs.existsSync(venvPythonWin) ? venvPythonWin : null);

  if (venvPython) {
    try {
      execFileSync(venvPython, ['-c', 'import uvicorn'], { stdio: 'ignore', timeout: 3000 });
      return venvPython;
    } catch (_) {
      return resolveSystemPython();
    }
  }
  return resolveSystemPython();
}

function startDashboard(config = {}) {
  // 仅在 Gateway 进程内自动启动
  if (!process.env.OPENCLAW_GATEWAY_PORT?.trim()) {
    return;
  }

  if (dashboardProcess) {
    log('服务已在运行');
    return;
  }

  if (activeStartId !== 0) {
    log('启动链已在进行中, 跳过');
    return;
  }

  const dashboardDir = getDashboardDir();
  if (!fs.existsSync(dashboardDir)) {
    logWarn('dashboard 目录不存在, 请先执行 npm run deploy 安装插件');
    return;
  }

  const basePort = config.port ?? DEFAULT_PORT;
  const isExplicitPort = basePort !== DEFAULT_PORT;
  const autoStart = config.autoStart !== false;

  if (!autoStart) {
    return;
  }

  // 仅在即将启动异步链时递增世代 + 重置中止标志
  generation++;
  aborted = false;
  const startGen = generation;

  // 占位互斥锁：activeStartId 设为本次 generation
  activeStartId = startGen;

  // 异步启动链
  (async () => {
    try {
      // FR-8: 先从 PID 文件检查旧实例
      await reclaimFromPidFile(basePort);

      // 世代校验（PID 文件回收可能耗时）
      if (generation !== startGen || aborted) {
        log(`启动链 ${startGen} 在 PID 文件回收后被作废`);
        return;
      }

      // 回收已知旧实例
      await reclaimStaleOurDashboardPort(basePort);

      // 世代校验
      if (generation !== startGen || aborted) {
        log(`启动链 ${startGen} 在 stale port 回收后被作废`);
        return;
      }

      // 选择端口
      const port = isExplicitPort ? basePort : await findAvailablePort(basePort);

      // 世代校验
      if (generation !== startGen || aborted) {
        log(`启动链 ${startGen} 在端口选择后被作废`);
        return;
      }

      // FR-2/3/5: 带重试的启动
      await startWithRetry(port, isExplicitPort, startGen);
    } catch (err) {
      logError(`启动链 ${startGen} 异常:`, err.message || err);
    } finally {
      // 所有权释放：仅当 activeStartId 仍归我所有时才清锁
      if (activeStartId === startGen) {
        activeStartId = 0;
      }
    }
  })();
}

/**
 * OpenClaw 插件入口
 * @param {object} api - OpenClaw 插件 API，pluginConfig 来自 openclaw.json 的 config 字段
 */
function DashboardPlugin(api) {
  const pluginConfig = (api && api.pluginConfig) || {};
  const config = loadConfig(pluginConfig);

  if (process.env.OPENCLAW_GATEWAY_PORT?.trim()) {
    log('插件已加载, 准备启动 Dashboard');
  }

  startDashboard(config);

  return {
    stop() {
      stopDashboard();
    },
  };
}

module.exports = DashboardPlugin;
