# 维护者全量发布流程

从「新增功能」到 **npm 发布**、**Git 推送与 GitHub Release**、**本机与其他环境更新插件** 的完整操作清单（与当前仓库结构一致：`plugin/` 为 npm 发布根、`npm run publish:npm`、推送 `v*` 标签触发 Release）。

---

## 一、开发阶段

1. 在仓库内修改代码（`frontend/`、`src/backend/`、`plugin/index.js` 等）。
2. 本地验证：
   ```bash
   npm run pack
   ```
   必要时使用 `npm run deploy` 装到本机 OpenClaw 做联调，并重启 Gateway 验证行为。

---

## 二、发版前：统一版本号

新版本号在三处保持一致（示例 `1.0.18`）：

| 文件 | 字段 |
|------|------|
| `plugin/package.json` | `"version"` |
| `plugin/openclaw.plugin.json` | `"version"` |
| 根目录 `package.json` | `"version"`（与上保持一致，便于对照） |

> GitHub Actions 中 Release 使用的版本来自 **`plugin/openclaw.plugin.json`**。Git 标签建议使用 **`v` + 该版本号**（如 `v1.0.18`），与 CI 一致。

---

## 三、打包自检（发布前必跑）

```bash
cd /path/to/openclaw-agent-dashboard
npm run pack
```

确认无报错。`plugin/dashboard`、`plugin/frontend-dist`、`plugin/scripts` 由 `build-plugin.js` 生成；`plugin/scripts/` 已在 `.gitignore` 中，无需提交。

---

## 四、发布到 npm

用户执行 `openclaw plugins install openclaw-agent-dashboard@…` 时，会从 **npm 公共仓库** 拉取已发布的包。

```bash
npm login    # 若尚未登录
npm run publish:npm
```

等价于：先执行 `pack`，再 `npm publish --prefix plugin`。

发布后自检：

```bash
npm view openclaw-agent-dashboard version
```

---

## 五、Git：推送代码 + 打标签（触发 GitHub Release）

```bash
git add -A
git commit -m "feat: 功能说明（v1.0.18）"
git push origin main

git tag -a v1.0.18 -m "Release 1.0.18"
git push origin v1.0.18
```

- **`main`**：保存源码与文档。
- **`v1.0.18`**：推送后触发 `.github/workflows/release.yml`，构建并上传 **GitHub Release** 及 `openclaw-agent-dashboard-v*.tgz`（以仓库内 workflow 为准）。

在 GitHub **Actions** 中确认 Release 工作流成功结束。

---

## 六、本机 / 服务器：更新已安装的插件

插件已通过 **npm** 安装到 `~/.openclaw/extensions/openclaw-agent-dashboard` 时，推荐：

```bash
openclaw plugins update openclaw-agent-dashboard
# 若 CLI 支持更新全部 npm 插件：
# openclaw plugins update --all
```

然后重启 Gateway：

```bash
openclaw gateway restart
```

若 **`requirements.txt` 有变更**，在扩展目录下再执行一次 Python 依赖安装：

```bash
PLUGIN="$HOME/.openclaw/extensions/openclaw-agent-dashboard"
node "$PLUGIN/scripts/install-python-deps.js" "$PLUGIN"
```

**Windows（PowerShell）**：

```powershell
$plugin = "$env:USERPROFILE\.openclaw\extensions\openclaw-agent-dashboard"
node "$plugin\scripts\install-python-deps.js" $plugin
```

> **不要用** `openclaw plugins install …@latest` **代替**「升级」：已安装时可能被判定为全新安装且目录已存在而失败。升级以 `plugins update` 为准；若 CLI 不支持，再查阅 `openclaw plugins --help` 或 README「迁移 / 升级」章节。

---

## 七、一页顺序（速查）

```
改代码
→ 三处版本号 +1
→ npm run pack
→ npm run publish:npm
→ git commit & push main
→ git tag vX.Y.Z && git push origin vX.Y.Z
→ 确认 GitHub Actions Release 成功
→ 本机：plugins update + gateway restart +（必要时）install-python-deps
```

---

## 八、其他环境下的安装与升级

- 在 **npm 已发布新版本** 之后，在其他机器上执行：
  ```bash
  openclaw plugins update openclaw-agent-dashboard
  ```
  或指定版本：
  ```bash
  openclaw plugins install openclaw-agent-dashboard@1.0.18
  ```
  然后重启 Gateway；依赖有变时同样执行 `install-python-deps.js`。
- **从 path 安装迁到 npm**、或出现 `plugin already exists` 时，见仓库根目录 **README**「从 path / 旧版安装迁移到 npm」。

---

## 九、相关文档

- 用户安装与迁移：**[README.md](../README.md)**
- 历史发布说明：**[release-guide.md](./release-guide.md)**（若与本文冲突，以本文与当前 `package.json` / workflow 为准）
