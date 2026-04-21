#!/usr/bin/env node
/**
 * OpenClaw Agent Dashboard - 插件安装脚本（跨平台）
 *
 * 两种模式：
 * 1. 本地模式：从本地源码安装（npm run deploy 流程）
 * 2. 远程模式：从 GitHub Release 下载预构建包安装（npx 流程）
 *
 * 用法:
 *   node scripts/install.js           # 本地模式
 *   npx openclaw-agent-dashboard       # 远程模式（发布 npm 后）
 *   node scripts/install.js --verbose  # 显示详细输出
 *   node scripts/install.js --dry-run  # 预览
 *   node scripts/install.js --skip-python # 跳过 Python 依赖
 *   node scripts/install.js --version 1.0.4  # 指定版本（远程模式）
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
  copyDir,
  backupDir,
  restoreBackup,
  cleanupBackup,
  cleanupOldBackups,
  downloadFile,
  formatBytes,
} = require('./lib/common');

// ============================================
// 配置
// ============================================

const REPO_OWNER = 'Umarchen';
const REPO_NAME = 'openclaw-agent-dashboard';
const PLUGIN_ID = 'openclaw-agent-dashboard';

// ============================================
// 参数解析
// ============================================

function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {
    verbose: args.includes('--verbose') || args.includes('-v') || process.env.VERBOSE === '1',
    dryRun: args.includes('--dry-run'),
    skipPython: args.includes('--skip-python'),
    version: null,
  };

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--version' && args[i + 1]) {
      opts.version = args[++i];
    }
  }

  return opts;
}

// ============================================
// 判断安装模式
// ============================================

/**
 * 检测是否为远程模式（npx 触发，无本地源码）
 * @returns {boolean}
 */
function isRemoteMode() {
  // 如果本地 plugin 目录已打包好，优先用本地模式
  const pluginDir = path.join(__dirname, '..', 'plugin');
  const dashboardMain = path.join(pluginDir, 'dashboard', 'main.py');

  if (fs.existsSync(dashboardMain)) {
    return false;
  }

  // npx 模式下，__dirname 会在 npx 缓存目录中
  // 检查是否在 node_modules/.cache/npx 或类似路径中
  const execDir = path.dirname(__dirname);
  const inNpxCache = execDir.includes('npx') ||
    execDir.includes('_npx') ||
    execDir.includes('npm/_npx');

  return inNpxCache;
}

// ============================================
// 检查函数
// ============================================

function checkPrerequisites(remoteMode) {
  const os = detectOS();
  const checks = [{ cmd: 'node', hint: 'https://nodejs.org' }];

  if (!remoteMode) {
    checks.push({ cmd: 'openclaw', hint: 'npm install -g openclaw' });
  }

  // Python 检查
  if (!commandExists('python3') && !commandExists('python')) {
    logWarn('未找到 Python 3，Dashboard 后端可能无法运行');
    logInfo('安装指南: https://www.python.org');
  }

  let allPassed = true;
  for (const { cmd, hint } of checks) {
    if (!commandExists(cmd)) {
      logError(`未找到 ${cmd}，请先安装: ${hint}`);
      allPassed = false;
    }
  }

  return allPassed;
}

// ============================================
// 远程模式：tgz 解压（纯 Node.js，跨平台）
// ============================================

/**
 * 解析 tar 文件路径和大小
 * @param {Buffer} buffer - tar 数据
 * @returns {{name: string, size: number, type: string, offset: number}[]}
 */
function parseTarEntries(buffer) {
  const entries = [];
  let offset = 0;

  while (offset < buffer.length - 512) {
    // 读取文件名（0-99）
    let name = buffer.toString('utf8', offset, offset + 100).replace(/\0.*$/, '');

    // 跳过空块
    if (name === '') {
      offset += 512;
      continue;
    }

    // 文件大小（124-135，八进制）
    const sizeStr = buffer.toString('utf8', offset + 124, offset + 135).replace(/\0.*$/, '').trim();
    const size = parseInt(sizeStr, 8) || 0;

    // 文件类型（156）
    const type = buffer.toString('utf8', offset + 156, offset + 157);

    entries.push({ name, size, type, offset });

    // 跳到下一个条目（512 字节头 + 数据，数据按 512 对齐）
    const dataBlocks = Math.ceil(size / 512);
    offset += 512 + dataBlocks * 512;
  }

  return entries;
}

