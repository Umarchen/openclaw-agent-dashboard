# OpenClaw Agent Dashboard 开发与发布流程

本文档整理不同修改场景下的最优调试与发布方式。

## 前置条件

- **工作目录**：以下命令均在项目根目录 `openclaw-agent-dashboard/` 下执行
- **开发模式**：后端需在 `http://localhost:8000` 运行（如 `openclaw` 启动或 `uvicorn` 独立运行）
- **插件模式**：插件已安装至 `~/.openclaw/extensions/openclaw-agent-dashboard`

### 目录说明（以本工程为例）

| 命令中的路径 | 实际目录 |
|--------------|----------|
| 项目根目录 | `openclaw-agent-dashboard/`（如 `~/vrt-projects/projects/openclaw-agent-dashboard/`） |
| `cd frontend` | 进入 `openclaw-agent-dashboard/frontend/`，即 Vue + Vite 前端源码目录 |
| `cd src/backend` | 进入 `openclaw-agent-dashboard/src/backend/`，即 FastAPI 后端源码目录 |

示例：在项目根目录执行 `cd frontend && npm run dev`，会先切换到 `frontend/` 子目录，再启动 Vite 开发服务器。

---

## 开发模式（调试 / 迭代）

### 仅修改前端

| 步骤 | 执行命令 |
|------|----------|
| 1. 确保后端运行 | `openclaw tui` 或 `openclaw gateway start`（任选其一，保证 8000 端口有服务） |
| 2. 启动前端开发服务 | `cd frontend && npm run dev` |
| 3. 访问 | 浏览器打开 http://localhost:5173 |
| 4. 修改代码 | 保存后浏览器自动热更新，无需重启 |

### 修改前端 + 后端

| 步骤 | 执行命令 |
|------|----------|
| 1. 启动后端 | `openclaw tui` 或 `openclaw gateway start` |
| 2. 启动前端开发服务 | `cd frontend && npm run dev` |
| 3. 访问 | 浏览器打开 http://localhost:5173 |
| 4. 修改前端 | 保存即生效 |
| 5. 修改后端 | 改完后执行 `openclaw gateway restart` |

### 仅修改后端

| 步骤 | 执行命令 |
|------|----------|
| 1. 启动后端（带热重载） | `cd src/backend && uvicorn main:app --reload --port 8000` |
| 2. 访问 | 浏览器打开 http://localhost:8000（需先执行过 `npm run build`）<br>或同时跑 `cd frontend && npm run dev` 后访问 http://localhost:5173 |
| 3. 修改后端 | 保存后 uvicorn 自动重载，刷新浏览器即可 |

---

## 准备发布插件

### 仅修改前端

```bash
npm run build-plugin && openclaw plugins install ./plugin
```

若刷新后未生效，再执行：

```bash
openclaw gateway restart
```

### 修改前端 + 后端

```bash
npm run build-plugin && openclaw plugins install ./plugin
openclaw gateway restart
```

若新增了 Python 依赖，需额外执行：

```bash
pip install -r ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard/requirements.txt
```

### 仅修改后端

```bash
npm run build-plugin && openclaw plugins install ./plugin
openclaw gateway restart
```

> 当前 `build-plugin` 会顺带构建前端，无法单独只打包后端。

---

## 命令速查

| 命令 | 用途 |
|------|------|
| `cd frontend && npm run dev` | 启动 Vite 开发服务器（热更新） |
| `npm run build-plugin` | 构建前端 + 复制前后端到 plugin 目录 |
| `openclaw plugins install ./plugin` | 将 plugin 安装到 OpenClaw |
| `openclaw gateway restart` | 重启 OpenClaw 网关（加载新后端） |
| `npm run deploy` | 完整部署：build-plugin + install-plugin（含 npm install、pip install） |

---

## 开发模式 vs 插件模式

| 对比项 | 开发模式 | 插件模式 |
|--------|----------|----------|
| 前端入口 | http://localhost:5173（Vite） | http://localhost:8000（网关托管） |
| 热更新 | 支持 | 不支持，需重新 build + install |
| 适用场景 | 日常开发、快速迭代 | 正式使用、给他人安装 |
