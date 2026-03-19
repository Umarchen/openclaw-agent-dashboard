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
  const isWin = process.platform === 'win32';

  try {
    // Windows 用双引号，Unix 用单引号
    const esc = (arg) => {
      if (!arg) return '""';
      if (isWin) {
        // Windows: 用双引号包裹含空格/特殊字符的路径
        if (/[^a-zA-Z0-9_\-./:=@]/.test(arg)) {
          return '"' + arg.replace(/"/g, '""') + '"';
        }
        return arg;
      } else {
        return shellEscape(arg);
      }
    };

    const cmdStr = [cmd, ...args.map(esc)].join(' ');

    const result = execSync(
      cmdStr,
      {
        cwd,
        encoding: 'utf8',
        timeout,
        stdio: silent ? ['ignore', 'pipe', 'pipe'] : 'inherit',
        shell: true,
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
// 网络下载
// ============================================

const https = require('https');
const http = require('http');

/**
 * 下载文件
 * @param {string} url - 下载地址
 * @param {string} dest - 保存路径
 * @param {object} [options]
 * @param {boolean} [options.verbose] - 显示进度
 * @returns {Promise<boolean>}
 */
function downloadFile(url, dest, options = {}) {
  return new Promise((resolve) => {
    logInfo(`  下载: ${url}`);

    const client = url.startsWith('https') ? https : http;
    const file = fs.createWriteStream(dest);

    client.get(url, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        file.close();
        fs.unlinkSync(dest);
        return downloadFile(res.headers.location, dest, options).then(resolve);
      }

      if (res.statusCode !== 200) {
        file.close();
        fs.unlinkSync(dest);
        logError(`  下载失败: HTTP ${res.statusCode}`);
        resolve(false);
        return;
      }

      const total = parseInt(res.headers['content-length'], 10);
      let downloaded = 0;

      res.on('data', (chunk) => {
        downloaded += chunk.length;
        if (options.verbose && total) {
          const pct = Math.round((downloaded / total) * 100);
          process.stdout.write(`  进度: ${pct}% (${formatBytes(downloaded)}/${formatBytes(total)})\r`);
        }
      });

      res.pipe(file);

      file.on('finish', () => {
        file.close();
        if (options.verbose) console.log('');
        resolve(true);
      });
    }).on('error', (err) => {
      file.close();
      if (fs.existsSync(dest)) fs.unlinkSync(dest);
      logError(`  下载失败: ${err.message}`);
      resolve(false);
    });
  });
}

/**
 * 格式化字节数
 * @param {number} bytes
 * @returns {string}
 */
function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1048576).toFixed(1) + ' MB';
}

// ============================================
// 备份与恢复
// ============================================

/**
 * 备份目录（移动到 .backup-{timestamp}）
 * @param {string} dir - 要备份的目录
 * @returns {string | null} 备份目录路径，失败返回 null
 */
function backupDir(dir) {
  if (!fs.existsSync(dir)) return null;

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const backupPath = dir + `.backup-${timestamp}`;

  try {
    fs.renameSync(dir, backupPath);
    logInfo(`  备份: ${path.basename(backupPath)}`);
    return backupPath;
  } catch (err) {
    logWarn(`  备份失败: ${err.message}`);
    // 尝试复制后删除
    try {
      copyDir(dir, backupPath);
      rmrf(dir);
      return backupPath;
    } catch {
      return null;
    }
  }
}

/**
 * 恢复备份
 * @param {string} backupPath - 备份目录路径
 * @param {string} targetPath - 目标路径
 * @returns {boolean}
 */
function restoreBackup(backupPath, targetPath) {
  if (!fs.existsSync(backupPath)) return false;

  try {
    rmrf(targetPath);
    fs.renameSync(backupPath, targetPath);
    return true;
  } catch {
    return false;
  }
}

/**
 * 清理备份目录
 * @param {string} backupPath
 */
function cleanupBackup(backupPath) {
  if (backupPath && fs.existsSync(backupPath)) {
    rmrf(backupPath);
    logInfo('  已清理备份');
  }
}

/**
 * 清理旧备份目录（只保留最新的 N 个）
 * @param {string} parentDir - 父目录
 * @param {string} prefix - 备份目录前缀
 * @param {number} [keep=2] - 保留数量
 */
function cleanupOldBackups(parentDir, prefix, keep = 2) {
  if (!fs.existsSync(parentDir)) return;

  const dirs = fs.readdirSync(parentDir)
    .filter(f => f.startsWith(prefix) && fs.statSync(path.join(parentDir, f)).isDirectory())
    .sort()
    .reverse();

  // 保留最新的 keep 个，删除其余
  for (let i = keep; i < dirs.length; i++) {
    rmrf(path.join(parentDir, dirs[i]));
    logInfo(`  清理旧备份: ${dirs[i]}`);
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
  backupDir,
  restoreBackup,
  cleanupBackup,
  cleanupOldBackups,

  // 网络下载
  downloadFile,
  formatBytes,
};
