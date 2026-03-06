# 方案 A：预构建 + 入口脚本 - 修改方案

> 供审核用，确认后再实施。

---

## 一、目标

- **用户体验**：一条命令完成安装，无需 git clone、npm、Node 构建环境
- **安装脚本**：`install.sh` 入口，自动检测环境，下载预构建包并安装
- **保留能力**：开发者仍可通过 `npm run deploy` 从源码安装

---

## 二、核心变化

| 项目 | 当前 | 方案 A 后 |
|------|------|-----------|
| 用户安装方式 | `git clone` → `npm run deploy` | `curl \| bash` 或 `./install.sh` |
| 用户需具备 | Node、npm、Python、openclaw | openclaw、Python（仅用于后端依赖） |
| 前端构建 | 用户本地执行 | CI 预构建，用户下载 |
| 插件包格式 | 无预构建 | 单一 `.tgz`（跨平台通用） |
| Python 依赖 | 脚本内联处理 | 抽取为 `install-python-deps.sh`，逻辑不变 |

---

## 三、预构建包说明

### 3.1 包内容

插件为 **JavaScript + Python + 静态前端**，无需按 OS 区分，**同一 tgz 适用于 Linux/macOS/Windows**。

预构建包 = `npm pack` 产物，结构示例：

```
openclaw-agent-dashboard-1.0.0.tgz
└── package/
    ├── openclaw.plugin.json
    ├── index.js
    ├── package.json
    ├── dashboard/          # Python 后端（已复制）
    │   ├── main.py
    │   ├── requirements.txt
    │   └── ...
    └── frontend-dist/      # 前端构建产物（已构建）
        ├── index.html
        └── assets/
```

### 3.2 发布方式

- **GitHub Releases**：每次发布时附带 `openclaw-agent-dashboard-v{version}.tgz`
- **下载 URL 示例**：`https://github.com/{owner}/{repo}/releases/download/v{version}/openclaw-agent-dashboard-v{version}.tgz`
- **版本**：从 `plugin/openclaw.plugin.json` 的 `version` 读取

---

## 四、目录与脚本变更

### 4.1 新增目录

```
scripts/
├── install.sh              # 入口：检测 → 下载 → 安装（新增）
├── install-python-deps.sh  # Python 依赖安装（从 install-plugin.sh 抽取）
├── install-plugin.sh       # 保留：开发者从源码安装（简化）
├── build-plugin.js         # 不变
├── bundle.sh               # 不变
└── release-pack.sh         # 新增：生成预构建 tgz（供 CI 或本地发布用）
```

### 4.2 入口脚本 `install.sh` 流程

```
1. 检测 OS（linux/macos/windows）
2. 检测 openclaw 是否已安装 → 未安装则退出并提示
3. 解析版本（可选：从 URL 参数或默认 latest）
4. 下载 tgz 到临时目录
   - 支持：GitHub Releases / 自定义 CDN
   - 工具：curl 或 wget
5. openclaw plugins install ./xxx.tgz
6. 调用 install-python-deps.sh 安装 Python 依赖
7. 输出成功信息与访问地址
```

### 4.3 `install-python-deps.sh` 职责

从 `install-plugin.sh` 抽取 Python 依赖安装逻辑，保持：

- venv 优先
- pip --user 兜底
- 多 Python 命令尝试（python3、python、py）

**入参**：`$1` = 插件安装目录（如 `~/.openclaw/extensions/openclaw-agent-dashboard`）

### 4.4 `install-plugin.sh` 简化

保留给开发者使用：

- 不再执行前端构建（若 `frontend/dist` 和 `plugin/dashboard` 已存在则跳过）
- 调用 `build-plugin.js` 打包
- 调用 `openclaw plugins install ./plugin`
- 调用 `install-python-deps.sh` 安装 Python 依赖

删除：大量内联的 venv/pip 回退逻辑，改为调用 `install-python-deps.sh`。

---

## 五、CI 配置（GitHub Actions）

### 5.1 触发

