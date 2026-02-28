# OpenClaw Agent Dashboard

多 Agent 可视化看板 - 实时展示 OpenClaw Agent 状态、任务进度和 API 异常。

## 使用方式

| 方式 | 适用场景 |
|------|----------|
| **独立运行**（推荐） | 日常开发、自己使用，克隆后直接启动 |
| **插件模式**（可选） | 希望随 OpenClaw 启动时自动打开 Dashboard |

---

## 功能特性

- ✅ **工位视图** - 以卡片形式展示主 Agent 和子 Agent
- ✅ **状态展示** - 空闲/工作中/异常三种状态
- ✅ **产出查看** - 点击查看 Agent 最近输出
- ✅ **API 状态** - 展示 API 服务异常
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
├── tests/                  # 测试
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

### 2. 启动后端

```bash
cd src/backend
uvicorn main:app --reload --port 8000
```

### 3. 启动前端（开发模式）

```bash
cd frontend
npm run dev
```

### 4. 访问看板

打开浏览器访问: http://localhost:5173

> 后端会托管前端静态文件。若已执行 `npm run build`，也可直接访问 http://localhost:8000 使用生产构建版本。

## API 文档

后端启动后，访问: http://localhost:8000/docs

### 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/agents` | 获取所有 Agent 列表及状态 |
| GET | `/api/agents/:id` | 获取单个 Agent 详情 |
| GET | `/api/subagents` | 获取子代理运行记录 |
| GET | `/api/workflows` | 获取项目工作流状态 |
| GET | `/api/api-status` | 获取 API 服务状态 |

## 数据源

看板从以下数据源读取信息：

- `~/.openclaw/openclaw.json` - Agent 配置
- `~/.openclaw/subagents/runs.json` - 子代理运行记录
- `~/.openclaw/agents/*/sessions/*.jsonl` - 会话消息
- `~/.openclaw/workspace-*/memory/model-failures.log` - API 异常日志

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

详见 `plugin/README.md`。

## 开发说明

### 添加新 Agent 类型

1. 在 `AgentCard.vue` 中添加新的 emoji 规则
2. 状态计算逻辑在 `status/status_calculator.py`

### 自定义刷新间隔

在 `App.vue` 中修改 `autoRefreshSeconds` 的值（默认 10 秒）。

## 注意事项

- ⚠️ 需要确保 OpenClaw 正在运行，且有 Agent 配置
- ⚠️ 需要有权限访问 `~/.openclaw` 目录
- ⚠️ 生产环境建议配置适当的认证机制

## 许可证

MIT

---

*OpenClaw Agent Dashboard v1.0 - 2026-02-26*
