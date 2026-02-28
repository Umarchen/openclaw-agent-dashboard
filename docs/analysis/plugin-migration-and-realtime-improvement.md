# OpenClaw Agent Dashboard 改造与插件化分析

**文档版本**：v1.0  
**日期**：2026-02-28  
**目标**：在不改架构的前提下提升实时性，并评估插件化可行性（既做成插件又保留现有功能）

---

## 阶段 1 完成状态（2026-02-28）

- ✅ 轮询间隔：`pollingInterval` 30s → 10s
- ✅ WebSocket 路径：`/ws/dashboard` → `/ws`，Vite 代理增加 `/ws`
- ✅ 文件监听：watchdog 监听 runs.json、sessions/*.jsonl、task_history.json、model-failures.log
- ✅ 文件变更时通过 WebSocket 推送 `full_state`（agents、subagents、apiStatus、collaboration、tasks、performance）
- ✅ 防抖：0.5 秒内多次变更只触发一次推送

---

## 一、现状概览

### 1.1 当前架构

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | Python + FastAPI | 独立进程，端口 8000 |
| 前端 | Vue 3 + TypeScript + Vite | 端口 5173（开发）/ 静态托管 |
| 数据获取 | 文件读取 + 轮询 | 无 Hook，无事件驱动 |
| 实时通道 | WebSocket `/ws` | 仅发送初始状态，无服务端主动推送 |

### 1.2 数据源与用途

| 数据 | 路径 | 用途 |
|------|------|------|
| Agent 配置 | `~/.openclaw/openclaw.json` | 角色列表、名称、模型 |
| 子代理运行 | `~/.openclaw/subagents/runs.json` | 当前/历史 subagent 任务、状态 |
| 会话内容 | `~/.openclaw/agents/*/sessions/*.jsonl` | 消息、工具调用、API 错误 |
| 任务历史 | `~/.openclaw/dashboard/task_history.json` | 持久化已完成任务 |
| API 异常 | `~/.openclaw/workspace-*/memory/model-failures.log` | 降级、429、超 token |
| 工作流 | `vrt-projects/.../workflow_state.json` | 项目流水线、待审核产出 |

### 1.3 与 ActivityClaw 对比

| 维度 | 你的 Dashboard | ActivityClaw |
|------|----------------|--------------|
| **信息面** | 宽（配置、状态、API、工作流、性能、协作） | 窄（仅工具调用活动流） |
| **实时性** | 轮询（10–30 秒） | 事件驱动（Hook 触发即推送） |
| **数据来源** | 文件解析（session jsonl、runs.json 等） | Hook `tool_result_persist` |
| **部署形态** | 独立 FastAPI 服务 | OpenClaw 插件，随 OpenClaw 加载启动 |
| **工具级细节** | 从 session 解析 toolCall | 从 Hook 直接获取 |

---

## 二、不改架构的实时性提升

### 2.1 缩短轮询间隔

**改动**：将 `autoRefreshSeconds` 从 10 秒改为 3–5 秒，或在前端 `RealtimeDataManager` 中把 `pollingInterval` 从 30 秒改为 10 秒。

**优点**：实现简单，无需改后端。  
**缺点**：仍为轮询，延迟存在；频繁读文件可能增加 I/O 压力。

**建议**：作为快速优化，可先降到 5 秒，观察 CPU/磁盘负载。

---

### 2.2 文件变更监听（watchdog）

**思路**：对关键文件做 `watchdog` 监听，文件变更时触发后端刷新并推送给前端。

**关键文件**：
- `~/.openclaw/subagents/runs.json`
- `~/.openclaw/agents/*/sessions/*.jsonl`
- `~/.openclaw/dashboard/task_history.json`
- `~/.openclaw/workspace-*/memory/model-failures.log`

**实现要点**：
1. 后端增加 `watchdog` 依赖，监听上述路径。
2. 文件变更时，重新读取对应数据，通过 WebSocket 广播给已连接客户端。
3. 对 `*.jsonl` 可用 `FileSystemEventHandler` 的 `on_modified`，注意防抖（同一文件短时间多次写入只触发一次刷新）。

**优点**：接近「事件驱动」，延迟低，无需改 OpenClaw 核心。  
**缺点**：需要维护监听逻辑，跨平台需测试。

---

### 2.3 完善 WebSocket 推送

**现状**：`websocket.py` 已有 `broadcast_agent_update`、`broadcast_subagent_update`、`broadcast_api_status`，但**没有被调用**，仅发送初始状态。

**改造**：
1. 在 `watchdog` 监听到变更时，调用上述 `broadcast_*` 函数。
2. 或增加一个「刷新触发器」：每次文件变更后，聚合最新数据，通过 `broadcast_message` 发送 `full_state` 或增量更新。

**前端**：`RealtimeDataManager` 已支持按 channel 订阅，只需确保后端推送的 `type`/`channel` 与前端订阅一致。

---

## 三、插件化方案

### 3.1 能否做成 OpenClaw 插件？

**可以。** OpenClaw 插件支持：
- 注册 Hooks（如 `tool_result_persist`）
- 启动后台服务（如 Express/FastAPI）
- 声明 `openclaw.plugin.json` 和配置结构

ActivityClaw 即：Hook 监听 + 启动 Dashboard 服务。

### 3.2 能否既做成插件又保留现有功能？

**可以。** 两种思路：

| 方案 | 说明 | 保留程度 |
|------|------|----------|
| **A. 插件外壳 + 现有服务** | 插件只负责：注册 Hook、启动你的 FastAPI、注入配置路径 | 100% 保留 |
| **B. 混合数据源** | 插件注册 Hook 提供实时工具流，同时继续读文件提供配置/工作流/API 状态等 | 100% 保留 + 实时性增强 |

---

### 3.3 方案 A：插件外壳（推荐起步）

**结构**：
```
openclaw-agent-dashboard-plugin/
├── openclaw.plugin.json
├── package.json
├── index.js                    # 插件入口
└── dashboard/                  # 你现有的 Python 项目（或打包后的 dist）
    ├── main.py
    ├── api/
    ├── data/
    └── ...
