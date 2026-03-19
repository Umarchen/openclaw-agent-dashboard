#!/usr/bin/env node
/**
 * Python 依赖安装脚本（跨平台）
 * 用法: node scripts/install-python-deps.js <plugin_dir> [--verbose]
 *
 * 策略:
 * 1. venv（推荐，不受 PEP 668 影响）
 * 2. pip --user（兜底）
 *
 * 选项:
 *   --verbose, -v    显示详细输出
 *   --venv-only      仅使用 venv，不回退 pip
 */

const fs = require('fs');
const path = require('path');
const {
  logInfo,
  logOk,
  logWarn,
  logError,
  detectOS,
  commandExists,
  runCommand,
  rmrf,
} = require('./lib/common');

// ============================================
// 参数解析
// ============================================

/**
 * 解析命令行参数
 * @returns {{ pluginDir: string | null, verbose: boolean, venvOnly: boolean }}
 */
function parseArgs() {
  const args = process.argv.slice(2);
  let pluginDir = null;
  let verbose = false;
  let venvOnly = false;

  for (const arg of args) {
    if (arg === '--verbose' || arg === '-v') {
      verbose = true;
    } else if (arg === '--venv-only') {
      venvOnly = true;
    } else if (!arg.startsWith('-')) {
      pluginDir = arg;
    }
  }

  return { pluginDir, verbose, venvOnly };
}

// ============================================
// Python 环境检测
// ============================================

/**
 * 获取 Python 命令（跨平台）
 * Windows 通常是 python，Linux/macOS 通常是 python3
 * @returns {string}
 */
function getPythonCmd() {
  if (runCommand('python3', ['--version'], { silent: true }).success) return 'python3';
  if (runCommand('python', ['--version'], { silent: true }).success) return 'python';
  return 'python3'; // 默认
}

/**
 * 检查 venv 模块是否可用
 * @returns {boolean}
 */
function checkVenvModule() {
  const pythonCmd = getPythonCmd();
  const result = runCommand(pythonCmd, ['-c', 'import venv'], { silent: true });
  return result.success;
}

/**
 * 检查 pip 模块是否可用
 * @returns {boolean}
 */
function checkPipModule() {
  const pythonCmd = getPythonCmd();
  // 尝试 python -m pip
  let result = runCommand(pythonCmd, ['-m', 'pip', '--version'], { silent: true });
  if (result.success) return true;

  // 尝试 pip3 / pip
  if (commandExists('pip3')) return true;
  if (commandExists('pip')) return true;

  return false;
}

/**
 * 获取 venv Python 路径
 * @param {string} venvDir
 * @returns {string | null}
 */
function getVenvPython(venvDir) {
  // Unix: venv/bin/python
  const unixPath = path.join(venvDir, 'bin', 'python');
  if (fs.existsSync(unixPath)) return unixPath;

  // Windows: venv\Scripts\python.exe
  const winPath = path.join(venvDir, 'Scripts', 'python.exe');
  if (fs.existsSync(winPath)) return winPath;

  return null;
}

// ============================================
// Pip 镜像
// ============================================

/**
 * 获取 pip 镜像参数
 * 支持环境变量 PIP_INDEX_URL 或 PIP_MIRROR
 * @returns {string[]}
 */
function getPipMirrorArgs() {
  const mirror = process.env.PIP_INDEX_URL || process.env.PIP_MIRROR || '';
  if (mirror) {
    return ['-i', mirror, '--trusted-host', new URL(mirror).hostname];
  }
  return [];
}

// ============================================
// Python 依赖安装
// ============================================

/**
 * 使用 venv 安装依赖
 * @param {string} reqFile
 * @param {string} venvDir
 * @param {boolean} silent
 * @returns {boolean}
 */
