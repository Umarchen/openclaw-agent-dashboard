#!/usr/bin/env bash
#
# 打包项目为可分发的压缩包
# 用法: npm run bundle
#
set -e
cd "$(dirname "$0")/.."
ROOT=$(pwd)

VERSION=$(grep '"version"' "$ROOT/plugin/openclaw.plugin.json" | sed 's/.*"version": *"\([^"]*\)".*/\1/')
OUTPUT="openclaw-agent-dashboard-v$VERSION.tar.gz"

echo "=== 打包分发文件 ==="
echo ""
echo "  版本: $VERSION"
echo "  输出: $OUTPUT"
echo ""

# 临时目录
TMPDIR=$(mktemp -d)
DISTDIR="$TMPDIR/openclaw-agent-dashboard"

mkdir -p "$DISTDIR"

# 复制需要的文件
echo ">>> 复制文件..."
cp -r "$ROOT/frontend" "$DISTDIR/"
cp -r "$ROOT/src" "$DISTDIR/"
cp -r "$ROOT/plugin" "$DISTDIR/"
cp -r "$ROOT/scripts" "$DISTDIR/"
cp "$ROOT/package.json" "$DISTDIR/"
cp "$ROOT/README.md" "$DISTDIR/"

# 清理不需要的文件
echo ">>> 清理 node_modules..."
rm -rf "$DISTDIR/frontend/node_modules"
rm -rf "$DISTDIR/frontend/dist"
rm -rf "$DISTDIR/plugin/frontend-dist"
rm -rf "$DISTDIR/plugin/dashboard"
find "$DISTDIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$DISTDIR" -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true

# 打包
echo ">>> 压缩..."
cd "$TMPDIR"
tar -czf "$ROOT/$OUTPUT" openclaw-agent-dashboard

# 清理临时目录
rm -rf "$TMPDIR"

# 显示结果
echo ""
echo "=== 打包完成 ==="
echo ""
echo "  文件: $OUTPUT"
echo "  大小: $(du -h "$ROOT/$OUTPUT" | cut -f1)"
echo ""
echo "同事使用方式:"
echo "  1. 解压: tar -xzf $OUTPUT"
echo "  2. 进入: cd openclaw-agent-dashboard"
echo "  3. 安装: npm run deploy"
echo ""
