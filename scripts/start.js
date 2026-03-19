/**
 * 跨平台启动脚本
 * 解决 Windows 下 npm run start 无法解析 Linux shell 语法的问题
 */
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');

// 环境变量处理（跨平台）
const OPENCLAW_HOME = process.env.OPENCLAW_HOME || path.join(os.homedir(), '.openclaw');
const DASHBOARD_PORT = process.env.DASHBOARD_PORT || '38271';

// Windows 使用 python，非 Windows 使用 python3
const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

// 工作目录
const backendDir = path.join(__dirname, '..', 'src', 'backend');

// 设置环境变量并启动 uvicorn
const env = {
  ...process.env,
  OPENCLAW_HOME,
  DASHBOARD_PORT
};

console.log(`Starting Dashboard...`);
console.log(`  OPENCLAW_HOME: ${OPENCLAW_HOME}`);
console.log(`  PORT: ${DASHBOARD_PORT}`);
console.log(`  Python: ${pythonCmd}`);

const child = spawn(pythonCmd, [
  '-m', 'uvicorn',
  'main:app',
  '--host', '0.0.0.0',
  '--port', DASHBOARD_PORT
], {
  cwd: backendDir,
  env,
  stdio: 'inherit',
  shell: process.platform === 'win32'
});

child.on('error', (err) => {
  console.error('Failed to start Dashboard:', err);
  process.exit(1);
});

child.on('exit', (code) => {
  process.exit(code || 0);
});
