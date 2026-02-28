/**
 * OpenClaw Agent Dashboard - 插件入口
 * 启动 FastAPI 后端，随 OpenClaw 加载时自动运行
 *
 * 端口配置优先级（高到低）：
 * 1. 环境变量 DASHBOARD_PORT
 * 2. ~/.openclaw/dashboard/config.json
 * 3. openclaw.json 中 plugins.entries.openclaw-agent-dashboard.config.port
 * 4. 默认 8000
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
  let config = { port: 8000 };

  if (apiPluginConfig && typeof apiPluginConfig.port === 'number') {
    config.port = apiPluginConfig.port;
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

/** 找到可用端口，从 basePort 开始尝试 */
async function findAvailablePort(basePort, maxAttempts = 10) {
  for (let i = 0; i < maxAttempts; i++) {
    const port = basePort + i;
    if (await isPortAvailable(port)) return port;
  }
  return basePort;
}

function startDashboard(config = {}) {
  if (dashboardProcess) {
    console.log('[OpenClaw-Dashboard] 服务已在运行');
    return;
  }

  const dashboardDir = getDashboardDir();
  const openclawHome = getOpenClawHome();

  if (!fs.existsSync(dashboardDir)) {
    console.warn('[OpenClaw-Dashboard] dashboard 目录不存在，请先执行 npm run build 打包');
    return;
  }

  const basePort = config.port ?? 8000;

  findAvailablePort(basePort).then((port) => {
    if (dashboardProcess) return;

    const env = {
      ...process.env,
      OPENCLAW_HOME: openclawHome,
      DASHBOARD_PORT: String(port),
    };

    const pythonCmd = process.env.PYTHON_CMD || 'python3';
    const args = ['-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', String(port)];

    if (port !== basePort) {
      console.log(`[OpenClaw-Dashboard] 端口 ${basePort} 被占用，使用 ${port}`);
    }
    console.log(`[OpenClaw-Dashboard] 启动服务: ${pythonCmd} ${args.join(' ')}`);
    console.log(`[OpenClaw-Dashboard] 访问地址: http://localhost:${port}`);

    dashboardProcess = spawn(pythonCmd, args, {
      env,
      cwd: dashboardDir,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    dashboardProcess.stdout.on('data', (data) => {
      process.stdout.write(`[Dashboard] ${data}`);
    });
    dashboardProcess.stderr.on('data', (data) => {
      process.stderr.write(`[Dashboard] ${data}`);
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