- 推送 tag：`v*`（如 `v1.0.0`）
- 或手动 workflow_dispatch

### 5.2 构建步骤

```yaml
- run: npm ci
- run: npm run pack                    # 构建前端 + 打包插件
- run: bash scripts/release-pack.sh    # 生成 tgz
- uses: actions/upload-artifact@v4
  with:
    name: plugin-tgz
    path: openclaw-agent-dashboard-v*.tgz
```

### 5.3 发布步骤

- 创建 GitHub Release（对应 tag）
- 将 tgz 上传为 Release Asset

### 5.4 `release-pack.sh` 逻辑

```bash
# 1. 确保已 pack（npm run pack）
# 2. cd plugin && npm pack
# 3. 重命名为 openclaw-agent-dashboard-v{VERSION}.tgz
# 4. 输出到项目根目录
```

---

## 六、`install.sh` 行为细节

### 6.1 系统检测

```bash
detect_os() {
  case "$(uname -s)" in
    Linux*)   echo "linux" ;;
    Darwin*)  echo "macos" ;;
    MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
    *)        echo "unknown" ;;
  esac
}
```

### 6.2 下载逻辑

- 优先 `curl -fSL`，失败则尝试 `wget -qO-`
- 支持环境变量覆盖默认 URL：
  - `DASHBOARD_RELEASE_URL`：完整下载 URL
  - `DASHBOARD_VERSION`：版本号（默认 latest）

### 6.3 错误处理

- 下载失败：提示检查网络、代理、可手动下载
- 未安装 openclaw：提示 `npm install -g openclaw`
- Python 依赖失败：提示 `VERBOSE=1` 并给出 `install-python-deps.sh` 的单独调用方式

### 6.4 安装方式

```bash
# 方式一：curl 管道（常见）
curl -fsSL https://raw.githubusercontent.com/{owner}/{repo}/main/scripts/install.sh | bash

# 方式二：先下载再执行
curl -fsSL -o install.sh https://...
bash install.sh

# 方式三：指定版本
DASHBOARD_VERSION=1.0.0 bash install.sh
```

---

## 七、README 更新

### 7.1 快速安装（推荐）

```markdown
## 快速安装

```bash
# 一键安装（需已安装 openclaw：npm install -g openclaw）
curl -fsSL https://raw.githubusercontent.com/{owner}/{repo}/main/scripts/install.sh | bash
```

安装完成后，执行任意 `openclaw` 命令时 Dashboard 会自动启动。

访问地址: http://localhost:38271
```

### 7.2 开发者安装（保留）

```markdown
## 开发者安装（从源码）

```bash
git clone https://github.com/{owner}/{repo}.git
cd openclaw-agent-dashboard
npm run deploy
```
```

---

## 八、待确认项

| 序号 | 说明 | 默认值 |
|------|------|--------|
| 1 | GitHub 仓库地址 | 需确认（README 中为 Umarchen/openclaw-agent-dashboard） |
| 2 | 是否支持 Windows | 先支持，若 `openclaw` 在 Windows 可用则安装；否则提示 |
| 3 | 默认版本 | `latest`（从 GitHub API 获取最新 release） |
| 4 | 是否需要校验 tgz 校验和 | 可选，后续可加 SHA256 |

---

## 九、实施顺序

1. 新增 `scripts/release-pack.sh`
2. 新增 `scripts/install-python-deps.sh`（从 install-plugin.sh 抽取）
3. 简化 `scripts/install-plugin.sh`（调用 install-python-deps.sh）
4. 新增 `scripts/install.sh`
5. 新增 `.github/workflows/release.yml`
6. 更新 README
7. 本地测试：`npm run pack` → `release-pack.sh` → `install.sh` 使用本地 tgz

---

## 十、回退与兼容

- `npm run deploy` 行为不变，仅内部实现简化
- 现有 `bundle.sh` 不变，仍支持离线打包给同事
- 不破坏现有 `install-plugin.sh` 的调用方式