function installWithVenv(reqFile, venvDir, silent) {
  logInfo('  尝试: venv（推荐，不受 PEP 668 影响）');

  // 清理旧 venv
  if (fs.existsSync(venvDir)) {
    rmrf(venvDir);
  }

  // 创建 venv
  logInfo('  创建虚拟环境...');
  const pythonCmd = getPythonCmd();
  const createResult = runCommand(pythonCmd, ['-m', 'venv', venvDir], { silent });
  if (!createResult.success) {
    logWarn('  venv 创建失败');
    if (!silent) {
      console.log('    错误:', createResult.output);
    }
    return false;
  }

  // 获取 venv Python 路径
  const venvPython = getVenvPython(venvDir);
  if (!venvPython) {
    logWarn('  无法找到 venv Python');
    return false;
  }

  // 升级 pip（静默，失败不影响）
  // 如果设了镜像，升级 pip 也用镜像
  const pipMirrorArgs = getPipMirrorArgs();
  runCommand(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip', '-q', ...pipMirrorArgs], { silent: true });

  // 安装依赖
  logInfo('  安装依赖...');
  const installResult = runCommand(
    venvPython,
    ['-m', 'pip', 'install', '-r', reqFile, '-q', ...pipMirrorArgs],
    { silent, timeout: 180000 }
  );

  if (!installResult.success) {
    // 默认源失败，尝试清华镜像
    if (!pipMirrorArgs.length) {
      logWarn('  默认源失败，尝试清华镜像...');
      const tsinghuaArgs = ['-i', 'https://pypi.tuna.tsinghua.edu.cn/simple', '--trusted-host', 'pypi.tuna.tsinghua.edu.cn'];
      runCommand(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip', '-q', ...tsinghuaArgs], { silent: true, timeout: 60000 });
      const retryResult = runCommand(
        venvPython,
        ['-m', 'pip', 'install', '-r', reqFile, '-q', ...tsinghuaArgs],
        { silent, timeout: 180000 }
      );
      if (retryResult.success) return true;
    }
    logWarn('  venv 安装依赖失败');
    if (!silent) {
      console.log('    错误:', installResult.output);
    }
    return false;
  }

  return true;
}

/**
 * 使用 pip --user 安装依赖
 * @param {string} reqFile
 * @param {boolean} silent
 * @returns {{ success: boolean, method: string | null }}
 */
function installWithPipUser(reqFile, silent) {
  logInfo('  尝试: pip --user（PEP 668 兜底）');

  const pipMirrorArgs = getPipMirrorArgs();
  const tsinghuaArgs = ['-i', 'https://pypi.tuna.tsinghua.edu.cn/simple', '--trusted-host', 'pypi.tuna.tsinghua.edu.cn'];

  const pipCommands = [
    { cmd: getPythonCmd(), args: ['-m', 'pip', 'install', '-r', reqFile, '-q', '--user', ...pipMirrorArgs], name: 'pip --user' },
    { cmd: getPythonCmd(), args: ['-m', 'pip', 'install', '-r', reqFile, '-q', ...pipMirrorArgs], name: 'pip' },
  ];

  for (const { cmd, args, name } of pipCommands) {
    if (!commandExists(cmd)) continue;

    const result = runCommand(cmd, args, { silent, timeout: 180000 });
    if (result.success) {
      return { success: true, method: name };
    }
  }

  // 默认源失败，尝试清华镜像
  if (!pipMirrorArgs.length) {
    logWarn('  默认源失败，尝试清华镜像...');
    const retryCommands = [
      { cmd: getPythonCmd(), args: ['-m', 'pip', 'install', '-r', reqFile, '-q', '--user', ...tsinghuaArgs], name: 'pip --user (tsinghua)' },
      { cmd: getPythonCmd(), args: ['-m', 'pip', 'install', '-r', reqFile, '-q', ...tsinghuaArgs], name: 'pip (tsinghua)' },
    ];
    for (const { cmd, args, name } of retryCommands) {
      if (!commandExists(cmd)) continue;
      const result = runCommand(cmd, args, { silent, timeout: 180000 });
      if (result.success) return { success: true, method: name };
    }
  }

  return { success: false, method: null };
}

/**
 * 安装 Python 依赖
 * @param {string} pluginDir
 * @param {object} options
 * @param {boolean} [options.verbose]
 * @param {boolean} [options.venvOnly]
 * @returns {boolean}
 */
function installPythonDeps(pluginDir, options = {}) {
  const { verbose = false, venvOnly = false } = options;
  const reqFile = path.join(pluginDir, 'dashboard', 'requirements.txt');
  const venvDir = path.join(pluginDir, 'dashboard', '.venv');

  // 检查 requirements.txt
  if (!fs.existsSync(reqFile)) {
    logWarn('未找到 requirements.txt');
    return false;
  }

  const silent = !verbose;
  let success = false;
  let method = null;

  // 策略 1: venv（推荐）
  if (checkVenvModule()) {
    if (installWithVenv(reqFile, venvDir, silent)) {
      success = true;
      method = 'venv';
    }
  } else {
    logWarn('  venv 模块不可用');
  }

  // 策略 2: pip --user 兜底
  if (!success && !venvOnly) {
    const result = installWithPipUser(reqFile, silent);
    if (result.success) {
      success = true;
      method = result.method;
    }
  }

  // 结果
  if (success) {
    logOk(`Python 依赖已就绪 (${method})`);
    return true;
  } else {
    logError('Python 依赖安装失败');
    printPythonDepsHelp(reqFile);
    return false;
  }
}

// ============================================
// 帮助信息
// ============================================

/**
 * 打印 Python 依赖安装帮助
 * @param {string} reqFile
 */
function printPythonDepsHelp(reqFile) {
  const os = detectOS();

  console.log('');
  console.log('========================================');
  console.log('请检查以下系统依赖是否已安装：');
  console.log('========================================');
  console.log('');

  switch (os) {
    case 'linux':
      console.log('检测到 Linux 系统');
      console.log('');
      console.log('Debian/Ubuntu:');
      console.log('  sudo apt update && sudo apt install python3 python3-pip python3-venv');
      console.log('');
      console.log('Fedora/CentOS/RHEL:');
      console.log('  sudo dnf install python3 python3-pip');
      console.log('');
      break;

    case 'macos':
      console.log('检测到 macOS 系统');
      console.log('');
      console.log('使用 Homebrew:');
      console.log('  brew install python3');
      console.log('');
      break;

    case 'windows':
      console.log('检测到 Windows 系统');
      console.log('');
      console.log('1. 从 https://www.python.org 下载安装 Python 3');
      console.log('2. 安装时务必勾选 "Add Python to PATH"');
      console.log('3. 安装完成后重新打开终端');
      console.log('');
      break;

    default:
      console.log('请确保已安装：');
      console.log('  - Python 3');
      console.log('  - pip (python3-pip)');
      console.log('  - venv 模块 (python3-venv，Linux 通常需要单独安装)');
      console.log('');
  }

  console.log('========================================');
  console.log('安装系统依赖后，重新执行：');
  console.log('========================================');
  console.log('');
  console.log('  npm run deploy');
  console.log('');
  console.log('或手动安装依赖：');
  console.log('');
  console.log(`  python3 -m pip install -r ${reqFile} --user`);
  console.log('');
  console.log('========================================');
  console.log('调试模式：');
  console.log('========================================');
  console.log('');
  console.log('  VERBOSE=1 npm run deploy');
  console.log('');
}

// ============================================
// 主函数
// ============================================

function main() {
  const { pluginDir, verbose, venvOnly } = parseArgs();

  // 检查参数
  if (!pluginDir) {
    console.log('用法: node scripts/install-python-deps.js <plugin_dir> [options]');
    console.log('');
    console.log('参数:');
    console.log('  plugin_dir    插件安装目录 (必须)');
    console.log('');
    console.log('选项:');
    console.log('  --verbose, -v  显示详细输出');
    console.log('  --venv-only    仅使用 venv，不回退 pip');
    process.exit(1);
  }

  // 检查目录
  if (!fs.existsSync(pluginDir)) {
    logError(`插件目录不存在: ${pluginDir}`);
    process.exit(1);
  }

  // 执行安装
  const success = installPythonDeps(pluginDir, { verbose, venvOnly });
  process.exit(success ? 0 : 1);
}

main();
