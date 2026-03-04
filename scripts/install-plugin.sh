#!/usr/bin/env bash
#
# OpenClaw Agent Dashboard 插件 - 安装/升级脚本
# 用法: npm run deploy（推荐）或 ./scripts/install-plugin.sh
#
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)

PLUGIN_PATH="$HOME/.openclaw/extensions/openclaw-agent-dashboard"
NEW_VERSION=$(grep '"version"' "$ROOT/plugin/openclaw.plugin.json" | sed 's/.*"version": *"\([^"]*\)".*/\1/')

# 获取已安装版本
get_installed_version() {
  if [ -f "$PLUGIN_PATH/openclaw.plugin.json" ]; then
    grep '"version"' "$PLUGIN_PATH/openclaw.plugin.json" | sed 's/.*"version": *"\([^"]*\)".*/\1/'
  else
    echo ""
  fi
}

OLD_VERSION=$(get_installed_version)

# 显示标题（区分安装/升级）
if [ -n "$OLD_VERSION" ] && [ -d "$PLUGIN_PATH" ]; then
  echo "=== OpenClaw Agent Dashboard 插件升级 ==="
  echo ""
  echo "  $OLD_VERSION → $NEW_VERSION"
else
  echo "=== OpenClaw Agent Dashboard 插件安装 ==="
  echo ""
  echo "  版本: $NEW_VERSION"
fi

# 1. 检查前置条件
check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "❌ 未找到 $1，请先安装: $2"
    exit 1
  fi
}
check_cmd node "https://nodejs.org"
check_cmd python3 "https://www.python.org"
check_cmd openclaw "npm install -g openclaw"

echo ""
echo "✓ 前置条件检查通过"

# 2. 构建前端
echo ""
echo ">>> 1/4 构建前端..."
(cd frontend && npm install --silent 2>/dev/null; npm run build)

# 3. 打包插件
echo ""
echo ">>> 2/4 打包插件..."
node scripts/build-plugin.js

# 4. 安装插件（若已存在则先删除）
if [ -d "$PLUGIN_PATH" ]; then
  echo ""
  echo ">>> 3/4 移除旧版本..."
  rm -rf "$PLUGIN_PATH"
fi

echo ""
echo ">>> 4/4 安装新版本..."
openclaw plugins install ./plugin

# 5. 安装 Python 依赖
if [ -f "$PLUGIN_PATH/dashboard/requirements.txt" ]; then
  echo ""
  if [ -n "$OLD_VERSION" ]; then
    echo ">>> 检查 Python 依赖..."
  else
    echo ">>> 安装 Python 依赖..."
  fi
  if pip install -r "$PLUGIN_PATH/dashboard/requirements.txt" 2>/dev/null || pip3 install -r "$PLUGIN_PATH/dashboard/requirements.txt" 2>/dev/null; then
    echo "✓ Python 依赖已就绪"
  else
    echo "❌ Python 依赖安装失败，请手动执行:"
    echo "   pip install -r $PLUGIN_PATH/dashboard/requirements.txt"
    exit 1
  fi
else
  echo ""
  echo "⚠ 插件未正确安装（缺少 requirements.txt）"
fi

# 完成
echo ""
if [ -n "$OLD_VERSION" ]; then
  echo "=== 升级完成 ($OLD_VERSION → $NEW_VERSION) ==="
else
  echo "=== 安装完成 (v$NEW_VERSION) ==="
fi
echo ""
echo "执行任意 openclaw 命令（如 openclaw tui）时，Dashboard 会自动启动。"
echo "访问地址: http://localhost:8000"
echo ""
echo "若端口被占用，可创建 ~/.openclaw/dashboard/config.json 设置端口:"
echo '  {"port": 8000}'
echo ""
