# OpenClaw Agent Dashboard 发布操作手册

> 面向小白的发布流程说明，包含操作步骤和原理讲解。

---

## 一、整体流程概览

```
你写代码 → 推送到 GitHub → 打 tag → 自动构建 → 别人可以安装
```

| 阶段 | 你做什么 | 系统做什么 |
|------|----------|------------|
| 1. 开发 | 修改代码 | - |
| 2. 提交 | `git add`、`git commit` | 记录到本地 |
| 3. 推送 | `git push origin main` | 代码同步到 GitHub |
| 4. 打 tag | `git tag v1.0.0` | 给当前代码打个「版本号」 |
| 5. 发布 | `git push origin v1.0.0` | **触发自动构建**，生成安装包 |
| 6. 完成 | 无 | 别人可以一键安装 |

---

## 二、核心概念

### 2.1 什么是 tag？

tag 就像给某次提交贴一个「版本标签」，例如 `v1.0.0`。

- **作用**：标记「这是 1.0.0 正式版」
- **和分支的区别**：分支会继续往前走，tag 一般固定在那次提交上
- **命名习惯**：`v` + 版本号，如 `v1.0.0`、`v1.0.1`、`v2.0.0`

### 2.2 什么是 GitHub Actions？

GitHub 提供的**自动化流水线**，可以在你推送代码或 tag 时自动执行脚本。

- **不是**：GitHub 自带的通用测试
- **是**：项目里自己配置的「发布流水线」
- **配置文件**：`.github/workflows/release.yml`

### 2.3 为什么推送 tag 会触发构建？

在 `release.yml` 里写了：

```yaml
on:
  push:
    tags:
      - 'v*'   # 只要推送的 tag 以 v 开头，就触发
```

所以：`git push origin v1.0.0` → GitHub 检测到 tag 推送 → 自动跑 workflow。

### 2.4 构建完成后会发生什么？

1. 在 frontend 目录安装依赖、构建前端
2. 打包 backend 和 frontend，生成 `.tgz` 安装包
3. 在 GitHub 上创建 **Release**
4. 把 `.tgz` 作为附件上传到 Release

别人就可以通过 Release 下载安装包，或使用一键安装脚本。

---

## 三、常用操作

### 3.1 首次发布（第一次发 v1.0.0）

```bash
# 1. 确保代码已提交并推送到 main
git add .
git commit -m "你的提交说明"
git push origin main

# 2. 打 tag
git tag v1.0.0

# 3. 推送 tag，触发构建
git push origin v1.0.0
```

### 3.2 发布新版本（如 v1.0.1）

```bash
# 1. 代码已推送到 main 后
git tag v1.0.1
git push origin v1.0.1
```

### 3.3 重新触发构建（tag 已存在，想再跑一次）

有时 workflow 失败，修好代码后想用同一个版本号再跑一次：

```bash
# 删除本地 tag
git tag -d v1.0.0

# 在最新提交上重新打 tag
git tag v1.0.0

# 删除远程 tag
git push origin :refs/tags/v1.0.0

# 推送新 tag，触发构建
git push origin v1.0.0
```

### 3.4 手动触发构建（不推 tag）

在 GitHub 网页上：

1. 打开 https://github.com/Umarchen/openclaw-agent-dashboard/actions
2. 左侧选择 **Release** workflow
3. 点击 **Run workflow** → **Run workflow**

---

## 四、重要说明

### 4.1 推送 main 不会触发 Release

- `git push origin main`：只同步代码，**不会**触发 Release workflow
- `git push origin v1.0.0`：推送 tag，**会**触发 Release workflow

### 4.2 tag 指向哪次提交，就用哪次提交的代码构建

如果 tag 是之前打的，后来改了 `.github/workflows/release.yml` 但没重新打 tag，workflow 用的还是**旧配置**。需要把 tag 挪到最新提交上（见 3.3）。

### 4.3 别人怎么安装

| 方式 | 命令 |
|------|------|
| 一键安装 | `curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh \| bash` |
| 源码安装 | `git clone ... && npm run deploy` |
| 手动下载 | 从 [Releases](https://github.com/Umarchen/openclaw-agent-dashboard/releases) 下载 tgz，`openclaw plugins install xxx.tgz` |

---

## 五、故障排查

### 5.1 构建失败：Dependencies lock file is not found

**原因**：`setup-node` 的 `cache: 'npm'` 需要在根目录有 `package-lock.json`，本项目锁文件在 `frontend/` 下。

**解决**：已在 `release.yml` 中移除 `cache: 'npm'`，无需再改。

### 5.2 推送 tag 后没看到 workflow 运行

- 检查：https://github.com/Umarchen/openclaw-agent-dashboard/actions
- 确认 tag 已推送成功：`git ls-remote --tags origin`

### 5.3 Release 里没有 tgz 附件

说明 workflow 某一步失败了。在 Actions 里点进那次运行，查看失败步骤的日志。

---

## 六、快速参考

| 目标 | 命令 |
|------|------|
| 发布 v1.0.0 | `git tag v1.0.0` → `git push origin v1.0.0` |
| 发布 v1.0.1 | `git tag v1.0.1` → `git push origin v1.0.1` |
| 重新触发 v1.0.0 构建 | 见 3.3 |
| 查看构建状态 | https://github.com/Umarchen/openclaw-agent-dashboard/actions |
| 查看 Release | https://github.com/Umarchen/openclaw-agent-dashboard/releases |
