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
 * 启动前：若首选端口被占用且响应为本插件的 /api/version，则在 Unix 上 SIGTERM 释放端口（避免重启后落到 38272）。
 */
const path = require('path');
const os = require('os');
const fs = require('fs');
const net = require('net');
const http = require('http');
const { spawn, execFileSync } = require('child_process');

let dashboardProcess = null;

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

/** Dashboard 数据目录，与 Python 端一致：本工程数据统一放此，不写入 ~/.openclaw */
function getDashboardDataDir() {
  return process.env.OPENCLAW_AGENT_DASHBOARD_DATA || path.join(os.homedir(), '.openclaw-agent-dashboard');
}

function getDashboardDir() {
  const pluginDir = __dirname;
  return path.join(pluginDir, 'dashboard');
}

/** 兼容旧路径：若存在 ~/.openclaw/dashboard 或 ~/.openclaw-dashboard 下的 config.json 则迁移到新目录一次 */
function migrateLegacyConfigIfNeeded() {
  const openclawHome = getOpenClawHome();
  const newDir = getDashboardDataDir();
  const newPath = path.join(newDir, 'config.json');
  if (fs.existsSync(newPath)) return;
  const legacyPaths = [
    path.join(openclawHome, 'dashboard', 'config.json'),
    path.join(os.homedir(), '.openclaw-dashboard', 'config.json')
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
  const openclawHome = getOpenClawHome();
  let config = { port: 38271, autoStart: true }; // 使用罕见端口避免冲突

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
  const legacyUserConfigPath = path.join(openclawHome, 'dashboard', 'config.json');
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

/** 检测端口是否已被占用（有进程在监听） */
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

/** 与 Python 端 VersionInfo.name 一致（来自 openclaw.plugin.json / package.json） */
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
 * @returns {Promise<boolean>}
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
 * @returns {number[]}
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

function sleepMs(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Gateway 重启后旧 Dashboard 子进程常仍占用首选端口，导致新实例落到 38272。
 * 若占用者为本插件的 Dashboard，则 SIGTERM 释放端口后再启动（仅 Unix；Windows 行为不变）。
 */
async function reclaimStaleOurDashboardPort(port) {
  if (await isPortAvailable(port)) return;
  const ours = await probeOurDashboardListening(port);
  if (!ours) {
    return;
  }
  const pids = getListenPidsOnPort(port);
  if (pids.length === 0) {
    console.log(
      `[OpenClaw-Dashboard] 端口 ${port} 上检测到本插件 Dashboard，但无法解析占用进程（可安装 lsof），仍尝试后续端口`
    );
    return;
  }
  console.log(
    `[OpenClaw-Dashboard] 端口 ${port} 被上一实例 Dashboard 占用 (PID: ${pids.join(', ')})，正在结束以便固定端口`
  );
  for (const pid of pids) {
    try {
      process.kill(pid, 'SIGTERM');
    } catch (e) {
      console.warn(`[OpenClaw-Dashboard] 无法向 PID ${pid} 发送 SIGTERM:`, e.message || e);
    }
  }
  await sleepMs(900);
}

function startDashboard(config = {}) {
  // 仅在 Gateway 进程内自动启动（OPENCLAW_GATEWAY_PORT 由 Gateway 设置）
  // CLI 命令（status、health 等）加载插件时不会设置此变量，故不启动
  if (!process.env.OPENCLAW_GATEWAY_PORT?.trim()) {
    return;
  }

  if (dashboardProcess) {
    console.log('[OpenClaw-Dashboard] 服务已在运行');
    return;
  }

  const dashboardDir = getDashboardDir();
  const openclawHome = getOpenClawHome();

  if (!fs.existsSync(dashboardDir)) {
    console.warn('[OpenClaw-Dashboard] dashboard 目录不存在，请先执行 npm run deploy 安装插件');
    return;
  }

  const basePort = config.port ?? 38271;
  const isExplicitPort = basePort !== 38271; // 用户显式配置了端口（非默认 38271）
  const autoStart = config.autoStart !== false; // 默认 true，可配置为 false 禁用自动启动

  if (!autoStart) {
    return;
  }

  const portPromise = (async () => {
    await reclaimStaleOurDashboardPort(basePort);
    return isExplicitPort ? basePort : await findAvailablePort(basePort);
  })();

  portPromise.then(async (port) => {
    if (dashboardProcess) return;

    // 若端口已被占用，认为 Dashboard 已在其他进程运行，跳过启动，避免重复实例
    if (await isPortInUse(port)) {
      console.log(`[OpenClaw-Dashboard] 端口 ${port} 已被占用，Dashboard 可能已在运行，跳过启动`);
      return;
    }

    const env = {
      ...process.env,
      OPENCLAW_HOME: openclawHome,
      DASHBOARD_PORT: String(port),
    };

    // 优先使用插件 venv 的 Python（安装时 venv 优先，避免 PEP 668）
    // 若 venv 存在但不完整（如缺 python3-venv 导致 ensurepip 失败、无 uvicorn），回退到 python3
    const venvPythonUnix = path.join(dashboardDir, '.venv', 'bin', 'python');
    const venvPythonWin = path.join(dashboardDir, '.venv', 'Scripts', 'python.exe');
    let pythonCmd = process.env.PYTHON_CMD;
    if (!pythonCmd) {
      const venvPython = fs.existsSync(venvPythonUnix) ? venvPythonUnix : (fs.existsSync(venvPythonWin) ? venvPythonWin : null);
      if (venvPython) {
        try {
          execFileSync(venvPython, ['-c', 'import uvicorn'], { stdio: 'ignore', timeout: 3000 });
          pythonCmd = venvPython;
        } catch (_) {
          pythonCmd = resolveSystemPython(); // venv 不完整，回退到系统 Python
        }
      } else {
        pythonCmd = resolveSystemPython();
      }
    }
    const args = ['-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', String(port)];

    if (!isExplicitPort && port !== basePort) {
      console.log(`[OpenClaw-Dashboard] 端口 ${basePort} 被占用，使用 ${port}`);
    }
    console.log(`[OpenClaw-Dashboard] 插件服务已启动`);
    console.log(`[OpenClaw-Dashboard] 访问地址: http://localhost:${port}`);

    dashboardProcess = spawn(pythonCmd, args, {
      env,
      cwd: dashboardDir,
      stdio: ['ignore', 'ignore', 'ignore'],
    });

    dashboardProcess.on('error', (err) => {
      console.error('[OpenClaw-Dashboard] 启动失败:', err.message);
      dashboardProcess = null;
    });
    dashboardProcess.on('exit', (code, signal) => {
      dashboardProcess = null;
      if (code !== 0 && code !== null) {
        console.log(`[OpenClaw-Dashboard] 进程退出 code=${code} signal=${signal}`);
      }
    });
  });
}

function stopDashboard() {
  if (dashboardProcess) {
    dashboardProcess.kill('SIGTERM');
    dashboardProcess = null;
    console.log('[OpenClaw-Dashboard] 服务已停止');
  }
}

/**
 * OpenClaw 插件入口
 * @param {object} api - OpenClaw 插件 API，pluginConfig 来自 openclaw.json 的 config 字段
 */
function DashboardPlugin(api) {
  console.log('[OpenClaw-Dashboard] 插件已加载');

  const pluginConfig = (api && api.pluginConfig) || {};
  const config = loadConfig(pluginConfig);
  startDashboard(config);

  return {
    stop() {
      stopDashboard();
    },
  };
}

module.exports = DashboardPlugin;