```

**插件职责**：
1. 加载时启动你的 FastAPI（通过 `child_process.spawn` 或 `python -m uvicorn`）。
2. 可选：注册 `tool_result_persist`，将事件写入共享文件或内存，供 FastAPI 读取（实现「准实时」）。
3. 通过 `api.config` 获取 `~/.openclaw` 路径，传给 FastAPI 作为环境变量或参数。

**优点**：现有功能完全保留，改造量小。  
**缺点**：实时性仍依赖文件监听或轮询，除非在 Hook 里写文件触发刷新。

---

### 3.4 方案 B：混合数据源（完整插件化）

**思路**：插件既提供 Hook 实时数据，又保留文件读取能力。

| 数据 | 来源 | 说明 |
|------|------|------|
| 工具调用流 | Hook `tool_result_persist` | 实时推送，可单独展示「活动流」 |
| Agent 配置 | 文件 `openclaw.json` | 不变 |
| 子代理运行 | 文件 `runs.json` | 不变；可选：Hook 中检测 subagent 相关事件做增量 |
| 会话/错误 | 文件 `sessions/*.jsonl` | 不变 |
| API 异常 | 文件 `model-failures.log` | 不变 |
| 工作流 | 文件 `workflow_state.json` | 不变 |

**实现**：
1. 插件注册 `tool_result_persist`，将事件写入 SQLite/JSON 或通过 WebSocket 直接推给 Dashboard。
2. Dashboard 后端：新增「活动流」API，从插件写入的存储读取；其余 API 继续读文件。
3. 前端：新增「实时活动」卡片（类似 ActivityClaw），与现有工位视图、协作流程、API 状态并列。

**优点**：信息面更全、实时性更好，且与 ActivityClaw 思路一致。  
**缺点**：需要维护两套数据源（Hook + 文件），但逻辑清晰可拆分。

---

## 四、迁移路径建议

### 阶段 1：短期（1–2 周）—— 不改架构

1. **缩短轮询**：`autoRefreshSeconds` 改为 5 秒，`pollingInterval` 改为 10 秒。
2. **文件监听**：引入 `watchdog`，监听 `runs.json`、`sessions/*.jsonl`、`task_history.json`、`model-failures.log`。
3. **WebSocket 推送**：文件变更时调用 `broadcast_*`，推送增量或全量状态。

**交付**：实时性明显提升，无需改 OpenClaw 或插件化。

---

### 阶段 2：中期（2–4 周）—— 插件外壳

1. 创建 `openclaw-agent-dashboard` 插件包，包含 `openclaw.plugin.json` 和 `index.js`。
2. 插件启动时：启动你的 FastAPI、注入 `OPENCLAW_HOME` 等环境变量。
3. 打包：将 Python 后端 + 前端 dist 打包进插件目录，或通过 `pip install` 安装后由插件调用。

**交付**：`openclaw plugins install` 后即可使用，Dashboard 随 OpenClaw 启动。

---

### 阶段 3：长期（可选）—— 混合数据源

1. 在插件中注册 `tool_result_persist`，将事件写入 `~/.openclaw/dashboard/activity_stream.json` 或 SQLite。
2. 后端新增 `/api/activity-stream`，从该存储读取。
3. 前端新增「实时活动」模块，展示工具调用流。

**交付**：既有宽信息面，又有 ActivityClaw 级别的工具调用实时性。

---

## 五、技术要点

### 5.1 插件 `openclaw.plugin.json` 示例

```json
{
  "id": "openclaw-agent-dashboard",
  "name": "OpenClaw Agent Dashboard",
  "description": "多 Agent 可视化看板 - 状态、任务、API、工作流",
  "version": "1.0.0",
  "configSchema": {
    "type": "object",
    "properties": {
      "port": { "type": "number", "default": 8000 },
      "openclawHome": { "type": "string" }
    }
  }
}
```

### 5.2 插件入口 `index.js` 核心逻辑

```javascript
function DashboardPlugin(api) {
  const config = api.config || {};
  const port = config.port ?? 8000;
  const openclawHome = config.openclawHome || require('path').join(require('os').homedir(), '.openclaw');

  // 启动 FastAPI
  const child = require('child_process').spawn('python', [
    '-m', 'uvicorn', 'main:app',
    '--host', '0.0.0.0', '--port', port
  ], {
    env: { ...process.env, OPENCLAW_HOME: openclawHome },
    cwd: __dirname + '/dashboard'
  });

  // 可选：注册 Hook 推送工具调用
  if (typeof api.on === 'function') {
    api.on('tool_result_persist', (event, ctx) => {
      // 写入文件或通过 WebSocket 推给 Dashboard
    });
  }

  return { /* 可选：stop 时 kill child */ };
}
module.exports = DashboardPlugin;
```

### 5.3 WebSocket 与前端对接

**当前**：`RealtimeDataManager` 连接 `ws://host/ws/dashboard`，但后端是 `/ws`。需统一：
- 后端：保持 `/ws` 或改为 `/ws/dashboard`。
- 前端：`wsUrl` 与后端一致，并确保 Vite 代理 `/ws` 到后端（开发时）。

```ts
// vite.config.ts 补充
proxy: {
  '/api': { target: 'http://localhost:8000', changeOrigin: true },
  '/ws': { target: 'ws://localhost:8000', ws: true }
}
```

---

## 六、总结

| 问题 | 结论 |
|------|------|
| 能否不改架构提升实时性？ | 能。缩短轮询 + 文件监听 + WebSocket 推送。 |
| 能否做成插件？ | 能。通过插件外壳启动现有服务即可。 |
| 能否既做插件又保留现有功能？ | 能。方案 A 完全保留；方案 B 在保留基础上增加 Hook 实时数据。 |
| 推荐路径 | 阶段 1 → 阶段 2 →（可选）阶段 3。 |

---

*文档结束*
