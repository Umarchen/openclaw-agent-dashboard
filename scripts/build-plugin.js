#!/usr/bin/env node
/**
 * 插件打包脚本
 * 1. 构建前端
 * 2. 复制 backend 到 plugin/dashboard
 * 3. 复制 frontend/dist 到 plugin/frontend-dist
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const ROOT = path.join(__dirname, '..');
const PLUGIN_DIR = path.join(ROOT, 'plugin');
const BACKEND_SRC = path.join(ROOT, 'src', 'backend');
const FRONTEND_DIR = path.join(ROOT, 'frontend');
const DASHBOARD_DEST = path.join(PLUGIN_DIR, 'dashboard');
const FRONTEND_DEST = path.join(PLUGIN_DIR, 'frontend-dist');

function rmrf(dir) {
  if (fs.existsSync(dir)) {
    fs.rmSync(dir, { recursive: true });
  }
}

function copyDir(src, dest, exclude = []) {
  fs.mkdirSync(dest, { recursive: true });
  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    if (exclude.includes(entry.name)) continue;
    if (entry.name.endsWith('.pyc') || entry.name.endsWith('.log')) continue;
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath, exclude);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

console.log('[pack] 1. 构建前端...');
// 检查是否需要安装依赖
const nodeModulesPath = path.join(FRONTEND_DIR, 'node_modules');
if (!fs.existsSync(nodeModulesPath)) {
  console.log('[pack] 安装前端依赖...');
  execSync('npm install', { cwd: FRONTEND_DIR, stdio: 'inherit' });
}
execSync('npm run build', { cwd: FRONTEND_DIR, stdio: 'inherit' });

console.log('[pack] 2. 复制 backend -> plugin/dashboard');
rmrf(DASHBOARD_DEST);
copyDir(BACKEND_SRC, DASHBOARD_DEST, ['__pycache__', '.pytest_cache']);

console.log('[pack] 3. 复制 frontend/dist -> plugin/frontend-dist');
rmrf(FRONTEND_DEST);
const frontendDist = path.join(FRONTEND_DIR, 'dist');
if (fs.existsSync(frontendDist)) {
  copyDir(frontendDist, FRONTEND_DEST);
} else {
  console.warn('[pack] frontend/dist 不存在，跳过');
}

console.log('[pack] 完成');
