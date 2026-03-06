/**
 * 公共函数库 - 安装脚本共用（Node.js 版）
 *
 * 提供跨平台的日志、系统检测、路径解析、命令执行等功能
 */

const os = require('os');
const fs = require('fs');
const path = require('path');
const { execSync, spawn } = require('child_process');

// ============================================
// 日志函数
// ============================================

/**
 * 输出普通信息
 * @param {string} msg
 */
function logInfo(msg) {
  console.log(msg);
}

/**
 * 输出步骤标题
 * @param {string} msg
 */
function logStep(msg) {
  console.log('\n>>> ' + msg);
}

/**
 * 输出成功信息
 * @param {string} msg
 */
function logOk(msg) {
  console.log('✓ ' + msg);
}

/**
 * 输出警告信息
 * @param {string} msg
 */
function logWarn(msg) {
  console.log('⚠ ' + msg);
}

/**
 * 输出错误信息
 * @param {string} msg
 */
function logError(msg) {
  console.error('❌ ' + msg);
}

// ============================================
// 系统检测
// ============================================

/**
 * 检测操作系统
 * @returns {'linux' | 'macos' | 'windows' | 'unknown'}
 */
function detectOS() {
  switch (process.platform) {
    case 'linux':
      return 'linux';
    case 'darwin':
      return 'macos';
    case 'win32':
      return 'windows';
    default:
      return 'unknown';
  }
}

/**
 * 检查命令是否存在
 * @param {string} cmd - 命令名称
 * @returns {boolean}
 */
