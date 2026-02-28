# OpenClaw Agent Dashboard 插件

多 Agent 可视化看板 - 作为 OpenClaw 插件安装后，随 OpenClaw 启动自动运行。

## 一键安装（推荐）

克隆仓库后，在项目根目录执行：

```bash
./scripts/install-plugin.sh
# 或
npm run install-plugin
```

**前置要求**（脚本会自动检查）：
- Node.js（构建前端）
- Python 3.10+
- OpenClaw（`npm install -g openclaw`）

安装完成后，执行任意 `openclaw` 命令即可自动启动 Dashboard。

---

## 依赖说明

| 依赖 | 用途 |
|------|------|
| Node.js | 构建前端（Vue→静态文件），仅安装时需要 |
| Python 3.10+ | 运行 Dashboard 后端 |
| openclaw | 主程序 |
| fastapi, uvicorn, watchdog 等 | 由安装脚本自动 `pip install` |

## 手动安装

若一键脚本失败，可分步执行：

```bash
# 1. 构建 + 打包
npm run build-plugin

# 2. 安装插件
openclaw plugins install ./plugin

# 3. 安装 Python 依赖
pip install -r ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard/requirements.txt
```

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
   复制 `config.json.example` 并修改即可，可随项目分发。
3. **openclaw.json**：`plugins.entries.openclaw-agent-dashboard.config.port`
4. **默认**：8000

端口被占用时会自动尝试 8001、8002...

## 首次使用：安装 Python 依赖

插件内的 `dashboard/` 需要 Python 依赖。若未全局安装，可在插件目录执行：

```bash
cd ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard
pip install -r requirements.txt
```