/**
 * 解压 tgz 文件到指定目录
 * @param {string} tgzFile - tgz 文件路径
 * @param {string} destDir - 目标目录
 * @param {boolean} verbose - 显示详细信息
 * @returns {Promise<boolean>}
 */
async function extractTgz(tgzFile, destDir, verbose) {
  const zlib = require('zlib');
  const fsPromises = require('fs').promises;

  return new Promise((resolve) => {
    const fileStream = fs.createReadStream(tgzFile);
    const gunzip = zlib.createGunzip();
    const chunks = [];

    gunzip.on('data', (chunk) => chunks.push(chunk));
    gunzip.on('end', () => {
      try {
        const tarData = Buffer.concat(chunks);
        const entries = parseTarEntries(tarData);

        for (const entry of entries) {
          // 跳过目录类型
          if (entry.type === '5') continue;
          // 跳过空文件名或 pax header
          if (!entry.name || entry.name.startsWith('PaxHeader')) continue;

          const fullPath = path.join(destDir, entry.name);
          fs.mkdirSync(path.dirname(fullPath), { recursive: true });

          // 写入文件数据
          const dataOffset = entry.offset + 512;
          const fileData = tarData.slice(dataOffset, dataOffset + entry.size);
          fs.writeFileSync(fullPath, fileData);

          if (verbose) {
            logInfo(`  ${entry.name} (${formatBytes(entry.size)})`);
          }
        }

        resolve(true);
      } catch (err) {
        logError(`解压处理失败: ${err.message}`);
        resolve(false);
      }
    });

    gunzip.on('error', (err) => {
      logError(`gzip 解压失败: ${err.message}`);
      resolve(false);
    });

    fileStream.on('error', (err) => {
      logError(`读取文件失败: ${err.message}`);
      resolve(false);
    });

    fileStream.pipe(gunzip);
  });
}

// ============================================
// 远程模式：版本解析
// ============================================

function resolveVersion(requested) {
  if (requested && requested !== 'latest') {
    return requested;
  }

  // 优先从本地 package.json 读取版本（npm/npx 安装时自带）
  try {
    const pkgPath = path.join(__dirname, '..', 'package.json');
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    if (pkg.version) return pkg.version;
  } catch {
    // ignore
  }

  // fallback: 从 GitHub API 获取最新 release 版本
  try {
    const https = require('https');
    const url = `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest`;

    return new Promise((resolve) => {
      https.get(url, {
        headers: { 'User-Agent': 'openclaw-agent-dashboard-installer' },
      }, (res) => {
        let data = '';
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
          try {
            const json = JSON.parse(data);
            const tag = json.tag_name || '';
            resolve(tag.replace(/^v/, '') || '1.0.0');
          } catch {
            logWarn('无法解析版本信息');
            resolve('1.0.0');
          }
        });
      }).on('error', () => {
        logWarn('无法连接 GitHub API');
        resolve('1.0.0');
      });
    });
  } catch {
    return Promise.resolve('1.0.0');
  }
}

// ============================================
// 远程模式：从 npm 包自带的 plugin 目录安装（无需下载 tgz）
// ============================================

