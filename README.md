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

### 方式一：OpenClaw 官方命令（推荐，全平台）

与 OpenClaw 其它 npm 插件一致，由 CLI 下载并安装到 `extensions` 目录：

```bash
openclaw plugins install openclaw-agent-dashboard@latest
```

指定版本：

```bash
openclaw plugins install openclaw-agent-dashboard@1.0.17
```

首次安装见上；**已安装后的升级**见下文 [升级插件（已用 npm 安装）](#升级插件已用-npm-安装)。

**安装 Python 依赖（首次或报错时执行一次）**  
插件目录在 `~/.openclaw/extensions/openclaw-agent-dashboard`（Windows 为 `%USERPROFILE%\.openclaw\extensions\openclaw-agent-dashboard`）。打包时已包含跨平台的 `scripts/install-python-deps.js`，请用 **Node** 调用（勿依赖 bash）：

**Linux / macOS：**

```bash
PLUGIN="$HOME/.openclaw/extensions/openclaw-agent-dashboard"
node "$PLUGIN/scripts/install-python-deps.js" "$PLUGIN" --verbose
```

**Windows（PowerShell）：**

```powershell
$plugin = "$env:USERPROFILE\.openclaw\extensions\openclaw-agent-dashboard"
node "$plugin\scripts\install-python-deps.js" $plugin --verbose
```

脚本会在 `dashboard/.venv` 下创建虚拟环境并安装 `requirements.txt`，避免 Debian/Ubuntu 上 PEP 668 限制。

> 安装完成后，在 **Gateway 进程**中加载插件时会自动启动 Dashboard。访问地址默认: http://localhost:38271

---

### 方式二：从源码安装（开发者）

```bash
git clone https://github.com/Umarchen/openclaw-agent-dashboard.git
cd openclaw-agent-dashboard
npm run deploy
```

`npm run deploy` 会执行 `pack`（构建前端 + 写入 `plugin/`）并调用 `openclaw plugins install` 指向本地 `plugin` 目录。**Windows** 在 PowerShell / CMD 中同样可用。

---

### 方式三：GitHub Release 离线包

从 [GitHub Releases](https://github.com/Umarchen/openclaw-agent-dashboard/releases) 下载 `openclaw-agent-dashboard-v*.tgz` 后：

```bash
openclaw plugins install ./openclaw-agent-dashboard-v1.0.0.tgz
```

再按 [方式一](#方式一openclaw-官方命令推荐全平台) 用 `node .../install-python-deps.js` 安装 Python 依赖。

---

### 方式四：一键脚本（仅 Linux / macOS，可选）

```bash
curl -fsSL https://raw.githubusercontent.com/Umarchen/openclaw-agent-dashboard/main/scripts/install.sh | bash
```

更推荐优先使用 **方式一**，便于版本与 OpenClaw 配置一致。

---

### 关于旧版 `npx openclaw-agent-dashboard`

早期曾通过 `npx` 调用安装脚本；**当前推荐**使用 `openclaw plugins install` 安装插件本体。若仍需从 GitHub Release 拉取完整 tgz，请使用方式三或仓库内 `scripts/install.js`（开发者）。

---

### 从 path / 旧版安装迁移到 npm（同事必读）

若此前使用 **`openclaw plugins install /某路径/plugin`**、手动拷贝到 `extensions`，或旧版安装方式，改用 **方式一** 时可能出现：

```text
plugin already exists: .../openclaw-agent-dashboard (delete it first)
```

**原因简述**：OpenClaw 对 **`source: "path"`** 的插件执行卸载时，**不会删除** `~/.openclaw/extensions/` 下对应目录（避免误删本机源码目录）；配置已卸掉，但文件夹仍在，新的 `plugins install` 会拒绝覆盖。

**一次性处理（迁移只需做一次）**：

```bash
openclaw plugins uninstall openclaw-agent-dashboard --force
rm -rf ~/.openclaw/extensions/openclaw-agent-dashboard
openclaw plugins install openclaw-agent-dashboard@latest
```

**Windows（PowerShell）**：

```powershell
openclaw plugins uninstall openclaw-agent-dashboard --force
Remove-Item -Recurse -Force "$env:USERPROFILE\.openclaw\extensions\openclaw-agent-dashboard"
openclaw plugins install openclaw-agent-dashboard@latest
```

然后按 [方式一](#方式一openclaw-官方命令推荐全平台) 安装 Python 依赖，并重启 Gateway。

---

### 升级插件（已用 npm 安装）

对已通过 **npm** 安装的副本，请使用 OpenClaw 的 **更新** 命令（会覆盖旧版本，**不会**出现上面的 `plugin already exists`）：

```bash
openclaw plugins update openclaw-agent-dashboard
# 或按官方文档更新全部 npm 插件，例如：
# openclaw plugins update --all
```

**不要**在已安装的情况下再跑 `openclaw plugins install openclaw-agent-dashboard@latest` 当作升级（可能被判定为「全新安装」且目录已存在而失败）。具体子命令以本机 `openclaw plugins --help` 为准。

## 命令说明

| 命令 | 说明 |
|------|------|
| `openclaw plugins install openclaw-agent-dashboard@latest` | **用户推荐**：从 npm 安装插件到 OpenClaw |
| `npm run deploy` | 开发：打包 + `openclaw plugins install` 本地 `plugin/` |
| `npm run publish:npm` | 维护者：打包后 `npm publish --prefix plugin` 发布到 npm |
| `npm run upgrade` | 开发：拉取最新代码 + `deploy` |
| `npm run pack` | 仅打包 `plugin/`（不安装） |
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

1. **venv（推荐）** - 在插件目录下创建 `.venv`，隔离依赖，不受 PEP 668 影响；Debian/Ubuntu 下**必须**用此方式（系统禁止 pip 装到系统/用户目录）。
2. **pip --user（回退）** - 仅在不支持 venv 或非 Debian/Ubuntu 环境下尝试，安装到 `~/.local/`。

若安装失败，请确保已安装系统依赖（见 [系统要求](#系统要求)）。

详见 [Python 环境兼容性](docs/python-environment-compatibility.md)。

## 独立运行（不作为插件）

如果需要独立运行（不作为插件）：

```bash
# 1. 安装后端依赖（Debian/Ubuntu 建议用 venv：python3 -m venv .venv && .venv/bin/pip install -r requirements.txt）
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
# Debian/Ubuntu（需安装 python3-venv）
sudo apt update && sudo apt install python3 python3-pip python3-venv

# 推荐：用插件自带的 Node 脚本安装 venv 依赖（跨平台）
PLUGIN="$HOME/.openclaw/extensions/openclaw-agent-dashboard"
node "$PLUGIN/scripts/install-python-deps.js" "$PLUGIN" --verbose
```

若仍失败，可手动在 `dashboard` 下创建 venv：

```bash
cd ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard
python3 -m venv .venv
# Linux/macOS:
.venv/bin/pip install -r requirements.txt
# Windows: .venv\Scripts\pip install -r requirements.txt
```

### 无法访问 Dashboard

若 http://localhost:38271 无法访问，可能是插件未随 Gateway 自动启动，可手动启动：

```bash
# 方式一：在项目目录下（需先 npm run deploy）
npm run start

# 方式二：使用已安装的插件目录（若有 .venv 可用 .venv/bin/python 替代 python3）
cd ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard
OPENCLAW_HOME=~/.openclaw python3 -m uvicorn main:app --host 0.0.0.0 --port 38271
```

说明：`openclaw gateway restart` 重启的是 Gateway 网关（端口 18789），不是 Agent Dashboard（38271）。Dashboard 作为插件随 Gateway 加载，若 systemd 方式运行的 Gateway 未正确加载插件，需手动启动 Dashboard。

### 安装报错：plugin not found / Invalid config

若出现 `plugins.allow: plugin not found: openclaw-agent-dashboard` 或 `Invalid config`，说明配置中有脏数据（插件曾被加入 allow 但当前未被发现）。按以下步骤处理：

**方式一：先清理再安装（推荐）**

```bash
openclaw plugins uninstall openclaw-agent-dashboard
openclaw plugins install openclaw-agent-dashboard@latest
```

**方式二：手动编辑配置**

编辑 `~/.openclaw/openclaw.json`，在 `plugins` 下：

- 若存在 `allow` 数组且包含 `"openclaw-agent-dashboard"`，将其移除
- 若存在 `entries.openclaw-agent-dashboard`，可删除
- 若存在 `installs.openclaw-agent-dashboard` 且为 `source: "path"` 的旧记录，可删除后改为官方 `npm` 安装

保存后再执行 `openclaw plugins install openclaw-agent-dashboard@latest`。

## 许可证

MIT
