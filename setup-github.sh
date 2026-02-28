#!/bin/bash
# 在 GitHub 创建远端仓库并推送
# 使用前请先运行: gh auth login

set -e
cd "$(dirname "$0")"

echo "正在创建 GitHub 仓库并推送..."
gh repo create openclaw-agent-dashboard --public --source=. --remote=origin --push

echo ""
echo "✅ 完成！仓库已创建并推送至: https://github.com/$(gh api user -q .login)/openclaw-agent-dashboard"
