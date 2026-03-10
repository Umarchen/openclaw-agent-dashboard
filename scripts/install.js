#!/usr/bin/env node
/**
 * OpenClaw Agent Dashboard - 插件安装脚本（跨平台）
 * 用法: npm run install 或 node scripts/install.js
 *
 * 选项:
 *   --verbose, -v    显示详细输出
 *   --dry-run        仅预览，不执行实际安装
 *   --skip-python    跳过 Python 依赖安装
 *
 * 环境变量:
 *   VERBOSE=1        显示详细输出
 */

const fs = require('fs');
const path = require('path');
const {
  logInfo,
  logStep,
  logOk,
  logWarn,
  logError,
  detectOS,
  commandExists,
  resolveOpenClawConfigDir,
  getPluginPath,
  parseJsonVersion,
  runCommand,
  runCommandAsync,
  rmrf,
} = require('./lib/common');

// ============================================
// 参数解析
// ============================================

/**
 * 解析命令行参数
 * @returns {{ verbose: boolean, dryRun: boolean, skipPython: boolean }}
 */
function parseArgs() {
  const args = process.argv.slice(2);
  return {
    verbose: args.includes('--verbose') || args.includes('-v') || process.env.VERBOSE === '1',
    dryRun: args.includes('--dry-run'),
    skipPython: args.includes('--skip-python'),
  };
}

// ============================================
// 检查函数
// ============================================

/**
 * 检查前置条件
 * @returns {boolean}
 */
function checkPrerequisites() {
  const os = detectOS();
  const checks = [
    { cmd: 'node', hint: 'https://nodejs.org' },
    { cmd: 'python3', hint: os === 'windows' ? 'https://www.python.org（安装时勾选 "Add Python to PATH"）' : 'https://www.python.org' },
    { cmd: 'openclaw', hint: 'npm install -g openclaw' },
  ];

  let allPassed = true;

  for (const { cmd, hint } of checks) {
    if (!commandExists(cmd)) {
      logError(`未找到 ${cmd}，请先安装: ${hint}`);
      allPassed = false;
    }
  }

  return allPassed;
}

/**
 * 检查插件是否已打包
 * @returns {boolean}
 */
function isPluginPacked() {
  const pluginDir = path.join(__dirname, '..', 'plugin');
  const dashboardMain = path.join(pluginDir, 'dashboard', 'main.py');
  return fs.existsSync(dashboardMain);
}

// ============================================
// 安装步骤
// ============================================

/**
 * 卸载旧版本
 * @param {string} pluginPath
 * @param {boolean} verbose
 * @returns {Promise<boolean>}
 */
async function uninstallOld(pluginPath, verbose) {
  if (!fs.existsSync(pluginPath)) {
    logOk('无旧版本');
    return true;
  }

  logInfo('  执行: openclaw plugins uninstall openclaw-agent-dashboard --force');

  const result = await runCommandAsync('openclaw', ['plugins', 'uninstall', 'openclaw-agent-dashboard', '--force']);

  if (result.success) {
    logOk('  已卸载（配置记录）');
  } else {
    logWarn('  uninstall 失败（可能未注册）');
  }

  // 删除物理目录
  if (fs.existsSync(pluginPath)) {
    rmrf(pluginPath);
    logOk('  已删除旧目录');
  }

  return true;
}

/**
 * 安装插件
 * @param {boolean} verbose
 * @returns {Promise<boolean>}
 */
async function installPlugin(verbose) {
  logInfo('  执行: openclaw plugins install ./plugin');

  const result = await runCommandAsync('openclaw', ['plugins', 'install', './plugin']);

  if (!result.success) {
    logError('插件安装失败');
    return false;
  }

  logOk('插件已安装');
  return true;
}

/**
 * 安装 Python 依赖
 * @param {string} pluginPath
 * @param {boolean} verbose
 * @returns {boolean}
 */
