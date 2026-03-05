/**
 * OpenClaw Agent Dashboard - 插件入口
 * 仅在 Gateway 进程内自动启动 FastAPI 后端（检测 OPENCLAW_GATEWAY_PORT）
 *
 * 启动条件：OPENCLAW_GATEWAY_PORT 已设置（即 Gateway 进程）且 autoStart !== false
 *
 * 端口配置优先级（高到低）：
 * 1. 环境变量 DASHBOARD_PORT
 * 2. ~/.openclaw/dashboard/config.json
 * 3. openclaw.json 中 plugins.entries.openclaw-agent-dashboard.config.port
 * 4. 默认 38271
 */
const path = require('path');
const os = require('os');
const fs = require('fs');
const net = require('net');
const { spawn } = require('child_process');

let dashboardProcess = null;

function getOpenClawHome() {
  return process.env.OPENCLAW_HOME || path.join(os.homedir(), '.openclaw');
}

function getDashboardDir() {
  const pluginDir = __dirname;
  return path.join(pluginDir, 'dashboard');
}

/**
 * 加载配置，优先级：env > 用户 config.json > api.pluginConfig > 默认
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

  const userConfigPath = path.join(openclawHome, 'dashboard', 'config.json');
  if (fs.existsSync(userConfigPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(userConfigPath, 'utf8'));
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

  const portPromise = isExplicitPort
    ? Promise.resolve(basePort)
    : findAvailablePort(basePort);

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

    const pythonCmd = process.env.PYTHON_CMD || 'python3';
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
      detached: true,
    });
    dashboardProcess.unref();

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
