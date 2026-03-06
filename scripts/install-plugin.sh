#!/usr/bin/env bash
#
# OpenClaw Agent Dashboard 插件 - 安装/升级脚本
# 用法: npm run deploy（推荐）或 ./scripts/install-plugin.sh
#
# 配置目录与 OpenClaw 一致：OPENCLAW_STATE_DIR > OPENCLAW_HOME > HOME
#
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)

# 解析 OpenClaw 配置目录（与 openclaw 内部逻辑一致）
resolve_openclaw_config_dir() {
  if [ -n "${OPENCLAW_STATE_DIR}" ]; then
    echo "${OPENCLAW_STATE_DIR}"
    return
  fi
  if [ -n "${CLAWDBOT_STATE_DIR}" ]; then
    echo "${CLAWDBOT_STATE_DIR}"
    return
  fi
  local home_dir="${OPENCLAW_HOME:-${HOME:-$USERPROFILE}}"
  if [ -z "$home_dir" ]; then
    home_dir="$HOME"
  fi
  # 展开 ~ 前缀（与 openclaw 行为一致）
  if [[ "$home_dir" == '~'* ]]; then
    home_dir="${HOME:-$HOME}${home_dir#\~}"
  fi
  echo "${home_dir}/.openclaw"
}

OPENCLAW_CONFIG_DIR=$(resolve_openclaw_config_dir)
PLUGIN_PATH="${OPENCLAW_CONFIG_DIR}/extensions/openclaw-agent-dashboard"
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

# 2. 构建前端（若通过 npm run deploy 调用，pack 已构建，跳过）
if [ -d "$ROOT/frontend/dist" ] && [ -n "$(ls -A $ROOT/frontend/dist 2>/dev/null)" ]; then
  echo ""
  echo ">>> 1/4 前端已构建，跳过"
else
  echo ""
  echo ">>> 1/4 构建前端..."
  (cd frontend && npm install --silent 2>/dev/null; npm run build)
fi

# 3. 打包插件（若通过 npm run deploy 调用，pack 已完成，跳过）
if [ -d "$ROOT/plugin/dashboard" ] && [ -f "$ROOT/plugin/dashboard/main.py" ]; then
  echo ""
  echo ">>> 2/4 插件已打包，跳过"
else
  echo ""
  echo ">>> 2/4 打包插件..."
  node scripts/build-plugin.js
fi

# 4. 安装插件（openclaw install 会覆盖，无需先 rm，避免 plugins.allow 校验失败）
echo ""
echo ">>> 3/4 安装/覆盖插件..."
openclaw plugins install ./plugin

# 5. 安装 Python 依赖（优先 python3 -m pip，兼容无 pip 命令的环境）
if [ -f "$PLUGIN_PATH/dashboard/requirements.txt" ]; then
  echo ""
  if [ -n "$OLD_VERSION" ]; then
    echo ">>> 4/4 检查 Python 依赖..."
  else
    echo ">>> 4/4 安装 Python 依赖..."
  fi
  if python3 -m pip install -r "$PLUGIN_PATH/dashboard/requirements.txt" -q \
    || pip install -r "$PLUGIN_PATH/dashboard/requirements.txt" -q \
    || pip3 install -r "$PLUGIN_PATH/dashboard/requirements.txt" -q; then
    echo "✓ Python 依赖已就绪"
  else
    echo "❌ Python 依赖安装失败，请手动执行:"
    echo "   python3 -m pip install -r $PLUGIN_PATH/dashboard/requirements.txt"
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
echo "访问地址: http://localhost:38271"
echo ""
echo "若端口被占用，可创建 ~/.openclaw/dashboard/config.json 设置端口:"
echo '  {"port": 38271}'
echo ""
