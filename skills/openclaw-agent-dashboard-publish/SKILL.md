---
name: openclaw-agent-dashboard-publish
description: Publishes and updates the openclaw-agent-dashboard OpenClaw plugin via npm pack/publish, git tags, GitHub Release, and post-install plugin update. Use when releasing the dashboard plugin, bumping its version, running npm publish, pushing v* tags, or guiding users through plugins update and gateway restart after requirements changes.
---

# openclaw-agent-dashboard 发布与更新

维护者从改代码到 **npm**、**Git**、**GitHub Release** 及环境内升级插件的规范流程。详细原文见仓库 `docs/Openclaw-Agent-Dashboard发布与更新.md`。

## 仓库事实（必读）

- npm 发布根目录为 **`plugin/`**；发布命令为根目录 **`npm run publish:npm`**（内部会先 pack，再 `npm publish --prefix plugin`）。
- **版本号三处一致**：`plugin/package.json` 的 `version`、`plugin/openclaw.plugin.json` 的 `version`、**根目录** `package.json` 的 `version`。
- GitHub Actions Release 取版本以 **`plugin/openclaw.plugin.json`** 为准；Git 标签建议 **`v` + 该版本号**（如 `v1.0.18`）。
- `plugin/dashboard`、`plugin/frontend-dist`、`plugin/scripts` 由打包生成；**`plugin/scripts/` 在 `.gitignore` 中，不要提交**。

## 开发自测

```bash
npm run pack
```

联调可用 `npm run deploy` 装到本机 OpenClaw，改完后 **重启 Gateway**。

## 发版前 checklist

1. 三处 `version` 已 bump 且一致。
2. 在仓库根执行 **`npm run pack`**，无报错。
3. **`npm login`**（若需要）后执行 **`npm run publish:npm`**。
4. 发布后抽检：`npm view openclaw-agent-dashboard version`（或指定版本号）。

## Git 与 Release

> ⚠️ 每次新 session 推 git 前需要先启动 ssh-agent 并加载 key：
> ```bash
> eval $(ssh-agent -s) && ssh-add ~/.ssh/id_ed25519
> ```

```bash
git add -A
git commit -m "feat: 说明（vX.Y.Z）"
git push origin main

git tag -a vX.Y.Z -m "Release X.Y.Z"
git push origin vX.Y.Z
```

在 GitHub **Actions** 确认 `release` 工作流成功。

## 已安装环境升级插件

通过 npm 装在 `~/.openclaw/extensions/openclaw-agent-dashboard` 时：

```bash
openclaw plugins update openclaw-agent-dashboard
openclaw gateway restart
```

若 **`requirements.txt` 有变更**，在扩展目录执行 Python 依赖安装：

```bash
PLUGIN="$HOME/.openclaw/extensions/openclaw-agent-dashboard"
node "$PLUGIN/scripts/install-python-deps.js" "$PLUGIN"
```

**Windows（PowerShell）**：

```powershell
$plugin = "$env:USERPROFILE\.openclaw\extensions\openclaw-agent-dashboard"
node "$plugin\scripts\install-python-deps.js" $plugin
```

**不要用** `openclaw plugins install …@latest` **当作升级**：已安装时可能因目录已存在失败；升级以 **`plugins update`** 为准。

## 一页顺序（速查）

```
改代码 → 三处 version +1 → npm run pack → npm run publish:npm
→ git push main → git tag vX.Y.Z && git push origin vX.Y.Z
→ 确认 Actions Release → 各环境 plugins update + gateway restart +（必要时）install-python-deps
```

## 延伸阅读

- 完整步骤与表格：仓库内 `docs/Openclaw-Agent-Dashboard发布与更新.md`（相对本文件：`../../docs/Openclaw-Agent-Dashboard发布与更新.md`）
- 用户安装与迁移：仓库根 `README.md`（`../../README.md`）
