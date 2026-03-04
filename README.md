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

## 快速安装

```bash
# 克隆仓库
git clone https://github.com/Umarchen/openclaw-agent-dashboard.git
cd openclaw-agent-dashboard

# 部署到 OpenClaw（构建前端 + 打包插件 + 安装）
npm run deploy
```

安装完成后，执行任意 `openclaw` 命令时 Dashboard 会自动启动。

访问地址: http://localhost:8000

## 命令说明

| 命令 | 说明 |
|------|------|
| `npm run deploy` | 打包 + 安装到 OpenClaw（首次安装或升级） |
| `npm run upgrade` | 拉取最新代码 + 部署（推荐用于升级） |
| `npm run pack` | 仅打包插件，不安装（开发调试用） |
| `npm run bundle` | 生成可分发的压缩包（给同事用） |

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
uvicorn main:app --host 0.0.0.0 --port 8000
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
├── scripts/               # 构建脚本
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

完整 API 文档: http://localhost:8000/docs

## 数据源

- `~/.openclaw/openclaw.json` - Agent 配置
- `~/.openclaw/subagents/runs.json` - 子代理运行记录
- `~/.openclaw/agents/*/sessions/*.jsonl` - 会话消息

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENCLAW_HOME` | OpenClaw 配置目录 | `~/.openclaw` |

## 开发调试

```bash
# 修改代码后重新部署
npm run deploy
openclaw gateway restart
```

## 许可证

MIT