function installPythonDeps(pluginPath, verbose) {
  const reqFile = path.join(pluginPath, 'dashboard', 'requirements.txt');

  if (!fs.existsSync(reqFile)) {
    logWarn('插件未正确安装（缺少 requirements.txt）');
    return false;
  }

  // 调用独立的 Python 依赖安装脚本
  const scriptPath = path.join(__dirname, 'install-python-deps.js');
  const args = [scriptPath, pluginPath];
  if (verbose) args.push('--verbose');

  const result = runCommand('node', args, { silent: !verbose });
  return result.success;
}

// ============================================
// 主流程
// ============================================

async function main() {
  const options = parseArgs();
  const os = detectOS();

  // 显示系统信息
  logInfo(`系统: ${os}`);
  logInfo(`配置目录: ${resolveOpenClawConfigDir()}`);

  const pluginPath = getPluginPath();
  logInfo(`插件路径: ${pluginPath}`);
  console.log('');

  // 获取版本信息
  const rootDir = path.join(__dirname, '..');
  const newVersion = parseJsonVersion(path.join(rootDir, 'plugin', 'openclaw.plugin.json'));
  const oldVersion = fs.existsSync(path.join(pluginPath, 'openclaw.plugin.json'))
    ? parseJsonVersion(path.join(pluginPath, 'openclaw.plugin.json'))
    : null;

  // 显示标题
  if (oldVersion) {
    logInfo('=== OpenClaw Agent Dashboard 插件升级 ===');
    console.log('');
    logInfo(`  ${oldVersion} → ${newVersion}`);
  } else {
    logInfo('=== OpenClaw Agent Dashboard 插件安装 ===');
    console.log('');
    logInfo(`  版本: ${newVersion}`);
  }

  // dry-run 模式
  if (options.dryRun) {
    console.log('');
    logInfo('[DRY-RUN] 将执行以下操作:');
    logInfo(`  - 安装插件到: ${pluginPath}`);
    if (!options.skipPython) {
      logInfo('  - 安装 Python 依赖到 venv 或 --user');
    }
    logOk('预览完成，未执行实际安装');
    process.exit(0);
  }

  // 1. 检查前置条件
  logStep('1/4 检查前置条件...');
  if (!checkPrerequisites()) {
    process.exit(1);
  }
  logOk('前置条件检查通过');

  // 2. 检查插件是否已打包
  logStep('2/4 检查插件打包...');
  if (!isPluginPacked()) {
    logError('插件未打包，请先执行: npm run pack');
    process.exit(1);
  }
  logOk('插件已打包');

  // 3. 安装插件
  if (fs.existsSync(pluginPath)) {
    logStep('3/4 移除旧版本后安装...');
  } else {
    logStep('3/4 安装插件...');
  }

  await uninstallOld(pluginPath, options.verbose);

  if (!await installPlugin(options.verbose)) {
    process.exit(1);
  }

  // 4. 安装 Python 依赖
  if (!options.skipPython) {
    logStep('4/4 安装 Python 依赖...');
    // Python 依赖安装失败不阻止整体流程
    installPythonDeps(pluginPath, options.verbose);
  } else {
    logStep('4/4 跳过 Python 依赖安装');
  }

  // 完成
  console.log('');
  if (oldVersion) {
    logOk(`=== 升级完成 (${oldVersion} → ${newVersion}) ===`);
  } else {
    logOk(`=== 安装完成 (v${newVersion}) ===`);
  }
  console.log('');
  logInfo('执行任意 openclaw 命令（如 openclaw tui）时，Dashboard 会自动启动。');
  logInfo('访问地址: http://localhost:38271');
  console.log('');
  logInfo('若端口被占用，可创建 ~/.openclaw-agent-dashboard/config.json 设置端口:');
  logInfo('  {"port": 38271}');
  console.log('');
}

main().catch((err) => {
  logError(`安装失败: ${err.message}`);
  if (process.env.VERBOSE === '1') {
    console.error(err);
  }
  process.exit(1);
});
