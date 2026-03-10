#!/usr/bin/env bash
#
# OpenClaw Agent Dashboard 插件 - 安装/升级脚本
# 用法: npm run deploy（推荐）或 ./scripts/install-plugin.sh
#
# 选项:
#   VERBOSE=1   显示详细输出（包括 npm/pip 的错误信息）
#   DRY_RUN=1   仅预览，不执行实际安装
#
# 配置目录与 OpenClaw 一致：OPENCLAW_STATE_DIR > OPENCLAW_HOME > HOME
#
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
SCRIPT_DIR="$ROOT/scripts"

# 引入公共库
source "$SCRIPT_DIR/lib/common.sh"

# 环境变量
VERBOSE="${VERBOSE:-0}"
DRY_RUN="${DRY_RUN:-0}"

# ============================================
# 本脚本特有函数
# ============================================

# 获取已安装版本
get_installed_version() {
  local plugin_path="$1"
  if [ -f "$plugin_path/openclaw.plugin.json" ]; then
    parse_json_version "$plugin_path/openclaw.plugin.json"
  else
    echo ""
  fi
}

# 检查命令是否存在
check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    log_error "未找到 $1，请先安装: $2"
    exit 1
  fi
}

# ============================================
# 主流程
# ============================================

OPENCLAW_CONFIG_DIR=$(resolve_openclaw_config_dir)
PLUGIN_PATH="${OPENCLAW_CONFIG_DIR}/extensions/openclaw-agent-dashboard"
NEW_VERSION=$(parse_json_version "$ROOT/plugin/openclaw.plugin.json")
OLD_VERSION=$(get_installed_version "$PLUGIN_PATH")

log_info "[安装] 配置目录: $OPENCLAW_CONFIG_DIR"
log_info "[安装] 插件路径: $PLUGIN_PATH"
echo ""

# 显示标题（区分安装/升级）
if [ -n "$OLD_VERSION" ] && [ -d "$PLUGIN_PATH" ]; then
  log_info "=== OpenClaw Agent Dashboard 插件升级 ==="
  echo ""
  log_info "  $OLD_VERSION → $NEW_VERSION"
else
  log_info "=== OpenClaw Agent Dashboard 插件安装 ==="
  echo ""
  log_info "  版本: $NEW_VERSION"
fi

# dry-run 模式：仅预览
if [ "$DRY_RUN" = "1" ]; then
  echo ""
  log_info "[DRY-RUN] 将执行以下操作:"
  log_info "  - 安装插件到: $PLUGIN_PATH"
  log_info "  - 安装 Python 依赖到 venv 或 --user"
  log_ok "预览完成，未执行实际安装"
  exit 0
fi

# 1. 检查前置条件
check_cmd node "https://nodejs.org"
check_cmd python3 "https://www.python.org"
check_cmd openclaw "npm install -g openclaw"

echo ""
log_ok "前置条件检查通过"

# 2. 构建前端（若通过 npm run deploy 调用，pack 已构建，跳过）
if [ -d "$ROOT/frontend/dist" ] && [ -n "$(ls -A "$ROOT/frontend/dist" 2>/dev/null)" ]; then
  log_step "1/4 前端已构建，跳过"
else
  log_step "1/4 构建前端..."
  (cd frontend && run_silent npm install && npm run build)
fi

# 3. 打包插件（若通过 npm run deploy 调用，pack 已完成，跳过）
if [ -d "$ROOT/plugin/dashboard" ] && [ -f "$ROOT/plugin/dashboard/main.py" ]; then
  log_step "2/4 插件已打包，跳过"
else
  log_step "2/4 打包插件..."
  node scripts/build-plugin.js
fi

# 4. 安装插件（升级时用 uninstall 清理配置+目录，避免 plugins.allow 引用已删目录导致校验失败）
PLUGIN_ID="openclaw-agent-dashboard"
if [ -d "$PLUGIN_PATH" ]; then
  log_step "3/4 移除旧版本后安装..."
  log_info "    执行: openclaw plugins uninstall $PLUGIN_ID"
  if run_silent openclaw plugins uninstall "$PLUGIN_ID" --force; then
    log_ok "    已卸载（配置记录）"
  else
    log_warn "    uninstall 失败（可能未注册）"
  fi
  # uninstall 只删除配置记录，需要手动删除物理目录
  rm -rf "$PLUGIN_PATH"
  log_ok "    已删除旧目录"
else
  log_step "3/4 安装插件..."
fi
log_info "    目标: $PLUGIN_PATH"
log_info "    执行: openclaw plugins install ./plugin"
if ! openclaw plugins install ./plugin; then
  log_error "插件安装失败"
  exit 1
fi
log_ok "    插件已安装"

# 5. 安装 Python 依赖
# 详见 docs/python-environment-compatibility.md
if [ -f "$PLUGIN_PATH/dashboard/requirements.txt" ]; then
  if [ -n "$OLD_VERSION" ]; then
    log_step "4/4 检查 Python 依赖..."
  else
    log_step "4/4 安装 Python 依赖..."
  fi

  # 调用独立的 Python 依赖安装脚本
  DEPS_OPTS=""
  [ "$VERBOSE" = "1" ] && DEPS_OPTS="--verbose"

  if ! bash "$SCRIPT_DIR/install-python-deps.sh" "$PLUGIN_PATH" $DEPS_OPTS; then
    exit 1
  fi
else
  log_warn "插件未正确安装（缺少 requirements.txt）"
fi

# 完成
echo ""
if [ -n "$OLD_VERSION" ]; then
  log_ok "=== 升级完成 ($OLD_VERSION → $NEW_VERSION) ==="
else
  log_ok "=== 安装完成 (v$NEW_VERSION) ==="
fi
echo ""
log_info "执行任意 openclaw 命令（如 openclaw tui）时，Dashboard 会自动启动。"
log_info "访问地址: http://localhost:38271"
echo ""
log_info "若端口被占用，可创建 ~/.openclaw-agent-dashboard/config.json 设置端口:"
log_info '  {"port": 38271}'
echo ""