function commandExists(cmd) {
  try {
    const isWin = process.platform === 'win32';
    // Windows 使用 where，Unix 使用 which
    const checkCmd = isWin ? 'where' : 'which';
    execSync(`${checkCmd} ${cmd}`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

// ============================================
// 路径解析
// ============================================

/**
 * 解析 OpenClaw 配置目录
 * 优先级: OPENCLAW_STATE_DIR > CLAWDBOT_STATE_DIR > OPENCLAW_HOME/.openclaw > HOME/.openclaw
 * @returns {string}
 */
function resolveOpenClawConfigDir() {
  // 1. OPENCLAW_STATE_DIR（最高优先级）
  if (process.env.OPENCLAW_STATE_DIR) {
    return expandHomeDir(process.env.OPENCLAW_STATE_DIR);
  }

  // 2. CLAWDBOT_STATE_DIR（兼容旧名称）
  if (process.env.CLAWDBOT_STATE_DIR) {
    return expandHomeDir(process.env.CLAWDBOT_STATE_DIR);
  }

  // 3. OPENCLAW_HOME/.openclaw
  let homeDir = process.env.OPENCLAW_HOME || process.env.HOME || os.homedir();
  homeDir = expandHomeDir(homeDir);

  return path.join(homeDir, '.openclaw');
}

/**
 * 展开 ~ 前缀为用户目录
 * @param {string} dir
 * @returns {string}
 */
function expandHomeDir(dir) {
  if (!dir) return os.homedir();
  if (dir === '~') return os.homedir();
  if (dir.startsWith('~/')) return path.join(os.homedir(), dir.slice(2));
  if (dir.startsWith('~')) return path.join(os.homedir(), dir.slice(1));
  return dir;
}

/**
 * 获取插件安装路径
 * @returns {string}
 */
function getPluginPath() {
  return path.join(resolveOpenClawConfigDir(), 'extensions', 'openclaw-agent-dashboard');
}

// ============================================
// JSON 解析
// ============================================

/**
 * 从 JSON 文件解析 version 字段
 * @param {string} filePath - JSON 文件路径
 * @returns {string | null}
 */
function parseJsonVersion(filePath) {
  try {
    if (!fs.existsSync(filePath)) {
      return null;
    }
    const content = fs.readFileSync(filePath, 'utf8');
    const json = JSON.parse(content);
    return json.version || null;
  } catch {
    return null;
  }
}

// ============================================
// 命令执行
// ============================================

/**
 * 对命令参数进行 shell 转义
 * @param {string} arg
 * @returns {string}
 */
function shellEscape(arg) {
  if (!arg) return "''";
  // 如果包含特殊字符，用单引号包裹
  if (/[^a-zA-Z0-9_\-./:=@]/.test(arg)) {
    return "'" + arg.replace(/'/g, "'\\''") + "'";
  }
  return arg;
}

/**
 * 同步执行命令
 * @param {string} cmd - 命令
 * @param {string[]} args - 参数
 * @param {object} options - 选项
 * @param {string} [options.cwd] - 工作目录
 * @param {boolean} [options.silent=true] - 是否静默（不显示输出）
 * @param {number} [options.timeout=120000] - 超时时间（毫秒）
 * @returns {{ success: boolean, code: number, output: string }}
 */
function runCommand(cmd, args = [], options = {}) {
  const { cwd, silent = true, timeout = 120000 } = options;

  try {
    // 构建命令字符串，对参数进行转义
    const cmdStr = [cmd, ...args.map(shellEscape)].join(' ');

    const result = execSync(
      cmdStr,
      {
        cwd,
        encoding: 'utf8',
        timeout,
        stdio: silent ? ['ignore', 'pipe', 'pipe'] : 'inherit',
        shell: process.platform === 'win32',
      }
    );
    return { success: true, code: 0, output: result || '' };
  } catch (error) {
    // 如果是静默模式且失败，返回错误信息
    const output = silent
      ? (error.stdout || error.stderr || error.message || '')
      : '';
    return {
      success: false,
      code: error.status || 1,
      output,
    };
  }
}

/**
 * 异步执行命令（实时输出到控制台）
 * @param {string} cmd - 命令
 * @param {string[]} args - 参数
 * @param {object} options - 选项
 * @param {string} [options.cwd] - 工作目录
 * @returns {Promise<{ success: boolean, code: number }>}
 */
function runCommandAsync(cmd, args = [], options = {}) {
  return new Promise((resolve) => {
    const { cwd } = options;

    const child = spawn(cmd, args, {
      cwd,
      stdio: 'inherit',
      shell: process.platform === 'win32',
    });

    child.on('close', (code) => {
      resolve({ success: code === 0, code: code || 0 });
    });

    child.on('error', (err) => {
      logError(`执行失败: ${err.message}`);
      resolve({ success: false, code: 1 });
    });
  });
}

// ============================================
// 文件操作辅助
// ============================================

/**
 * 递归删除目录
 * @param {string} dir
 */
function rmrf(dir) {
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * 递归复制目录
 * @param {string} src - 源目录
 * @param {string} dest - 目标目录
 * @param {string[]} [exclude=[]] - 排除的文件/目录名
 */
function copyDir(src, dest, exclude = []) {
  fs.mkdirSync(dest, { recursive: true });
  const entries = fs.readdirSync(src, { withFileTypes: true });

  for (const entry of entries) {
    // 跳过排除项
    if (exclude.includes(entry.name)) continue;
    // 跳过编译产物和日志
    if (entry.name.endsWith('.pyc') || entry.name.endsWith('.log')) continue;
    if (entry.name === '__pycache__' || entry.name === '.pytest_cache') continue;

    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);

    if (entry.isDirectory()) {
      copyDir(srcPath, destPath, exclude);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

// ============================================
// 导出
// ============================================

module.exports = {
  // 日志
  logInfo,
  logStep,
  logOk,
  logWarn,
  logError,

  // 系统检测
  detectOS,
  commandExists,

  // 路径解析
  resolveOpenClawConfigDir,
  expandHomeDir,
  getPluginPath,

  // JSON
  parseJsonVersion,

  // 命令执行
  runCommand,
  runCommandAsync,

  // 文件操作
  rmrf,
  copyDir,
};
