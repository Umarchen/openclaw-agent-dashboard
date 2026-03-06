# 发布与使用指南

> 本文档说明如何提交更改、发布新版本以及使用一键安装功能。

---

## 一、提交当前更改

### 1.1 查看待提交文件

```bash
git status --short
```

### 1.2 提交更改

```bash
# 方式一：提交所有更改
git add .
git commit -m "feat: 添加一键安装支持 + GitHub Actions 发布流程

- 新增 scripts/install.sh 一键安装入口
- 新增 scripts/install-python-deps.sh Python 依赖安装
- 新增 scripts/release-pack.sh 发布打包
- 新增 .github/workflows/release.yml CI/CD
- 优化 plugin/index.js 优先使用 venv Python
- 重构 scripts/install-plugin.sh 支持 VERBOSE/DRY_RUN
- 更新 README.md 添加一键安装说明"

git push origin main
```

```bash
# 方式二：选择性提交
git add .github/workflows/release.yml \
        scripts/install.sh \
        scripts/install-python-deps.sh \
        scripts/release-pack.sh \
        scripts/install-plugin.sh \
        plugin/index.js \
        README.md \
        docs/

git commit -m "feat: 添加一键安装支持 + GitHub Actions 发布流程"
git push origin main
```

---

## 二、发布新版本

### 2.1 更新版本号

编辑 `plugin/openclaw.plugin.json`，修改 version 字段：

```json
{
  "id": "openclaw-agent-dashboard",
  "name": "OpenClaw Agent Dashboard",
  "version": "1.0.1",  // 修改此处
  ...
}
```

### 2.2 提交并打 Tag

```bash
# 提交版本更新
git add plugin/openclaw.plugin.json
git commit -m "release: v1.0.1"
git push origin main

# 创建 tag 并推送（触发 GitHub Actions 自动构建发布）
git tag v1.0.1
git push origin v1.0.1
```

### 2.3 GitHub Actions 自动流程

推送 tag 后，GitHub Actions 会自动执行：

| 步骤 | 说明 |
|------|------|
| 1 | Checkout 代码 |
| 2 | 安装 Node.js 依赖 |
| 3 | 构建前端 (`npm run pack`) |
| 4 | 生成 tgz 包 (`release-pack.sh`) |
| 5 | 创建 GitHub Release |
| 6 | 上传 tgz 到 Release Assets |

### 2.4 验证发布

1. 访问 GitHub Releases 页面：`https://github.com/Umarchen/openclaw-agent-dashboard/releases`
2. 确认新版本已创建
3. 确认 tgz 文件已上传

---

## 三、本地测试

### 3.1 构建并打包

```bash
# 构建前端 + 打包插件
npm run pack

# 生成发布 tgz
bash scripts/release-pack.sh
```

### 3.2 测试一键安装脚本

```bash
# 预览模式（不执行实际安装）
DRY_RUN=1 bash scripts/install.sh

# 使用本地 tgz 测试安装
DASHBOARD_RELEASE_URL="file://$(pwd)/openclaw-agent-dashboard-v1.0.0.tgz" \
  bash scripts/install.sh

# 跳过 Python 依赖安装（快速测试）
DASHBOARD_RELEASE_URL="file://$(pwd)/openclaw-agent-dashboard-v1.0.0.tgz" \
  DASHBOARD_SKIP_PYTHON=1 \
  bash scripts/install.sh
```

### 3.3 测试源码安装脚本

```bash
# 预览模式
DRY_RUN=1 bash scripts/install-plugin.sh

# 详细输出模式
VERBOSE=1 bash scripts/install-plugin.sh
```

### 3.4 验证安装结果

```bash
# 检查插件目录
ls -la ~/.openclaw/extensions/openclaw-agent-dashboard/

# 检查插件配置
openclaw plugins list
```

---

## 四、清理构建产物

```bash
# 删除本地测试生成的 tgz（不需要提交到仓库）
rm -f openclaw-agent-dashboard-v*.tgz

# 清理前端构建产物
rm -rf frontend/dist

# 清理插件打包产物
rm -rf plugin/dashboard plugin/frontend-dist
```

---

## 五、用户安装方式

### 5.1 一键安装（推荐）

```bash
curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh | bash
```

### 5.2 指定版本安装

```bash
DASHBOARD_VERSION=1.0.1 curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh | bash
```

### 5.3 从源码安装

```bash
git clone https://github.com/Umarchen/openclaw-agent-dashboard.git
cd openclaw-agent-dashboard
npm run deploy
```

---

## 六、环境变量参考

### install.sh 支持的环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DASHBOARD_VERSION` | 指定安装版本 | `latest` |
| `DASHBOARD_RELEASE_URL` | 自定义下载地址 | GitHub Releases URL |
| `DASHBOARD_SKIP_PYTHON` | 跳过 Python 依赖安装 | `0` |
| `VERBOSE` | 显示详细输出 | `0` |
| `DRY_RUN` | 仅预览，不执行 | `0` |

### install-plugin.sh 支持的环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VERBOSE` | 显示详细输出 | `0` |
| `DRY_RUN` | 仅预览，不执行 | `0` |
| `OPENCLAW_STATE_DIR` | OpenClaw 配置目录 | - |
| `OPENCLAW_HOME` | 替代 HOME | `$HOME` |

---

## 七、常见问题

### Q1: GitHub Actions 构建失败

检查：
- `plugin/openclaw.plugin.json` 格式是否正确
- `npm run pack` 本地是否能正常运行
- package.json 中的依赖是否完整

### Q2: 下载 tgz 失败

用户可能遇到网络问题，建议：
- 设置代理：`export https_proxy=http://proxy:port`
- 手动下载后使用本地文件：`DASHBOARD_RELEASE_URL=file:///path/to/tgz`

### Q3: Python 依赖安装失败

常见于 Debian/Ubuntu PEP 668 环境：
```bash
# 安装 python3-venv
sudo apt install python3-venv python3-pip

# 或手动安装依赖
python3 -m pip install -r ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard/requirements.txt --user
```

---

## 八、快速命令参考

```bash
# 开发流程
npm run pack                    # 构建前端 + 打包插件
npm run deploy                  # 打包 + 安装到本地
bash scripts/release-pack.sh    # 生成发布 tgz

# 测试流程
DRY_RUN=1 bash scripts/install.sh                    # 预览安装
DASHBOARD_RELEASE_URL=file://... bash scripts/install.sh  # 本地 tgz 测试

# 发布流程
vim plugin/openclaw.plugin.json  # 更新版本号
git add . && git commit -m "release: vX.X.X"
git push origin main
git tag vX.X.X && git push origin vX.X.X  # 触发 CI/CD

# 清理
rm -f openclaw-agent-dashboard-v*.tgz
```
