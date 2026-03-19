# 发布新 Latest 版本指南

> 修改工程后，按本文步骤推送新 release，该版本会自动成为 GitHub 上的 **Latest**，用户一键安装即会装到该版本。

---

## 一、发布前必读

### 1.1 版本号从哪里来？

Release 的 **tag 和安装包版本** 由仓库里**两个文件**的 `version` 字段决定（不是由你打的 git tag 名决定）：

| 文件 | 作用 |
|------|------|
| `plugin/openclaw.plugin.json` | 插件元数据，**Release 流程会读这里的 version** 来创建 tag 和 tgz 包名。 |
| `plugin/package.json` | Node 包配置，需与上面保持一致，否则包版本和展示会错乱。 |

**重要**：先改这两个文件里的版本号并提交，再打同版本的 git tag。否则会出现「tag 是 v1.0.2、Release 却是 v1.0.0」的情况。

### 1.2 流程概览

```
改代码 → 改两处 version → 提交并 push main → 打 tag 并 push tag → 自动构建并设为 Latest
```

---

## 二、操作步骤（以发布 v1.0.2 为例）

### 步骤 1：在 main 上并拉取最新

```bash
git checkout main
git pull origin main
```

### 步骤 2：修改两处版本号

将 **`plugin/openclaw.plugin.json`** 和 **`plugin/package.json`** 中的 `"version"` 改为新版本，例如 `"1.0.2"`。

- 编辑 `plugin/openclaw.plugin.json`，找到 `"version": "x.x.x"` 改为 `"1.0.2"`。
- 编辑 `plugin/package.json`，同样把 `"version"` 改为 `"1.0.2"`。

或用一条命令同时改（把下面的 `1.0.1` 换成你当前版本，`1.0.2` 换成目标版本）：

```bash
sed -i 's/"version": "1.0.1"/"version": "1.0.2"/' plugin/openclaw.plugin.json plugin/package.json
```

### 步骤 3：提交并推送到 main

```bash
git add plugin/openclaw.plugin.json plugin/package.json
git commit -m "chore: bump version to 1.0.2"
git push origin main
```

> 注意：提交信息用 `-m "..."`，不要写成 `git commit "..."`（会报错 pathspec）。

### 步骤 4：打 tag 并推送（触发 Release）

```bash
git tag v1.0.2
git push origin v1.0.2
```

推送 tag 后，GitHub Actions 会自动：

1. 用该 tag 对应的 commit 构建
2. 读取 `plugin/openclaw.plugin.json` 的 version，创建 Release 和 tgz
3. 将本次 Release 设为 **Latest**

### 步骤 5：验证

- **Actions**：打开 [Actions](https://github.com/Umarchen/openclaw-agent-dashboard/actions)，确认 Release workflow 成功。
- **Releases**：打开 [Releases](https://github.com/Umarchen/openclaw-agent-dashboard/releases)，确认出现 **v1.0.2**，且为 **Latest release**。

---

## 三、用户如何安装

默认一键安装即安装 **Latest**（即你刚发布的版本）：

```bash
curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh | bash
```

安装指定版本：

```bash
DASHBOARD_VERSION=1.0.2 curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh | bash
```

---

## 四、快速命令清单（复制用）

发布新版本时，把 `1.0.2` 换成你的目标版本号即可：

```bash
# 1. 同步 main
git checkout main && git pull origin main

# 2. 改版本号（两处文件，或手动编辑）
# 编辑 plugin/openclaw.plugin.json 和 plugin/package.json 的 "version"

# 3. 提交并推送
git add plugin/openclaw.plugin.json plugin/package.json
git commit -m "chore: bump version to 1.0.2"
git push origin main

# 4. 打 tag 并推送，触发 Release
git tag v1.0.2
git push origin v1.0.2
```

---

## 五、常见问题

### 为什么 GitHub 上有的 release 没有「Set as latest」按钮？

若该 release 被标成了 **Pre-release**，GitHub 不允许把它设为 Latest，所以只会显示 Pre-release 相关选项。当前流程发布的是正式版并自动设为 Latest，不会出现这种情况。

### 推送 main 或 tag 报错：Could not read from remote repository / Connection closed

多为网络或权限问题：检查本机能否访问 GitHub、SSH 密钥或 token 是否有效、仓库是否存在且有写权限。

### 想重新用同一版本号再发一次（例如 workflow 之前失败了）

需要**先删本地 tag、再删远程 tag**，在要发布的 commit（例如当前 main）上重新打 tag 并推送。否则你 push 的仍是旧 tag 指向的旧 commit，Release 会错。完整步骤见下方 [六、Git tag 说明](#六git-tag-说明)。也可参见 `docs/release-operations-manual.md` 的「重新触发构建」一节。

---

## 六、Git tag 说明

发布流程依赖 **git tag**。了解其行为可以避免「改了版本号、删了远程 tag 再 push，结果 Release 还是错的」。

### 6.1 tag 是什么？

- 每个 **commit** 有一个唯一的 SHA-1（如 `f7db4d1...`）。
- **tag** 是给某个 commit 起的**固定名字**（如 `v1.0.1`），在 Git 里就是一个「名字 → 该 commit」的引用。
- 可以理解为：**tag = 钉在某个 commit 上的书签**，不会跟着你后续的新提交自动移动。

### 6.2 两种 tag

| 类型 | 命令 | 说明 |
|------|------|------|
| **轻量 tag** | `git tag v1.0.1` | 只记录「名字 → 当前 commit」，常用。 |
| **附注 tag** | `git tag -a v1.0.1 -m "Release 1.0.1"` | 会生成带作者、时间、说明的 tag 对象，再让名字指向它。 |

本项目的发布用轻量 tag 即可。

### 6.3 常用操作实际做了什么？

| 操作 | 实际效果 |
|------|----------|
| `git tag v1.0.1` | 在当前 HEAD 指向的 commit 上，创建引用 `refs/tags/v1.0.1`，不提交、不改文件。 |
| `git tag -d v1.0.1` | 删除**本地**的 `v1.0.1` 引用，commit 仍在。 |
| `git push origin v1.0.1` | 把本地 `v1.0.1` 指向的 commit 的「名字」同步到远程。 |
| `git push origin --delete v1.0.1` | 删除**远程**的 `v1.0.1` 引用，不删 commit。 |

### 6.4 为什么 tag「不会自己更新」？

Tag 的设计就是**给历史某一点打标签**（如「这是 1.0.1 正式版」），所以不会随 `git commit` 自动挪到新 commit。要换指向，只能：删掉旧 tag（本地 + 远程），在**新的** commit 上重新打 tag 再 push。

### 6.5 把已有版本号重新发布到当前 main（完整步骤）

例如 v1.0.1 已存在但指向了旧 commit，想让它指向当前 main 并重新跑 Release：

```bash
# 1. 确保在最新 main（已改好 version 的提交）
git checkout main
git pull origin main

# 2. 删本地 tag（否则会一直指向旧 commit）
git tag -d v1.0.1

# 3. 在当前 commit 上重新打 tag
git tag v1.0.1

# 4. 删远程 tag（若存在）
git push origin --delete v1.0.1

# 5. 推送新 tag，触发 Release workflow
git push origin v1.0.1
```

之后到 Actions / Releases 确认 v1.0.1 的 Release 和 tgz 是否正常。
