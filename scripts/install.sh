#!/usr/bin/env bash
#
# OpenClaw Agent Dashboard - 一键安装脚本
# 用法: curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh | bash
#
# 选项:
#   DASHBOARD_VERSION=x.x.x     安装指定版本 (默认: latest)
#   DASHBOARD_RELEASE_URL=URL   使用自定义下载地址
#   DASHBOARD_SKIP_PYTHON=1     跳过 Python 依赖安装
#   VERBOSE=1                   显示详细输出
#   DRY_RUN=1                   仅预览，不执行实际安装
#
set -euo pipefail

# ============================================
# [公共函数] 与 scripts/lib/common.sh 同步
# ============================================

log_info()  { echo "$1"; }
log_step()  { echo ""; echo ">>> $1"; }
log_ok()    { echo "✓ $1"; }
log_warn()  { echo "⚠ $1"; }
log_error() { echo "❌ $1" >&2; }

run_silent() {
  if [ "${VERBOSE:-0}" = "1" ]; then
    "$@"
  else
    "$@" 2>/dev/null
  fi
}

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
  if [[ "$home_dir" == '~'* ]]; then
    home_dir="${HOME:-}${home_dir#\~}"
  fi
  echo "${home_dir}/.openclaw"
}

detect_os() {
  case "$(uname -s 2>/dev/null)" in
    Linux*)   echo "linux" ;;
    Darwin*)  echo "macos" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    *)        echo "unknown" ;;
  esac
}

validate_os() {
  local os="$1"
  case "$os" in
    linux|macos|windows)
      log_info "系统: $os"
      ;;
    *)
      log_error "不支持的系统: $(uname -s 2>/dev/null || echo 'unknown')"
      log_info "支持的系统: Linux, macOS, Windows (Git Bash)"
      exit 1
      ;;
  esac
}

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
    exit 1
  fi
  return 0
}

# ============================================
# 配置
# ============================================

REPO_OWNER="Umarchen"
REPO_NAME="openclaw-agent-dashboard"
PLUGIN_ID="openclaw-agent-dashboard"

# ============================================
# 环境变量
# ============================================

VERBOSE="${VERBOSE:-0}"
DRY_RUN="${DRY_RUN:-0}"
DASHBOARD_VERSION="${DASHBOARD_VERSION:-latest}"
DASHBOARD_RELEASE_URL="${DASHBOARD_RELEASE_URL:-}"
DASHBOARD_SKIP_PYTHON="${DASHBOARD_SKIP_PYTHON:-0}"

# ============================================
# 版本解析
# ============================================