async function localPluginInstall(bundledPluginDir, pluginPath, options) {
  const newVersion = parseJsonVersion(path.join(bundledPluginDir, 'openclaw.plugin.json'));
  const oldVersion = fs.existsSync(path.join(pluginPath, 'openclaw.plugin.json'))
    ? parseJsonVersion(path.join(pluginPath, 'openclaw.plugin.json'))
    : null;

  logInfo(`版本: ${newVersion}（npm 包自带）`);
  if (oldVersion) {
    logInfo(`  ${oldVersion} → ${newVersion}`);
  }

  // 备份旧版本
  if (fs.existsSync(pluginPath)) {
    logStep('备份旧版本...');
    backupDir(pluginPath);
    const extDir = path.dirname(pluginPath);
    cleanupOldBackups(extDir, `${PLUGIN_ID}.backup-`, 2);
    logOk('备份完成');
  }

  // 复制到插件目录
  logStep('安装插件...');
  if (fs.existsSync(pluginPath)) {
    rmrf(pluginPath);
  }
  copyDir(bundledPluginDir, pluginPath);
  logOk('插件已安装');

  // 安装 Python 依赖
  if (!options.skipPython && fs.existsSync(path.join(pluginPath, 'dashboard', 'requirements.txt'))) {
    logStep('安装 Python 依赖...');
    const scriptPath = path.join(__dirname, 'install-python-deps.js');
    const args = [scriptPath, pluginPath];
    if (options.verbose) args.push('--verbose');
    const result = runCommand('node', args, { silent: !options.verbose });
    if (!result.success) {
      logWarn('Python 依赖安装失败，Dashboard 启动时可能需要手动安装');
    }
  }

  // 清理旧备份
  logStep('清理旧备份...');
  const extDir = path.dirname(pluginPath);
  cleanupOldBackups(extDir, `${PLUGIN_ID}.backup-`, 1);

  return true;
}

// ============================================
// 远程模式：下载安装
// ============================================

/**
 * 获取 tgz 缓存目录
 * @returns {string}
 */
function getCacheDir() {
  if (process.platform === 'win32') {
    // Windows: %LOCALAPPDATA%\openclaw-agent-dashboard\cache
    const localAppData = process.env.LOCALAPPDATA || process.env.USERPROFILE || require('os').homedir();
    return path.join(localAppData, 'openclaw-agent-dashboard', 'cache');
  }
  // Linux/macOS: ~/.cache/openclaw-agent-dashboard
  const home = process.env.HOME || require('os').homedir();
  return path.join(home, '.cache', 'openclaw-agent-dashboard');
}

