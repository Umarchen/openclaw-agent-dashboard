# OpenClaw Agent Dashboard

多 Agent 可视化看板 - 实时展示 OpenClaw Agent 状态、任务进度和错误分析。

## 功能特性

- **工位视图** - 以卡片形式展示主 Agent 和子 Agent 状态
- **时序视图** - 展示 Agent 执行步骤的时间线
- **链路视图** - 展示主 Agent 与子 Agent 的任务派发链路
- **Agent 配置** - 查看和修改 Agent 的模型配置
- **错误分析** - 错误根因分析、分类和修复建议
- **API 状态** - 展示 API 服务异常和限流情况
- **性能监控** - Token 使用、响应时间等

## 系统要求

| 组件 | 要求 |
|------|------|
| **openclaw** | 已安装 (`npm install -g openclaw`) |
| **Node.js** | 16+ |
| **Python** | 3.8+ |
| **pip** | python3-pip |
| **venv** | python3-venv（Linux 推荐） |

### 各系统依赖安装

**Debian / Ubuntu:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

**Fedora / CentOS / RHEL:**
```bash
sudo dnf install python3 python3-pip
```

**macOS:**
```bash
brew install python3
```

**Windows:**
1. 安装 [Node.js](https://nodejs.org/)（LTS 版本）
2. 安装 [Python 3](https://www.python.org/downloads/)
   - ⚠️ 安装时务必勾选 **"Add Python to PATH"**
3. 安装 [Git for Windows](https://git-scm.com/download/win)（可选，用于 `curl | bash` 安装方式）

## 快速安装

### 方式一：一键安装（推荐）

```bash
# 一键安装（需已安装 openclaw：npm install -g openclaw）
curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh | bash
```

安装完成后，执行任意 `openclaw` 命令时 Dashboard 会自动启动。

访问地址: http://localhost:38271

**可选参数**:

```bash
# 安装指定版本
DASHBOARD_VERSION=1.0.0 curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh | bash

# 使用自定义下载地址
DASHBOARD_RELEASE_URL=https://example.com/openclaw-agent-dashboard-v1.0.0.tgz curl -fsSL ... | bash

# 跳过 Python 依赖安装
DASHBOARD_SKIP_PYTHON=1 curl -fsSL ... | bash

# 显示详细输出（调试用）
VERBOSE=1 curl -fsSL ... | bash

# 预览安装过程（不执行实际安装）
DRY_RUN=1 curl -fsSL ... | bash
```

### 方式二：从源码安装

```bash
# 克隆仓库
git clone https://github.com/Umarchen/openclaw-agent-dashboard.git
cd openclaw-agent-dashboard

# 部署到 OpenClaw（构建前端 + 打包插件 + 安装）
npm run deploy
```

**Windows 用户**：源码安装使用 Node.js 脚本，无需 Git Bash，在 PowerShell 或 CMD 中直接运行：

```powershell
# 克隆仓库
git clone https://github.com/Umarchen/openclaw-agent-dashboard.git
cd openclaw-agent-dashboard

# 部署（跨平台）
npm run deploy
```

### 方式三：手动下载安装

从 [GitHub Releases](https://github.com/Umarchen/openclaw-agent-dashboard/releases) 下载 tgz 包：

```bash
# 下载
curl -LO https://github.com/Umarchen/openclaw-agent-dashboard/releases/download/v1.0.0/openclaw-agent-dashboard-v1.0.0.tgz

# 安装
openclaw plugins install openclaw-agent-dashboard-v1.0.0.tgz

# 安装 Python 依赖
cd ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard
python3 -m pip install -r requirements.txt --user
```

## 命令说明

| 命令 | 说明 |
|------|------|
| `npm run deploy` | 打包 + 安装到 OpenClaw（首次安装或升级） |
| `npm run upgrade` | 拉取最新代码 + 部署（推荐用于升级） |
| `npm run pack` | 仅打包插件，不安装（开发调试用） |
| `npm run bundle` | 生成可分发的压缩包（给同事用） |
| `npm run start` | 独立启动 Dashboard（插件未自动启动时使用） |

## 离线分发（给同事）

如果 git clone 失败，可以打包分发：

```bash
# 生成压缩包
npm run bundle
# 输出: openclaw-agent-dashboard-v1.0.0.tar.gz
```

同事收到后：

```bash
# 解压
tar -xzf openclaw-agent-dashboard-v1.0.0.tar.gz

# 进入目录
cd openclaw-agent-dashboard

# 安装
npm run deploy
```

## Python 依赖安装策略

安装脚本采用以下策略安装 Python 依赖：

1. **venv（推荐）** - 创建虚拟环境，隔离依赖，不受 PEP 668 影响
2. **pip --user（回退）** - 安装到 `~/.local/`，适用于无 venv 的环境

若安装失败，请确保已安装系统依赖（见 [系统要求](#系统要求)）。

详见 [Python 环境兼容性](docs/python-environment-compatibility.md)。

## 独立运行（不作为插件）

如果需要独立运行（不作为插件）：

```bash
# 1. 安装后端依赖
cd src/backend
pip install -r requirements.txt

# 2. 构建前端
cd ../../frontend
npm install
npm run build

# 3. 启动后端
cd ../src/backend
uvicorn main:app --host 0.0.0.0 --port 38271
```

## 项目结构

```
openclaw-agent-dashboard/
├── frontend/              # Vue 3 前端
│   └── src/              # 组件源码
├── src/backend/           # FastAPI 后端
│   ├── api/              # API 路由
│   ├── data/             # 数据读取层
│   └── main.py           # 入口
├── plugin/                # 插件打包配置
├── scripts/               # 安装与构建脚本
│   ├── lib/              # 公共函数库
│   ├── install.sh        # 一键安装
│   └── install-plugin.sh # 源码安装
├── .github/workflows/     # CI/CD
└── docs/                  # 设计文档
```

## 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/agents` | Agent 列表及状态 |
| GET | `/api/agent-config/:id` | Agent 配置 |
| PUT | `/api/agent-config/:id/model` | 更新模型配置 |
| GET | `/api/error-analysis/:id` | 错误分析 |
| GET | `/api/timeline/:id` | 时序数据 |
| GET | `/api/chains` | 任务链路 |

完整 API 文档: http://localhost:38271/docs

## 数据源

- `~/.openclaw/openclaw.json` - Agent 配置
- `~/.openclaw/subagents/runs.json` - 子代理运行记录
- `~/.openclaw/agents/*/sessions/*.jsonl` - 会话消息

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENCLAW_STATE_DIR` | OpenClaw 配置根目录（优先级最高） | - |
| `OPENCLAW_HOME` | 替代 HOME，用于解析 `~/.openclaw` | `$HOME` |

插件安装路径与 `openclaw` 命令一致：`$OPENCLAW_STATE_DIR/extensions/` 或 `$OPENCLAW_HOME/.openclaw/extensions/` 或 `~/.openclaw/extensions/`，确保 Gateway 能正确发现插件。

## 开发调试

```bash
# 修改代码后重新部署
npm run deploy
openclaw gateway restart
```

## 故障排查

### Python 依赖安装失败

```
❌ Python 依赖安装失败
```

**解决方案：**

```bash
# Debian/Ubuntu
sudo apt update && sudo apt install python3 python3-pip python3-venv

# 重新安装
npm run deploy

# 或手动安装依赖
python3 -m pip install -r ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard/requirements.txt --user
```

### 无法访问 Dashboard

若 http://localhost:38271 无法访问，可能是插件未随 Gateway 自动启动，可手动启动：

```bash
# 方式一：在项目目录下（需先 npm run deploy）
npm run start

# 方式二：使用已安装的插件目录
cd ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard
OPENCLAW_HOME=~/.openclaw python3 -m uvicorn main:app --host 0.0.0.0 --port 38271
```

说明：`openclaw gateway restart` 重启的是 Gateway 网关（端口 18789），不是 Agent Dashboard（38271）。Dashboard 作为插件随 Gateway 加载，若 systemd 方式运行的 Gateway 未正确加载插件，需手动启动 Dashboard。

### 安装报错：plugin not found / Invalid config

若出现 `plugins.allow: plugin not found: openclaw-agent-dashboard` 或 `Invalid config`，说明配置中有脏数据（插件曾被加入 allow 但当前未被发现）。按以下步骤处理：

**方式一：先清理再安装（推荐）**

```bash
# 1. 卸载旧配置
openclaw plugins uninstall openclaw-agent-dashboard

# 2. 重新安装
npm run deploy
```

**方式二：手动编辑配置**

编辑 `~/.openclaw/openclaw.json`，在 `plugins` 下：

- 若存在 `allow` 数组且包含 `"openclaw-agent-dashboard"`，将其移除
- 若存在 `entries.openclaw-agent-dashboard`，可删除
- 若存在 `installs.openclaw-agent-dashboard`，可删除

保存后执行 `npm run deploy`。

## 许可证

MIT
