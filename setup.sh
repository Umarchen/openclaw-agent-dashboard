#!/bin/bash

# OpenClaw Agent Dashboard 启动脚本

# 若存在 conda，激活以便使用 pip
if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh" 2>/dev/null && conda activate base 2>/dev/null
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh" 2>/dev/null && conda activate base 2>/dev/null
fi

echo "========================================="
echo "  OpenClow Agent Dashboard"
echo "========================================="

# 检查 Python 环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python3"
    exit 1
fi

# 检查 Node.js 环境
if ! command -v npm &> /dev/null; then
    echo "❌ 错误: 未找到 Node.js/npm"
    exit 1
fi

# 进入项目目录
cd "$(dirname "$0")"

echo ""
echo "📦 安装后端依赖..."
cd src/backend
# 兼容 pip / pip3 / conda / python3 -m pip
if command -v pip &>/dev/null; then
    pip install -q -r requirements.txt
elif command -v pip3 &>/dev/null; then
    pip3 install -q -r requirements.txt
else
    python3 -m pip install -q -r requirements.txt
fi
if [ $? -ne 0 ]; then
    echo "❌ 安装后端依赖失败。请确保已安装 pip: sudo apt install python3-pip 或 source ~/miniconda3/etc/profile.d/conda.sh && conda activate"
    exit 1
fi

echo ""
echo "📦 安装前端依赖..."
cd ../../frontend
npm install --silent
if [ $? -ne 0 ]; then
    echo "❌ 安装前端依赖失败"
    exit 1
fi

echo ""
echo "✅ 依赖安装完成"
echo ""
echo "========================================="
echo "  启动说明"
echo "========================================="
echo ""
echo "后端启动："
echo "  cd src/backend && uvicorn main:app --reload --port 8000"
echo ""
echo "前端启动："
echo "  cd frontend && npm run dev"
echo ""
echo "访问地址："
echo "  http://localhost:5173"
echo ""
echo "API 文档："
echo "  http://localhost:8000/docs"
echo ""
