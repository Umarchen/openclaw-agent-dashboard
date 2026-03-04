# OpenClaw Agent Dashboard 插件

多 Agent 可视化看板 - 作为 OpenClaw 插件安装后，随 OpenClaw 启动自动运行。

## 快速开始

克隆仓库后，在项目根目录执行：

```bash
npm run deploy
```

该命令会自动完成：
1. 检查前置条件（Node.js、Python 3、OpenClaw）
2. 构建前端
3. 打包并安装插件到 `~/.openclaw/extensions/`
4. 自动安装 Python 依赖（fastapi、uvicorn 等）

**前置要求**：
- Node.js（构建前端）
- Python 3.10+
- OpenClaw（`npm install -g openclaw`）

安装完成后，执行任意 `openclaw` 命令即可自动启动 Dashboard。

---

## 命令说明

| 命令 | 说明 |
|------|------|
| `npm run deploy` | 打包 + 安装到 OpenClaw（推荐） |
| `npm run pack` | 仅打包插件，不安装（开发调试用） |

---

## 使用

插件加载后（执行任意 `openclaw` 命令时）会自动启动 Dashboard 服务。

**访问地址**：http://localhost:8000（或你配置的端口）

### 端口配置（便于移植，无需改 openclaw.json）

优先级从高到低：

1. **环境变量**：`DASHBOARD_PORT=8000`
2. **独立配置文件**：`~/.openclaw/dashboard/config.json`
   ```json
   { "port": 8000 }
   ```
3. **openclaw.json**：`plugins.entries.openclaw-agent-dashboard.config.port`
4. **默认**：8000

端口被占用时会自动尝试 8001、8002...

---

## 手动安装（故障恢复）

若 `npm run deploy` 失败，可分步执行：

```bash
# 1. 打包
npm run pack

# 2. 安装插件
openclaw plugins install ./plugin

# 3. 安装 Python 依赖（通常不需要，脚本会自动完成）
pip install -r ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard/requirements.txt
```
