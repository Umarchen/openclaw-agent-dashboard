#!/usr/bin/env bash
#
# Python 依赖安装脚本
# 用法: ./install-python-deps.sh <plugin_dir> [options]
#
# 选项:
#   --verbose     显示详细输出
#   --venv-only   仅使用 venv，不回退 pip
#   --skip-create 跳过创建 venv (已存在)
#
# 环境变量:
#   VERBOSE=1     显示详细输出
#
set -euo pipefail

# ============================================
# 参数解析
# ============================================

if [ $# -lt 1 ]; then
  echo "用法: $0 <plugin_dir> [--verbose] [--venv-only] [--skip-create]"
  echo ""
  echo "参数:"
  echo "  plugin_dir    插件安装目录 (必须)"
  echo ""
  echo "选项:"
  echo "  --verbose     显示详细输出"
  echo "  --venv-only   仅使用 venv，不回退 pip"
  echo "  --skip-create 跳过创建 venv (已存在)"
  exit 1
fi

PLUGIN_DIR="$1"
shift

# 解析选项
VERBOSE="${VERBOSE:-0}"
VENV_ONLY=0
SKIP_CREATE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --verbose) VERBOSE=1 ;;
    --venv-only) VENV_ONLY=1 ;;
    --skip-create) SKIP_CREATE=1 ;;
    *) echo "未知选项: $1" >&2; exit 1 ;;
  esac
  shift
done

# ============================================
# 日志辅助函数
# ============================================

log_info()  { echo "$1"; }
log_ok()    { echo "✓ $1"; }
log_warn()  { echo "⚠ $1"; }
log_error() { echo "❌ $1" >&2; }

run_silent() {
  if [ "$VERBOSE" = "1" ]; then
    "$@"
  else
    "$@" 2>/dev/null
  fi
}

# ============================================
# 系统依赖检测
# ============================================

check_python() {
  if ! command -v python3 &>/dev/null; then
    log_error "未找到 python3 命令"
    echo ""
    echo "请先安装 Python 3:"
    echo "  Debian/Ubuntu: sudo apt install python3"
    echo "  macOS:         brew install python3"
    echo "  Windows:       从 https://www.python.org 下载安装"
    return 1
  fi
  return 0
}

check_venv_module() {
  if ! python3 -c "import venv" 2>/dev/null; then
    return 1
  fi
  return 0
}

check_pip_module() {
  if python3 -m pip --version &>/dev/null; then
    return 0
  fi
  if command -v pip3 &>/dev/null; then
    return 0
  fi
  if command -v pip &>/dev/null; then
    return 0
  fi
  return 1
}

# ============================================
# 验证
# ============================================

REQ_FILE="$PLUGIN_DIR/dashboard/requirements.txt"
VENV_DIR="$PLUGIN_DIR/dashboard/.venv"

if [ ! -f "$REQ_FILE" ]; then
  log_error "未找到 requirements.txt: $REQ_FILE"
  exit 1
fi

# ============================================
# 安装 Python 依赖
# ============================================

PYTHON_DEPS_OK=""

# 策略 1: venv（推荐，不受 PEP 668 影响，跨平台一致）
if check_venv_module; then
  log_info "  尝试: venv（推荐，不受 PEP 668 影响）"

  VENV_PYTHON=""
  # 检查现有 venv
  [ -x "$VENV_DIR/bin/python" ] && VENV_PYTHON="$VENV_DIR/bin/python"
  [ -z "$VENV_PYTHON" ] && [ -x "$VENV_DIR/Scripts/python.exe" ] && VENV_PYTHON="$VENV_DIR/Scripts/python.exe"

  # 创建新 venv
  if [ -z "$VENV_PYTHON" ] && [ "$SKIP_CREATE" != "1" ]; then
    rm -rf "$VENV_DIR"
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
      log_warn "  venv 创建失败，尝试其他方式..."
    else
      [ -x "$VENV_DIR/bin/python" ] && VENV_PYTHON="$VENV_DIR/bin/python"
      [ -z "$VENV_PYTHON" ] && [ -x "$VENV_DIR/Scripts/python.exe" ] && VENV_PYTHON="$VENV_DIR/Scripts/python.exe"
    fi
  fi

  # 安装依赖
  if [ -n "$VENV_PYTHON" ]; then
    if run_silent "$VENV_PYTHON" -m pip install --upgrade pip -q 2>/dev/null; then
      if run_silent "$VENV_PYTHON" -m pip install -r "$REQ_FILE" -q; then
        PYTHON_DEPS_OK="venv"
      fi
    fi
  fi
fi

# 策略 2: pip --user 兜底（Debian 12/Ubuntu 23.04+ 等 PEP 668 环境）
if [ -z "$PYTHON_DEPS_OK" ] && [ "$VENV_ONLY" != "1" ]; then
  log_info "  尝试: pip --user（PEP 668 兜底）"

  if run_silent python3 -m pip install -r "$REQ_FILE" -q --user; then
    PYTHON_DEPS_OK="pip --user"
  elif run_silent python3 -m pip install -r "$REQ_FILE" -q; then
    PYTHON_DEPS_OK="pip"
  elif run_silent pip install -r "$REQ_FILE" -q --user; then
    PYTHON_DEPS_OK="pip --user"
  elif run_silent pip3 install -r "$REQ_FILE" -q --user; then
    PYTHON_DEPS_OK="pip3 --user"
  fi
fi

# ============================================
# 结果
# ============================================

if [ -n "$PYTHON_DEPS_OK" ]; then
  log_ok "Python 依赖已就绪 ($PYTHON_DEPS_OK)"
  exit 0
else
  log_error "Python 依赖安装失败"
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
  echo "安装系统依赖后，重新执行："
  echo "========================================"
  echo ""
  echo "  npm run deploy"
  echo ""
  echo "或手动安装 Python 依赖："
  echo ""
  echo "  python3 -m pip install -r $REQ_FILE --user"
  echo ""
  echo "========================================"
  echo "调试模式："
  echo "========================================"
  echo ""
  echo "  VERBOSE=1 npm run deploy"
  echo ""
  
  exit 1
fi
