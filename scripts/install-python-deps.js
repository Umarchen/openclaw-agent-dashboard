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
 *
 * 环境变量:
 *   PIP_INDEX_URL / PIP_MIRROR  指定 pip 源（与 pip 一致）
 *   OPENCLAW_PIP_MIRROR         强制镜像: tsinghua | tuna | https://完整索引 URL
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
// Pip 镜像与安装选项
// ============================================

/** 优先使用 wheel，避免在 Windows 上从源码编译 pydantic-core 等（需 Rust） */
const PIP_PREFER_BINARY = ['--prefer-binary'];

const TSINGHUA_PIP_ARGS = [
  '-i',
  'https://pypi.tuna.tsinghua.edu.cn/simple',
  '--trusted-host',
  'pypi.tuna.tsinghua.edu.cn',
];

/**
 * 解析 OPENCLAW_PIP_MIRROR，返回与 getPipMirrorArgs 相同形状的额外参数；无法识别则 null
 * @returns {string[] | null}
 */
function mirrorArgsFromOpenClawEnv() {
  const raw = (process.env.OPENCLAW_PIP_MIRROR || '').trim();
  if (!raw) return null;
  const lower = raw.toLowerCase();
  if (lower === 'tsinghua' || lower === 'tuna') {
    return TSINGHUA_PIP_ARGS;
  }
  if (lower.startsWith('http://') || lower.startsWith('https://')) {
    try {
      return ['-i', raw, '--trusted-host', new URL(raw).hostname];
    } catch {
      return null;
    }
  }
  return null;
}

// ============================================
// PyPI 连通性检测
// ============================================

/**
 * 检测 pypi.org 是否可达（超时 3 秒）
 * @returns {boolean}
 */
function checkPypiReachable() {
  try {
    const https = require('https');
    return new Promise((resolve) => {
      const req = https.get('https://pypi.org/simple/', { timeout: 3000 }, (res) => {
        resolve(res.statusCode === 200);
        req.destroy();
      });
      req.on('timeout', () => { req.destroy(); resolve(false); });
      req.on('error', () => { resolve(false); });
    });
  } catch {
    return false;
  }
}

/**
 * 获取 pip 镜像参数
 * 优先级: 环境变量 > 自动检测（pypi 不通则用清华镜像）> 无镜像
 * @returns {Promise<string[]>}
 */
async function getPipMirrorArgs() {
  const forced = mirrorArgsFromOpenClawEnv();
  if (forced) {
    logInfo('  已设置 OPENCLAW_PIP_MIRROR，使用该镜像');
    return forced;
  }
  const envMirror = process.env.PIP_INDEX_URL || process.env.PIP_MIRROR || '';
  if (envMirror) {
    return ['-i', envMirror, '--trusted-host', new URL(envMirror).hostname];
  }
  const reachable = await checkPypiReachable();
  if (!reachable) {
    logInfo('  pypi.org 不可达，使用清华镜像');
    return [...TSINGHUA_PIP_ARGS];
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
async function installWithVenv(reqFile, venvDir, silent) {
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
  const pipMirrorArgs = await getPipMirrorArgs();
  runCommand(
    venvPython,
    ['-m', 'pip', 'install', '--upgrade', ...PIP_PREFER_BINARY, 'pip', '-q', ...pipMirrorArgs],
    { silent: true }
  );

  // 安装依赖
  logInfo('  安装依赖...');
  const installResult = runCommand(
    venvPython,
    ['-m', 'pip', 'install', ...PIP_PREFER_BINARY, '-r', reqFile, '-q', ...pipMirrorArgs],
    { silent, timeout: 180000 }
  );

  if (!installResult.success) {
    // 默认源失败，尝试清华镜像
    if (!pipMirrorArgs.length) {
      logWarn('  默认源失败，尝试清华镜像...');
      const tsinghuaArgs = [...TSINGHUA_PIP_ARGS];
      runCommand(
        venvPython,
        ['-m', 'pip', 'install', '--upgrade', ...PIP_PREFER_BINARY, 'pip', '-q', ...tsinghuaArgs],
        { silent: true, timeout: 60000 }
      );
      const retryResult = runCommand(
        venvPython,
        ['-m', 'pip', 'install', ...PIP_PREFER_BINARY, '-r', reqFile, '-q', ...tsinghuaArgs],
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
async function installWithPipUser(reqFile, silent) {
  logInfo('  尝试: pip --user（PEP 668 兜底）');

  const pipMirrorArgs = await getPipMirrorArgs();
  const tsinghuaArgs = [...TSINGHUA_PIP_ARGS];

  const pipCommands = [
    {
      cmd: getPythonCmd(),
      args: ['-m', 'pip', 'install', ...PIP_PREFER_BINARY, '-r', reqFile, '-q', '--user', ...pipMirrorArgs],
      name: 'pip --user',
    },
    {
      cmd: getPythonCmd(),
      args: ['-m', 'pip', 'install', ...PIP_PREFER_BINARY, '-r', reqFile, '-q', ...pipMirrorArgs],
      name: 'pip',
    },
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
      {
        cmd: getPythonCmd(),
        args: ['-m', 'pip', 'install', ...PIP_PREFER_BINARY, '-r', reqFile, '-q', '--user', ...tsinghuaArgs],
        name: 'pip --user (tsinghua)',
      },
      {
        cmd: getPythonCmd(),
        args: ['-m', 'pip', 'install', ...PIP_PREFER_BINARY, '-r', reqFile, '-q', ...tsinghuaArgs],
        name: 'pip (tsinghua)',
      },
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
 * @returns {Promise<boolean>}
 */
async function installPythonDeps(pluginDir, options = {}) {
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
    if (await installWithVenv(reqFile, venvDir, silent)) {
      success = true;
      method = 'venv';
    }
  } else {
    logWarn('  venv 模块不可用');
  }

  // 策略 2: pip --user 兜底
  if (!success && !venvOnly) {
    const result = await installWithPipUser(reqFile, silent);
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
      console.log('1. 从 https://www.python.org 下载安装 Python 3（若遇依赖编译问题，可优先使用 3.11 / 3.12）');
      console.log('2. 安装时务必勾选 "Add Python to PATH"');
      console.log('3. 安装完成后重新打开终端');
      console.log('');
      console.log('若报错含 getaddrinfo failed / Errno 11001：多为 DNS 或公司网络无法访问 pypi.org');
      console.log('  可在 PowerShell 中先设置镜像再安装，例如：');
      console.log('    $env:OPENCLAW_PIP_MIRROR="tsinghua"');
      console.log('  或（与 pip 一致）：');
      console.log('    $env:PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"');
      console.log('    $env:PIP_TRUSTED_HOST="pypi.tuna.tsinghua.edu.cn"');
      console.log('');
      console.log('若报错含 pydantic-core、Rust、Cargo：多为 pip 走了源码包。请拉取最新插件（安装脚本会加 --prefer-binary），');
      console.log('  或手动：pip install --prefer-binary -r requirements.txt');
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

async function main() {
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
  const success = await installPythonDeps(pluginDir, { verbose, venvOnly });
  process.exit(success ? 0 : 1);
}

main().catch((err) => {
  logError(err && err.message ? err.message : String(err));
  process.exit(1);
});