async function remoteInstall(pluginPath, options) {
  const tmpDir = path.join(require('os').tmpdir(), `oc-dashboard-install-${Date.now()}`);
  fs.mkdirSync(tmpDir, { recursive: true });

  // 优先使用 npm 包自带的 plugin 目录（npx 模式下 plugin 就在包里）
  const bundledPluginDir = path.join(__dirname, '..', 'plugin');
  const bundledPluginJson = path.join(bundledPluginDir, 'openclaw.plugin.json');
  const bundledDashboardMain = path.join(bundledPluginDir, 'dashboard', 'main.py');

  // 仅当 npm 包内带完整 plugin（含 dashboard）时才直接拷贝；否则走 GitHub Release tgz，避免残缺 plugin 覆盖用户目录
  if (fs.existsSync(bundledPluginJson) && fs.existsSync(bundledDashboardMain)) {
    return await localPluginInstall(bundledPluginDir, pluginPath, options);
  }

  try {
    // 1. 解析版本
    const version = await resolveVersion(options.version);
    logInfo(`版本: ${version}`);

    const downloadUrl = `https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/v${version}/${PLUGIN_ID}-v${version}.tgz`;
    const tgzFileName = `${PLUGIN_ID}-v${version}.tgz`;
    const cacheDir = getCacheDir();
    const cachedTgz = path.join(cacheDir, tgzFileName);
    const tgzFile = path.join(tmpDir, `${PLUGIN_ID}.tgz`);

    // 2. 检查缓存
    if (fs.existsSync(cachedTgz)) {
      logStep('使用本地缓存...');
      logInfo(`  缓存: ${cachedTgz}`);
      fs.copyFileSync(cachedTgz, tgzFile);
      logOk('缓存命中，跳过下载');
    } else {
      // 下载
      logStep('下载预构建包...');
      if (!await downloadFile(downloadUrl, tgzFile, { verbose: options.verbose })) {
        logError('下载失败');
        logInfo('');
        logInfo('可能原因:');
        logInfo('  1. 网络连接问题');
        logInfo('  2. 版本不存在: v' + version);
        logInfo('  3. GitHub 访问受限');
        logInfo('');
        logInfo('替代方案:');
        logInfo('  git clone https://github.com/' + REPO_OWNER + '/' + REPO_NAME + '.git');
        logInfo('  cd ' + REPO_NAME);
        logInfo('  npm install && npm run deploy');
        return false;
      }
      // 保存到缓存
      try {
        fs.mkdirSync(cacheDir, { recursive: true });
        fs.copyFileSync(tgzFile, cachedTgz);
        logInfo(`  已缓存到: ${cachedTgz}`);
      } catch (e) {
        // 缓存写入失败不影响安装
        if (options.verbose) logWarn(`缓存写入失败: ${e.message}`);
      }
      logOk('下载完成');
    }

    // 3. 解压 tgz（纯 Node.js 实现，不依赖系统 tar）
    logStep('解压安装包...');
    const extractDir = path.join(tmpDir, 'extract');
    fs.mkdirSync(extractDir, { recursive: true });

    let extractOk = false;
    try {
      extractOk = await extractTgz(tgzFile, extractDir, options.verbose);
    } catch (err) {
      logError(`解压失败: ${err.message}`);
    }

    if (!extractOk) {
      logError('解压失败');
      return false;
    }
    logOk('解压完成');

    // 找到解压后的 plugin 目录（tgz 内可能有一层 package 目录）
    let extractedPluginDir = extractDir;
    const entries = fs.readdirSync(extractDir);
    if (entries.length === 1) {
      const single = path.join(extractDir, entries[0]);
      if (fs.statSync(single).isDirectory() && fs.existsSync(path.join(single, 'openclaw.plugin.json'))) {
        extractedPluginDir = single;
      }
    }

    // 4. 获取新旧版本
    const newVersion = parseJsonVersion(path.join(extractedPluginDir, 'openclaw.plugin.json'));
    const oldVersion = fs.existsSync(path.join(pluginPath, 'openclaw.plugin.json'))
      ? parseJsonVersion(path.join(pluginPath, 'openclaw.plugin.json'))
      : null;

    if (oldVersion) {
      logInfo(`${oldVersion} → ${newVersion}`);
    }

    // 5. 备份旧版本
    if (fs.existsSync(pluginPath)) {
      logStep('备份旧版本...');
      const backupPath = backupDir(pluginPath);
      // 清理旧备份（保留最近2个）
      const extDir = path.dirname(pluginPath);
      cleanupOldBackups(extDir, `${PLUGIN_ID}.backup-`, 2);
      logOk('备份完成');
    }

    // 6. 安装
    logStep('安装插件...');

    // 复制到 extensions 目录，openclaw 会自动发现并加载，无需 plugins install
    copyDir(extractedPluginDir, pluginPath);
    logOk('插件已安装');

    if (!commandExists('openclaw')) {
      logWarn('未找到 openclaw 命令，请先安装: npm install -g openclaw');
    }

    // 7. 安装 Python 依赖
    if (!options.skipPython && fs.existsSync(path.join(pluginPath, 'dashboard', 'requirements.txt'))) {
      logStep('安装 Python 依赖...');
      const scriptPath = path.join(__dirname, 'install-python-deps.js');
      const args = [scriptPath, pluginPath];
      if (options.verbose) args.push('--verbose');
      const result = runCommand('node', args, { silent: !options.verbose });
      if (!result.success) {
        logWarn('Python 依赖安装失败，Dashboard 启动时可能需要手动安装');
      }
    }

    // 8. 清理旧备份（升级成功后）
    logStep('清理旧备份...');
    const extDir = path.dirname(pluginPath);
    cleanupOldBackups(extDir, `${PLUGIN_ID}.backup-`, 1);

    return true;
  } finally {
    // 清理临时目录
    rmrf(tmpDir);
  }
}

// ============================================
// 本地模式：原有流程（不变）
// ============================================

function isPluginPacked() {
  const pluginDir = path.join(__dirname, '..', 'plugin');
  const dashboardMain = path.join(pluginDir, 'dashboard', 'main.py');
  return fs.existsSync(dashboardMain);
}

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

  if (fs.existsSync(pluginPath)) {
    rmrf(pluginPath);
    logOk('  已删除旧目录');
  }

  return true;
}

