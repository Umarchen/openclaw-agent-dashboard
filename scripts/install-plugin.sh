#!/usr/bin/env bash
#
# OpenClaw Agent Dashboard 插件 - 一键安装
# 用法: ./scripts/install-plugin.sh
#
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)

echo "=== OpenClaw Agent Dashboard 插件安装 ==="

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
PLUGIN_PATH="$HOME/.openclaw/extensions/openclaw-agent-dashboard"
if [ -d "$PLUGIN_PATH" ]; then
  echo ""
  echo ">>> 检测到已安装插件，先移除..."
  rm -rf "$PLUGIN_PATH"
fi

echo ""
echo ">>> 3/4 安装插件..."
openclaw plugins install ./plugin

# 5. 安装 Python 依赖
if [ -f "$PLUGIN_PATH/dashboard/requirements.txt" ]; then
  echo ""
  echo ">>> 4/4 安装 Python 依赖..."
  (pip install -q -r "$PLUGIN_PATH/dashboard/requirements.txt" || pip3 install -q -r "$PLUGIN_PATH/dashboard/requirements.txt") 2>/dev/null || {
    echo "⚠ 请手动执行: pip install -r $PLUGIN_PATH/dashboard/requirements.txt"
  }
else
  echo ""
  echo ">>> 4/4 跳过（插件未正确安装）"
fi

echo ""
echo "=== 安装完成 ==="
echo ""
echo "执行任意 openclaw 命令（如 openclaw tui）时，Dashboard 会自动启动。"
echo "访问地址: http://localhost:8000"
echo ""
echo "若端口被占用，可创建 ~/.openclaw/dashboard/config.json 设置端口:"
echo '  {"port": 8001}'
echo ""
