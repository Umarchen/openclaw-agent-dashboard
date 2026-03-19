# Windows 协作流程与模型配置排查说明

## 背景

在 Windows 环境中，出现以下现象：

- 协作流程的时序视图无显示
- 模型配置（可用模型列表）获取失败

本说明用于快速定位**读取文件路径**、**配置入口**以及**根因与修复点**。

---

## 关键读取路径

所有数据最终都应来自 OpenClaw 根目录（记为 `<OpenClawRoot>`）：

- Agent 配置：`<OpenClawRoot>/openclaw.json`
- 子代理运行记录：`<OpenClawRoot>/subagents/runs.json`
- 会话数据：`<OpenClawRoot>/agents/<agent_id>/sessions/*.jsonl`
- 会话索引：`<OpenClawRoot>/agents/<agent_id>/sessions/sessions.json`
- 模型失败日志：`<workspace>/memory/model-failures.log`（由 `openclaw.json` 中各 Agent 的 `workspace` 推导）

---

## 配置读取入口

### 1) 协作流程与时序

- 协作流程 API：`src/backend/api/collaboration.py`
- 时序读取：`src/backend/data/timeline_reader.py`
- 子代理运行读取：`src/backend/data/subagent_reader.py`
- 文件监听推送：`src/backend/watchers/file_watcher.py`

### 2) 模型配置

- 模型配置 API：`src/backend/api/agent_config_api.py`
- 配置管理：`src/backend/data/agent_config_manager.py`
- 基础配置读取：`src/backend/data/config_reader.py`

前端对应接口：

- `/api/collaboration`
- `/api/collaboration/dynamic`
- `/api/timeline/{agent_id}`
- `/api/available-models`
- `/api/agent-config/{agent_id}`

---

## 根因分析（Windows 重点）

问题本质是**目录解析不统一**：

- 某些模块以前硬编码 `Path.home()/.openclaw`
- 某些模块只识别 `OPENCLAW_HOME`
- 未完整兼容 `OPENCLAW_STATE_DIR`
- 未兼容 `OPENCLAW_HOME` 两种常见写法：
  - 直接指向 `.openclaw`
  - 指向用户 Home（需要再拼接 `.openclaw`）

导致在同事机器上路径不一致时，部分接口读取不到真实数据目录，从而表现为：

- 协作流程/时序空白
- available models 为空或报错

---

## 已完成修复

已统一关键模块的 OpenClaw 根目录解析优先级：

1. `OPENCLAW_STATE_DIR`（最高优先级）
2. `OPENCLAW_HOME`（兼容两种写法）
3. `~/.openclaw`（兜底）

并同时修改了源码目录与插件镜像目录，避免打包后回退。

### 已修改文件

- `src/backend/data/config_reader.py`
- `src/backend/data/agent_config_manager.py`
- `src/backend/data/timeline_reader.py`
- `src/backend/data/subagent_reader.py`
- `src/backend/api/collaboration.py`
- `src/backend/watchers/file_watcher.py`
- `plugin/dashboard/data/config_reader.py`
- `plugin/dashboard/data/agent_config_manager.py`
- `plugin/dashboard/data/timeline_reader.py`
- `plugin/dashboard/data/subagent_reader.py`
- `plugin/dashboard/api/collaboration.py`
- `plugin/dashboard/watchers/file_watcher.py`

---

## 同事机器验证步骤（PowerShell）

1. 查看环境变量：

```powershell
$env:OPENCLAW_STATE_DIR
$env:OPENCLAW_HOME
```

2. 确认目标目录存在关键文件：

- `openclaw.json`
- `agents\`
- `subagents\runs.json`

3. 重启 Dashboard（或 Gateway）后验证页面：

- 协作流程是否恢复
- 时序视图是否有数据
- Agent 配置里的模型列表是否恢复

---

## 诊断接口

已实现 **GET** `/api/debug/paths`，直接返回后端当前解析出的：

- `openclawRoot`：OpenClaw 根目录路径
- `openclawJsonExists`：`openclaw.json` 是否存在
- `agentsDirExists`：`agents/` 是否存在
- `subagentsRunsExists`：`subagents/runs.json` 是否存在

可显著降低后续跨机器环境排查成本。同事机器上可访问 `http://localhost:38271/api/debug/paths` 验证路径解析是否正确。