async function installPlugin(verbose) {
  const rootDir = path.join(__dirname, '..');
  const pluginSrc = path.resolve(rootDir, 'plugin');
  const pluginPath = getPluginPath();

  // OpenClaw 新版会扫描「危险代码」(如 child_process)；Dashboard 插件需显式放行。
  // 使用绝对路径，避免 cwd 不在仓库根目录时 ./plugin 失效。
  const installFrom = (dir) =>
    runCommandAsync('openclaw', [
      'plugins',
      'install',
      dir,
      '--dangerously-force-unsafe-install',
    ]);

  logInfo(
    `  执行: openclaw plugins install ${pluginSrc} --dangerously-force-unsafe-install`,
  );
  let result = await installFrom(pluginSrc);

  if (!result.success) {
    logWarn('  首次安装失败，复制到 extensions 后重试...');
    copyDir(pluginSrc, pluginPath);
    logOk('  已复制插件目录');
    logInfo(
      `  执行: openclaw plugins install ${pluginPath} --dangerously-force-unsafe-install`,
    );
    result = await installFrom(pluginPath);
  }

  if (!result.success) {
    logError('插件安装失败');
    logError(
      `  可手动执行: openclaw plugins install ${pluginSrc} --dangerously-force-unsafe-install`,
    );
    return false;
  }

  logOk('插件已安装');
  return true;
}

function installPythonDeps(pluginPath, verbose) {
  const reqFile = path.join(pluginPath, 'dashboard', 'requirements.txt');

  if (!fs.existsSync(reqFile)) {
    logWarn('插件未正确安装（缺少 requirements.txt）');
    return false;
  }

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
  const remoteMode = isRemoteMode();

  logInfo(`系统: ${detectOS()}`);
  logInfo(`配置目录: ${resolveOpenClawConfigDir()}`);

  const pluginPath = getPluginPath();
  logInfo(`插件路径: ${pluginPath}`);
  console.log('');

  // dry-run
  if (options.dryRun) {
    const newVersion = remoteMode
      ? await resolveVersion(options.version)
      : parseJsonVersion(path.join(__dirname, '..', 'plugin', 'openclaw.plugin.json'));

    console.log('');
    logInfo(`[DRY-RUN] 模式: ${remoteMode ? '远程安装' : '本地安装'}`);
    logInfo(`[DRY-RUN] 版本: ${newVersion}`);
    logInfo(`[DRY-RUN] 安装到: ${pluginPath}`);
    if (!options.skipPython) {
      logInfo('[DRY-RUN] 安装 Python 依赖到 venv');
    }
    logOk('预览完成，未执行实际安装');
    process.exit(0);
  }

  if (remoteMode) {
    // ============ 远程模式 ============
    logInfo('=== OpenClaw Agent Dashboard 远程安装 ===');
    console.log('');

    if (!checkPrerequisites(true)) {
      process.exit(1);
    }

    const success = await remoteInstall(pluginPath, options);

    console.log('');
    if (success) {
      logOk('=== 安装完成 ===');
    } else {
      logError('安装失败');
      process.exit(1);
    }
  } else {
    // ============ 本地模式（原有流程） ============
    const rootDir = path.join(__dirname, '..');
    const newVersion = parseJsonVersion(path.join(rootDir, 'plugin', 'openclaw.plugin.json'));
    const oldVersion = fs.existsSync(path.join(pluginPath, 'openclaw.plugin.json'))
      ? parseJsonVersion(path.join(pluginPath, 'openclaw.plugin.json'))
      : null;

    if (oldVersion) {
      logInfo('=== OpenClaw Agent Dashboard 插件升级 ===');
      console.log('');
      logInfo(`  ${oldVersion} → ${newVersion}`);
    } else {
      logInfo('=== OpenClaw Agent Dashboard 插件安装 ===');
      console.log('');
      logInfo(`  版本: ${newVersion}`);
    }

    // 1. 检查前置条件
    logStep('1/4 检查前置条件...');
    if (!checkPrerequisites(false)) {
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
      installPythonDeps(pluginPath, options.verbose);
    } else {
      logStep('4/4 跳过 Python 依赖安装');
    }

    console.log('');
    if (oldVersion) {
      logOk(`=== 升级完成 (${oldVersion} → ${newVersion}) ===`);
    } else {
      logOk(`=== 安装完成 (v${newVersion}) ===`);
    }
  }

  // 公共完成提示
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
