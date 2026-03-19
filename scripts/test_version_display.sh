#!/bin/bash
# 版本号显示功能 - 快速测试脚本

set -e

PROJECT_DIR="/home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard"
cd "$PROJECT_DIR"

echo "=================================="
echo "版本号显示功能 - 快速测试"
echo "=================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试函数
test_passed() {
    echo -e "${GREEN}✅ 通过${NC}: $1"
}

test_failed() {
    echo -e "${RED}❌ 失败${NC}: $1"
}

test_info() {
    echo -e "${YELLOW}ℹ️  信息${NC}: $1"
}

echo "1. 检查文件是否存在"
echo "----------------------------------"

FILES=(
    "src/backend/data/version_info_reader.py"
    "src/backend/api/version.py"
    "frontend/src/components/common/VersionDisplay.vue"
    ".staging/traceability_manifest.json"
    ".staging/VERSION_DISPLAY_implementation_summary.md"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        test_passed "文件存在: $file"
    else
        test_failed "文件缺失: $file"
    fi
done

echo ""
echo "2. 检查 Python 语法"
echo "----------------------------------"

python3 -m py_compile src/backend/data/version_info_reader.py && \
    test_passed "version_info_reader.py 语法正确" || \
    test_failed "version_info_reader.py 语法错误"

python3 -m py_compile src/backend/api/version.py && \
    test_passed "version.py 语法正确" || \
    test_failed "version.py 语法错误"

echo ""
echo "3. 检查 API 路由注册"
echo "----------------------------------"

if grep -q "from api import.*version" src/backend/main.py; then
    test_passed "main.py 已导入 version 模块"
else
    test_failed "main.py 未导入 version 模块"
fi

if grep -q "app.include_router(version.router" src/backend/main.py; then
    test_passed "main.py 已注册 version 路由"
else
    test_failed "main.py 未注册 version 路由"
fi

echo ""
echo "4. 检查前端组件集成"
echo "----------------------------------"

if grep -q "import VersionDisplay from './components/common/VersionDisplay.vue'" frontend/src/App.vue; then
    test_passed "App.vue 已导入 VersionDisplay 组件"
else
    test_failed "App.vue 未导入 VersionDisplay 组件"
fi

if grep -q "<VersionDisplay />" frontend/src/App.vue; then
    test_passed "App.vue 模板包含 VersionDisplay 标签"
else
    test_failed "App.vue 模板缺少 VersionDisplay 标签"
fi

echo ""
echo "5. 检查版本号数据源"
echo "----------------------------------"

if [ -f "package.json" ]; then
    VERSION=$(python3 -c "import json; print(json.load(open('package.json')).get('version', 'unknown'))")
    test_info "当前版本号: $VERSION"
    test_passed "package.json 存在且可解析"
else
    test_failed "package.json 不存在"
fi

echo ""
echo "6. 检查组件目录结构"
echo "----------------------------------"

if [ -d "frontend/src/components/common" ]; then
    test_passed "common 目录已创建"
else
    test_failed "common 目录缺失"
fi

echo ""
echo "=================================="
echo "测试完成"
echo "=================================="
echo ""
echo "后续步骤："
echo "1. 启动服务: npm start"
echo "2. 测试 API: curl http://localhost:8000/api/version"
echo "3. 打开浏览器访问: http://localhost:8000"
echo "4. 检查右下角是否显示版本号"
echo ""