resolve_version() {
  local requested="$1"

  if [ "$requested" = "latest" ]; then
    local api_url="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest"
    local latest_tag

    if command -v curl &>/dev/null; then
      latest_tag=$(curl -fsSL "$api_url" 2>/dev/null | grep '"tag_name"' | head -1 | sed 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
    elif command -v wget &>/dev/null; then
      latest_tag=$(wget -qO- "$api_url" 2>/dev/null | grep '"tag_name"' | head -1 | sed 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
    fi

    if [ -n "$latest_tag" ]; then
      echo "${latest_tag#v}"
    else
      echo "1.0.0"
    fi
  else
    echo "$requested"
  fi
}

# ============================================
# [Python 依赖安装] 与 install-python-deps.sh 同步
# ============================================

install_python_deps_inline() {
  local plugin_dir="$1"
  local req_file="$plugin_dir/dashboard/requirements.txt"
  local venv_dir="$plugin_dir/dashboard/.venv"
  local python_deps_ok=""

  if [ ! -f "$req_file" ]; then
    log_warn "未找到 requirements.txt"
    return 1
  fi

  # 策略 1: venv（推荐，不受 PEP 668 影响）
  if python3 -c "import venv" 2>/dev/null; then
    log_info "  尝试: venv（推荐）"
    rm -rf "$venv_dir"
    if python3 -m venv "$venv_dir" 2>/dev/null; then
      local venv_python="$venv_dir/bin/python"
      [ ! -x "$venv_python" ] && [ -x "$venv_dir/Scripts/python.exe" ] && venv_python="$venv_dir/Scripts/python.exe"
      if [ -n "$venv_python" ]; then
        run_silent "$venv_python" -m pip install --upgrade pip -q 2>/dev/null || true
        if run_silent "$venv_python" -m pip install -r "$req_file" -q; then
          python_deps_ok="venv"
        fi
      fi
    fi
  fi

  # 策略 2: pip --user 兜底
  if [ -z "$python_deps_ok" ]; then
    log_info "  尝试: pip --user"
    if run_silent python3 -m pip install -r "$req_file" -q --user; then
      python_deps_ok="pip --user"
    elif run_silent python3 -m pip install -r "$req_file" -q; then
      python_deps_ok="pip"
    elif run_silent pip install -r "$req_file" -q --user; then
      python_deps_ok="pip --user"
    elif run_silent pip3 install -r "$req_file" -q --user; then
      python_deps_ok="pip3 --user"
    fi
  fi

  if [ -n "$python_deps_ok" ]; then
    log_ok "Python 依赖已就绪 ($python_deps_ok)"
    return 0
  else
    log_warn "Python 依赖安装失败"
    print_python_deps_help "$req_file"
    return 1
  fi
}

print_python_deps_help() {
  local req_file="$1"
  echo ""
  echo "========================================"
  echo "请检查以下系统依赖是否已安装："
  echo "========================================"
  echo ""
  
  # 检测系统并给出针对性建议
  if [ -f /etc/debian_version ]; then
    echo "检测到 Debian/Ubuntu 系统，请执行："
    echo ""
    echo "  sudo apt update"
    echo "  sudo apt install python3 python3-pip python3-venv"
    echo ""
  elif [ -f /etc/redhat-release ]; then
    echo "检测到 RedHat/CentOS/Fedora 系统，请执行："
    echo ""
    echo "  sudo dnf install python3 python3-pip"
    echo ""
  elif [[ "$(uname -s)" == "Darwin" ]]; then
    echo "检测到 macOS 系统，请执行："
    echo ""
    echo "  brew install python3"
    echo ""
  else
    echo "请确保已安装："
    echo "  - Python 3"
    echo "  - pip (python3-pip)"
    echo "  - venv 模块 (python3-venv，Linux 通常需要单独安装)"
    echo ""
  fi
  
  echo "========================================"
  echo "安装系统依赖后，重新执行安装："
  echo "========================================"
  echo ""
  echo "  curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh | bash"
  echo ""
  echo "或手动安装 Python 依赖："
  echo ""
  echo "  python3 -m pip install -r $req_file --user"
  echo ""
}

# ============================================
# 主流程
# ============================================

main() {
  # 1. 检测系统
  OS=$(detect_os)
  validate_os "$OS"

  # 2. 解析配置目录
  OPENCLAW_CONFIG_DIR=$(resolve_openclaw_config_dir)
  PLUGIN_PATH="${OPENCLAW_CONFIG_DIR}/extensions/${PLUGIN_ID}"

  log_info "配置目录: $OPENCLAW_CONFIG_DIR"
  log_info "插件路径: $PLUGIN_PATH"
  echo ""

  # 3. 检查 openclaw
  if ! command -v openclaw &>/dev/null; then
    log_error "未找到 openclaw 命令"
    log_info "请先安装: npm install -g openclaw"
    exit 1
  fi

  # 4. 解析版本
  VERSION=$(resolve_version "$DASHBOARD_VERSION")
  if [ "$DASHBOARD_VERSION" = "latest" ] && [ "$VERSION" = "1.0.0" ]; then
    log_warn "无法获取最新版本，使用默认版本 1.0.0"
  fi
  log_info "版本: $VERSION"

  # 5. 构建下载 URL
  if [ -n "$DASHBOARD_RELEASE_URL" ]; then
    DOWNLOAD_URL="$DASHBOARD_RELEASE_URL"
  else
    DOWNLOAD_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}/releases/download/v${VERSION}/${PLUGIN_ID}-v${VERSION}.tgz"
  fi

  log_info "下载地址: $DOWNLOAD_URL"

  # 6. dry-run 模式
  if [ "$DRY_RUN" = "1" ]; then
    echo ""
    log_info "[DRY-RUN] 将执行以下操作:"
    log_info "  - 下载: $DOWNLOAD_URL"
    log_info "  - 安装插件到: $PLUGIN_PATH"
    if [ "$DASHBOARD_SKIP_PYTHON" != "1" ]; then
      log_info "  - 安装 Python 依赖到 venv 或 --user"
    fi
    log_ok "预览完成，未执行实际安装"
    exit 0
  fi

  # 7. 创建临时目录
  TMP_DIR=$(mktemp -d)
  TGZ_FILE="$TMP_DIR/${PLUGIN_ID}.tgz"
  trap 'rm -rf "$TMP_DIR"' EXIT

  # 8. 下载
  log_step "下载预构建包..."
  if ! download_file "$DOWNLOAD_URL" "$TGZ_FILE"; then
    log_error "下载失败"
    log_info ""
    log_info "可能的原因:"
    log_info "  1. 网络连接问题"
    log_info "  2. 版本不存在: v$VERSION"
    log_info "  3. GitHub 访问受限"
    log_info ""
    log_info "尝试:"
    log_info "  1. 检查网络连接"
    log_info "  2. 设置代理: export https_proxy=http://proxy:port"
    log_info "  3. 手动下载: curl -LO $DOWNLOAD_URL"
    log_info "  4. 指定版本: DASHBOARD_VERSION=1.0.0 bash install.sh"
    exit 1
  fi
  log_ok "下载完成"

  # 9. 清理旧安装
  log_step "清理旧版本..."
  if [ -d "$PLUGIN_PATH" ]; then
    log_info "  执行: openclaw plugins uninstall $PLUGIN_ID"
    if run_silent openclaw plugins uninstall "$PLUGIN_ID" --force; then
      log_ok "  已卸载（配置记录）"
    else
      log_warn "  uninstall 失败（可能未注册）"
    fi
    rm -rf "$PLUGIN_PATH"
    log_ok "  已删除旧目录"
  else
    log_ok "  无旧版本"
  fi

  # 10. 安装插件
  log_step "安装插件..."
  log_info "  执行: openclaw plugins install $TGZ_FILE"
  if ! openclaw plugins install "$TGZ_FILE"; then
    log_error "插件安装失败"
    exit 1
  fi
  log_ok "插件已安装"

  # 11. 安装 Python 依赖
  if [ "$DASHBOARD_SKIP_PYTHON" != "1" ] && [ -f "$PLUGIN_PATH/dashboard/requirements.txt" ]; then
    log_step "安装 Python 依赖..."
    install_python_deps_inline "$PLUGIN_PATH" || true
  fi

  # 12. 完成
  echo ""
  log_ok "=== 安装完成 (v$VERSION) ==="
  echo ""
  log_info "执行任意 openclaw 命令（如 openclaw tui）时，Dashboard 会自动启动。"
  log_info "访问地址: http://localhost:38271"
  echo ""
  log_info "若端口被占用，可创建 ~/.openclaw/dashboard/config.json 设置端口:"
  log_info '  {"port": 38271}'
  echo ""
}

main "$@"
