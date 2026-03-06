#!/usr/bin/env bash
#
# 公共函数库 - 安装脚本共用
# 用法: source "$(dirname "$0")/../lib/common.sh" 或 source "$SCRIPT_DIR/lib/common.sh"
#

# ============================================
# 日志函数
# ============================================

log_info()  { echo "$1"; }
log_step()  { echo ""; echo ">>> $1"; }
log_ok()    { echo "✓ $1"; }
log_warn()  { echo "⚠ $1"; }
log_error() { echo "❌ $1" >&2; }

# ============================================
# 执行辅助
# ============================================

# run_silent: 静默执行命令（VERBOSE=1 时显示输出）
# 用法: run_silent command args...
run_silent() {
  if [ "${VERBOSE:-0}" = "1" ]; then
    "$@"
  else
    "$@" 2>/dev/null
  fi
}

# ============================================
# 配置目录解析（与 OpenClaw 内部逻辑一致）
# ============================================

# resolve_openclaw_config_dir: 解析 OpenClaw 配置目录
# 优先级: OPENCLAW_STATE_DIR > CLAWDBOT_STATE_DIR > OPENCLAW_HOME/.openclaw > HOME/.openclaw
# 用法: OPENCLAW_CONFIG_DIR=$(resolve_openclaw_config_dir)
resolve_openclaw_config_dir() {
  if [ -n "${OPENCLAW_STATE_DIR:-}" ]; then
    echo "${OPENCLAW_STATE_DIR}"
    return
  fi
  if [ -n "${CLAWDBOT_STATE_DIR:-}" ]; then
    echo "${CLAWDBOT_STATE_DIR}"
    return
  fi
  local home_dir="${OPENCLAW_HOME:-${HOME:-${USERPROFILE:-}}}"
  if [ -z "$home_dir" ]; then
    home_dir="${HOME:-}"
  fi
  # 展开 ~ 前缀（与 openclaw 行为一致）
  if [[ "$home_dir" == '~'* ]]; then
    home_dir="${HOME:-}${home_dir#\~}"
  fi
  echo "${home_dir}/.openclaw"
}

# ============================================
# JSON 版本解析
# ============================================

# parse_json_version: 从 JSON 文件解析 version 字段
# 优先使用 jq，回退 node，最后 grep+sed
# 用法: VERSION=$(parse_json_version plugin/openclaw.plugin.json)
parse_json_version() {
  local json_file="$1"
  if [ ! -f "$json_file" ]; then
    return 1
  fi
  if command -v jq &>/dev/null; then
    jq -r '.version' "$json_file"
  elif command -v node &>/dev/null; then
    node -e "const f=require('fs');console.log(JSON.parse(f.readFileSync(process.argv[1],'utf8')).version)" "$json_file"
  else
    # 最后兜底：使用 grep + sed
    grep '"version"' "$json_file" | head -1 | sed 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/'
  fi
}

# ============================================
# 系统检测
# ============================================

# detect_os: 检测操作系统
# 返回: linux, macos, windows, unknown
detect_os() {
  case "$(uname -s 2>/dev/null)" in
    Linux*)   echo "linux" ;;
    Darwin*)  echo "macos" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    *)        echo "unknown" ;;
  esac
}

# validate_os: 验证操作系统是否支持
# 用法: validate_os "$(detect_os)"
validate_os() {
  local os="$1"
  case "$os" in
    linux|macos|windows)
      log_info "系统: $os"
      ;;
    *)
      log_error "不支持的系统: $(uname -s 2>/dev/null || echo 'unknown')"
      log_info "支持的系统: Linux, macOS, Windows (Git Bash)"
      return 1
      ;;
  esac
}

# ============================================
# 下载辅助
# ============================================

# download_file: 下载文件（自动选择 curl 或 wget）
# 用法: download_file "https://example.com/file.tgz" "/tmp/file.tgz"
download_file() {
  local url="$1"
  local output="$2"

  log_info "  下载: $url"

  if command -v curl &>/dev/null; then
    if ! curl -fSL --progress-bar -o "$output" "$url"; then
      return 1
    fi
  elif command -v wget &>/dev/null; then
    if ! wget -q --show-progress -O "$output" "$url"; then
      return 1
    fi
  else
    log_error "需要 curl 或 wget 来下载文件"
    return 1
  fi

  return 0
}
