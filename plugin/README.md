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
| `npm run deploy` | 打包 + 安装到 OpenClaw（首次安装或升级） |
| `npm run upgrade` | 拉取最新代码 + 部署（推荐用于升级） |
| `npm run pack` | 仅打包插件，不安装（开发调试用） |
| `npm run bundle` | 生成可分发的压缩包（离线分发） |

### 升级插件

```bash
cd openclaw-agent-dashboard
npm run upgrade
```

输出示例：
```
=== OpenClaw Agent Dashboard 插件升级 ===

  1.0.0 → 1.1.0

✓ 前置条件检查通过
>>> 1/4 构建前端...
>>> 2/4 打包插件...
>>> 3/4 移除旧版本...
>>> 4/4 安装新版本...
>>> 检查 Python 依赖...
✓ Python 依赖已就绪

=== 升级完成 (1.0.0 → 1.1.0) ===
```

---

## 使用

插件加载后（执行任意 `openclaw` 命令时）会自动启动 Dashboard 服务。

**访问地址**：http://localhost:38271（或你配置的端口）

### 端口配置（便于移植，无需改 openclaw.json）

优先级从高到低：

1. **环境变量**：`DASHBOARD_PORT=38271`
2. **独立配置文件**：`~/.openclaw-agent-dashboard/config.json`（可与 `OPENCLAW_AGENT_DASHBOARD_DATA` 环境变量配合）
   ```json
   { "port": 38271 }
   ```
3. **openclaw.json**：`plugins.entries.openclaw-agent-dashboard.config.port`
4. **默认**：38271

端口被占用时会自动尝试 38272、38273...

---

## 手动安装（故障恢复）

若 `npm run deploy` 失败，可分步执行：

```bash
# 1. 打包
npm run pack

# 2. 安装插件
openclaw plugins install ./plugin

# 3. 安装 Python 依赖（通常不需要，脚本会自动完成；Debian/Ubuntu 请用 venv）
cd ~/.openclaw/extensions/openclaw-agent-dashboard/dashboard
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```
