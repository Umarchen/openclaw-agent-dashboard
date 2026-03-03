# OpenClaw Agent Dashboard

多 Agent 可视化看板 - 实时展示 OpenClaw Agent 状态、任务进度、API 异常和错误分析。

## 使用方式

| 方式 | 适用场景 |
|------|----------|
| **独立运行**（推荐） | 日常开发、自己使用，克隆后直接启动 |
| **插件模式**（可选） | 希望随 OpenClaw 启动时自动打开 Dashboard |

---

## 功能特性

- ✅ **工位视图** - 以卡片形式展示主 Agent 和子 Agent
- ✅ **状态展示** - 空闲/工作中/异常三种状态
- ✅ **时序视图** - 展示 Agent 执行步骤的时间线
- ✅ **链路视图** - 展示主 Agent 与子 Agent 的任务链路
- ✅ **Agent 配置** - 查看和修改 Agent 的模型配置
- ✅ **错误分析** - 错误根因分析、分类和修复建议
- ✅ **API 状态** - 展示 API 服务异常
- ✅ **性能监控** - Token 使用、响应时间等
- ✅ **自动刷新** - 每 10 秒自动刷新数据

## 技术栈

**后端**:
- Python 3.10+
- FastAPI
- Pydantic

**前端**:
- Vue 3
- TypeScript
- Vite

## 项目结构

```
openclaw-agent-dashboard/
├── docs/
│   ├── specs/              # 需求规格
│   └── design/             # 系统设计
├── src/
│   ├── backend/            # 后端代码
│   │   ├── api/           # API 路由
│   │   ├── data/          # 数据读取层
│   │   ├── status/        # 状态计算层
│   │   └── main.py        # 主入口
│   └── frontend/          # 前端代码
│       ├── src/           # Vue 组件
│       └── index.html
├── plugin/dashboard/       # 插件版本
└── README.md
```

## 快速开始（独立运行，推荐）

克隆仓库后，按以下步骤启动：

### 1. 安装依赖

**后端**:
```bash
cd src/backend
pip install -r requirements.txt
```

**前端**:
```bash
cd frontend
npm install
```

### 2. 构建前端

```bash
cd frontend
npm run build
```

### 3. 启动后端

```bash
cd src/backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. 访问看板

打开浏览器访问: http://localhost:8000

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `OPENCLAW_HOME` | OpenClaw 配置目录 | `~/.openclaw` |
| `VRT_PROJECTS_ROOT` | 项目根目录 | `~/vrt-projects` |

## API 文档

后端启动后，访问: http://localhost:8000/docs

### 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/agents` | 获取所有 Agent 列表及状态 |
| GET | `/api/agents/:id` | 获取单个 Agent 详情 |
| GET | `/api/agent-config/:id` | 获取 Agent 配置 |
| PUT | `/api/agent-config/:id/model` | 更新 Agent 模型配置 |
| GET | `/api/error-analysis/:id` | 获取 Agent 错误分析 |
| GET | `/api/timeline/:id` | 获取 Agent 时序数据 |
| GET | `/api/chains` | 获取任务链路 |
| GET | `/api/subagents` | 获取子代理运行记录 |
| GET | `/api/workflows` | 获取项目工作流状态 |
| GET | `/api/api-status` | 获取 API 服务状态 |

## 数据源

看板从以下数据源读取信息：

- `~/.openclaw/openclaw.json` - Agent 配置
- `~/.openclaw/subagents/runs.json` - 子代理运行记录
- `~/.openclaw/agents/*/sessions/*.jsonl` - 会话消息
- `~/.openclaw/agents/*/sessions/*.deleted.*` - 归档的子任务会话

## 部署

### 生产环境

**后端**:
```bash
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

**前端**:
```bash
npm run build
# Nginx 托管 dist 目录
```

## 插件安装（可选）

若希望 Dashboard 随 OpenClaw 启动时自动运行，可安装为插件：

```bash
# 一键安装（推荐）
./scripts/install-plugin.sh
# 或
npm run install-plugin
```

**同事使用**：克隆仓库后执行上述一条命令即可，脚本会自动完成构建、安装、Python 依赖。

## 开发调试

修改插件代码后，需重新构建并安装才能生效：

```bash
npm run deploy
openclaw gateway restart
```

## 注意事项

- ⚠️ 需要确保 OpenClaw 正在运行，且有 Agent 配置
- ⚠️ 需要有权限访问 `~/.openclaw` 目录
- ⚠️ 生产环境建议配置适当的认证机制

## 许可证

MIT

---

*OpenClaw Agent Dashboard v1.1 - 2026-03-03*
