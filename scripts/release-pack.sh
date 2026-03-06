#!/usr/bin/env bash
#
# 发布打包脚本
# 用法: ./scripts/release-pack.sh [--version X.X.X]
#
# 生成预构建 tgz 包，供 CI 或本地发布使用。
# 输出: openclaw-agent-dashboard-v{VERSION}.tgz
#
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)
SCRIPT_DIR="$ROOT/scripts"

# 引入公共库
source "$SCRIPT_DIR/lib/common.sh"

# ============================================
# 参数解析
# ============================================

VERSION_OVERRIDE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION_OVERRIDE="$2"; shift 2 ;;
    --help)
      echo "用法: $0 [--version X.X.X]"
      echo ""
      echo "选项:"
      echo "  --version  指定版本号 (默认从 plugin/openclaw.plugin.json 读取)"
      exit 0
      ;;
    *) echo "未知选项: $1" >&2; exit 1 ;;
  esac
done

# ============================================
# 读取版本
# ============================================

if [ -n "$VERSION_OVERRIDE" ]; then
  VERSION="$VERSION_OVERRIDE"
else
  if [ ! -f "$ROOT/plugin/openclaw.plugin.json" ]; then
    log_error "未找到 plugin/openclaw.plugin.json"
    exit 1
  fi
  VERSION=$(parse_json_version "$ROOT/plugin/openclaw.plugin.json")
fi

if [ -z "$VERSION" ]; then
  log_error "无法解析版本号"
  exit 1
fi

OUTPUT_FILE="$ROOT/openclaw-agent-dashboard-v${VERSION}.tgz"

log_info "版本: $VERSION"
log_info "输出: $OUTPUT_FILE"

# ============================================
# 确保已构建
# ============================================

if [ ! -d "$ROOT/plugin/frontend-dist" ] || [ ! -f "$ROOT/plugin/dashboard/main.py" ]; then
  log_info "构建插件..."
  npm run pack
fi

# ============================================
# 生成 tgz
# ============================================

log_info "生成 tgz 包..."

cd "$ROOT/plugin"

# 清理旧的 tgz
rm -f openclaw-agent-dashboard-*.tgz

# npm pack
npm pack

# 查找生成的文件
TGZ_FILE=$(ls openclaw-agent-dashboard-*.tgz 2>/dev/null | head -1)

if [ -z "$TGZ_FILE" ]; then
  log_error "npm pack 未生成 tgz 文件"
  exit 1
fi

# 移动并重命名
mv "$TGZ_FILE" "$OUTPUT_FILE"

# ============================================
# 完成
# ============================================

log_ok "已生成: $OUTPUT_FILE"

# 显示文件信息
ls -lh "$OUTPUT_FILE" 2>/dev/null || true

# 显示 SHA256
if command -v sha256sum &>/dev/null; then
  echo "SHA256: $(sha256sum "$OUTPUT_FILE" | cut -d' ' -f1)"
elif command -v shasum &>/dev/null; then
  echo "SHA256: $(shasum -a 256 "$OUTPUT_FILE" | cut -d' ' -f1)"
fi
