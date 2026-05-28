# watchers_and_api 核心模块解剖报告

> **模块范围**: `watchers/file_watcher.py` + `api/` 下 6 个路由模块
> **解剖时间**: 2026-05-28
> **解剖方法**: 逐文件物理阅读源码 + 跨模块调用链追踪

---

## 1. 模块概述

### 1.1 职责总览

本模块集承担 **数据感知 → 状态计算 → 实时推送 → 查询服务** 的完整链路：

| 层次 | 文件 | 核心职责 |
|------|------|---------|
| 感知层 | `watchers/file_watcher.py` | 监听文件系统变更，触发缓存失效与状态推送 |
| 推送层 | `api/websocket.py` | WebSocket 连接管理、全量/增量状态广播 |
| 查询层 | `api/agents.py` | Agent 状态查询（REST） |
| 查询层 | `api/subagents.py` | 子代理运行记录与任务管理 |
| 查询层 | `api/collaboration.py` | 协作拓扑图（含全量 + 动态轻量两个端点） |
| 查询层 | `api/performance.py` | TPM/RPM 统计与调用详情钻取 |
| 查询层 | `api/timeline.py` | 会话执行时序图 |

### 1.2 外部依赖关系（`[CROSS_MODULE_DEPENDENCY]`）

```
watchers/file_watcher.py
  ├── core/config_fortify.py          # watcher 配置
  ├── core/error_handler.py           # 错误记录/恢复/失败追踪
  ├── data/config_reader.py          # openclaw 根目录、workspace 路径
  ├── data/task_history.py            # dashboard 数据目录
  ├── status/status_cache.py          # 缓存失效 [CROSS]
  └── api/websocket.py                # broadcast_full_state [CROSS]

api/websocket.py
  ├── api/agents.py                   # get_agents [CROSS]
  ├── api/subagents.py                # get_subagents, get_tasks [CROSS]
  ├── api/api_status.py               # get_api_status_list [CROSS]
  ├── api/collaboration.py            # get_collaboration / get_collaboration_dynamic [CROSS]
  ├── api/performance.py              # get_real_stats [CROSS]
  ├── api/workflow.py                 # list_workflows [CROSS]
  └── status/status_calculator.py     # get_changed_agents, format_last_active [CROSS]

api/agents.py
  ├── status/status_calculator.py    # get_agents_with_status, format_last_active [CROSS]
  ├── data/config_reader.py           # agent_ids_equal [CROSS]
  ├── data/session_reader.py          # get_session_turns [CROSS]
  └── core/error_handler.py           # ErrorHandler retry wrapper [CROSS]

api/subagents.py
  ├── data/subagent_reader.py         # load_subagent_runs, get_active_runs 等 [CROSS]
  ├── data/task_history.py            # merge_with_history [CROSS]
  ├── data/session_reader.py         # session index 解析 [CROSS]
  ├── utils/data_repair.py           # parse_session_jsonl_line [CROSS]
  └── core/error_handler.py           # record_error [CROSS]

api/collaboration.py
  ├── data/config_reader.py           # agents_list, models, main_agent_id 等 [CROSS]
  ├── data/subagent_reader.py         # get_active_runs, is_agent_working [CROSS]
  ├── data/session_reader.py         # has_recent_errors, get_last_error 等 [CROSS]
  ├── status/status_calculator.py     # calculate_agent_status, get_current_task, get_display_status [CROSS]
  └── api/performance.py              # parse_session_file_with_details [CROSS]

api/performance.py
  ├── data/session_reader.py          # normalize_sessions_index [CROSS]
  ├── data/config_reader.py           # get_openclaw_root [CROSS]
  └── utils/data_repair.py            # parse_session_jsonl_line [CROSS]

api/timeline.py
  ├── data/timeline_reader.py         # get_timeline_steps [CROSS]
  ├── data/config_reader.py           # get_agent_config [CROSS]
  └── core/error_handler.py           # record_error [CROSS]
```

---

## 2. 逐文件分析

### 2.1 `watchers/file_watcher.py` — 文件变更监听

**核心职责**: 通过 watchdog 事件监听文件变更，触发缓存失效并广播全量状态。

**关键类/函数**:

| 符号 | 类型 | 职责 |
|------|------|------|
| `DebouncedHandler` | 类 | 防抖：1.5s 内多次变更只触发一次回调 |
| `_on_file_changed(filepath)` | 函数 | 核心：缓存失效 → `broadcast_full_state()` |
| `_build_observer()` | 函数 | 构建 watchdog Observer，过滤 `.json/.jsonl/.log` 后缀 |
| `_switch_to_polling(loop)` | 函数 | watchdog 失败时降级为轮询 |
| `_try_resume_watchdog(loop)` | 函数 | 每 12 个轮询周期尝试恢复 watchdog |
| `_start_monitor_thread(loop)` | 函数 | 监控线程：每 5s 检查 observer 存活状态 |
| `start_file_watcher(loop)` | 函数 | 启动入口：watchdog 启动 → 失败重试 → 降级轮询 |
| `get_watcher_health()` | 函数 | 健康检查：含持久化快照和可靠性指标 |

**数据流**:
```
文件变更 → watchdog Handler → DebouncedHandler(1.5s) → _on_file_changed()
  → status_cache.invalidate(agent_id | all)
  → asyncio.run_coroutine_threadsafe(broadcast_full_state(), event_loop)
```

**监听目录**:
1. `openclaw/subagents/` (非递归)
2. `dashboard_data/` (非递归)
3. 各 workspace 的 `memory/` (非递归)
4. 各 agent 的 `sessions/` 目录 (非递归，但每个 agent 单独调度)

**性能热点**:
- `_on_file_changed` 通过 `asyncio.run_coroutine_threadsafe` 将 broadcast 投递到事件循环，是 **fire-and-forget** 模式，不阻塞 watchdog 线程。
- `_get_watch_dirs()` 每次调用都会遍历 `agents/` 目录，但仅在 `_build_observer` 和 `_persist_watcher_state` 中调用，频率低。
- **持久化状态**: `_persist_watcher_state()` 在模式切换、恢复、心跳时写 `watcher_state.json`，I/O 轻量（单文件 JSON）。

---

### 2.2 `api/websocket.py` — WebSocket 路由

**核心职责**: 管理 WebSocket 连接，实现全量推送（`full_state`）和增量推送（`state_update`）两条路径。

**关键函数**:

| 符号 | 类型 | 职责 |
|------|------|------|
| `websocket_endpoint` | WS handler | 连接生命周期：accept → send_initial_state → 心跳循环 |
| `send_initial_state` | async | 新连接时推送 7 个子域的全量快照 |
| `broadcast_full_state` | async | 文件变更后推送 7 个子域的全量快照（节流 2s） |
| `broadcast_state_update` | async | 仅推送变化的 Agent 列表 |
| `_periodic_broadcast_loop` | async | 周期性（5s→最大30s）检查变更并增量推送 |
| `broadcast_message` | async | 底层广播到所有连接，自动清理断开连接 |

**连接管理**:
- `active_connections: Set[WebSocket]` — 模块级全局集合
- 广播时遍历所有连接，失败自动移除
- 无连接时自动取消 `_periodic_broadcast_loop` 后台任务

**两条推送路径**:

1. **全量推送** (`full_state`): 由 `file_watcher` 触发或新连接初始化时调用
2. **增量推送** (`state_update`): 由 `_periodic_broadcast_loop` 每 5s 轮询 ChangeTracker 触发

**性能热点**:
- `FULL_STATE_MIN_INTERVAL_SEC = 2.0` — 防止高频文件变更时全量推送风暴
- `_periodic_broadcast_loop` 空闲时自动退避到 30s，降低无变更时的 CPU 消耗
- `send_initial_state` 和 `broadcast_full_state` 都串行调用 7 个数据源，是 **最大的性能瓶颈**

---

### 2.3 `api/agents.py` — Agent 状态查询

**核心职责**: REST API 提供 Agent 列表和详情。

**关键端点**:

| 路由 | 方法 | 职责 |
|------|------|------|
| `/agents` | GET | 全量 Agent 列表（含状态、最后活跃时间） |
| `/agents/{agent_id}` | GET | 单 Agent 详情（线性扫描） |
| `/agents/{agent_id}/output` | GET | Agent 最近会话的 user/assistant/toolResult 详情 |

**性能特征**:
- 所有数据获取通过 `asyncio.to_thread` 包装，不阻塞事件循环
- 使用 `ErrorHandler.run_with_retry(max_retry=2)` 做重试
- **单 Agent 查询** 是 O(n) 线性扫描（先加载全部，再匹配），当 Agent 数量多时有优化空间

---

### 2.4 `api/subagents.py` — 子代理与任务管理

**核心职责**: 子代理运行记录查询、任务列表（含历史持久化）、任务时间线。

**关键端点**:

| 路由 | 方法 | 职责 |
|------|------|------|
| `/subagents` | GET | 最近 20 个子代理运行 |
| `/subagents/active` | GET | 活跃运行 |
| `/tasks` | GET | 任务列表（runs.json + 历史合并） |
| `/tasks/{run_id}/timeline` | GET | 任务执行时间线 |

**关键辅助函数**:

| 符号 | 职责 |
|------|------|
| `_run_to_task(run)` | 将原始 run 转为任务展示格式，含进度估算、子任务提取、输出/文件收集 |
| `_calculate_progress(run)` | 基于会话消息数量估算 0-100% 进度 |
| `_get_session_message_count(key)` | 统计子 Agent session 文件中的消息数量 |
| `_extract_subtasks_from_session(key)` | 从 session 文件提取嵌套 subagent 调用 |
| `_extract_timeline_from_session(key)` | 从 session 文件提取工具调用时序（最多 50 事件） |

**性能热点**:
- `_get_session_message_count` 和 `_extract_subtasks_from_session` 都需要打开并逐行解析 session JSONL 文件
- `_run_to_task` 对每个 run 都调用 `_get_session_name`（读配置）和 `_get_agent_workspace`（读配置），**无缓存**
- `_extract_timeline_from_session` 对每个 run 打开完整 session 文件，最大 50 事件后停止，但文件 I/O 已发生
- `get_tasks()` 调用 `merge_with_history` 后再对每个历史任务补充 `output`/`generatedFiles`，**可能触发多次 session 文件读取**

---

### 2.5 `api/collaboration.py` — 协作拓扑

**核心职责**: 构建 Agent 协作关系图，包含节点（Agent/任务/模型）、边（委托/调用/模型）、活跃路径、模型调用光球。

**关键端点**:

| 路由 | 方法 | 职责 |
|------|------|------|
| `/collaboration` | GET | 全量协作图（静态拓扑 + 动态状态） |
| `/collaboration/dynamic` | GET | 仅动态数据（状态变化、光球、活跃任务） |

**关键函数**:

| 符号 | 职责 |
|------|------|
| `get_collaboration()` | 全量接口：构建节点/边/活跃路径/模型光球/层级深度/多任务并行 |
| `get_collaboration_dynamic()` | 轻量接口：仅返回状态、光球、任务，不触发整体重载 |
| `_get_recent_model_calls(30)` | 遍历所有 agent 的 session 文件，提取 30 分钟内模型调用记录 |
| `_main_agent_status_for_collaboration()` | PM 卡片状态：仅认 runs.json 活跃 run + 会话错误 |
| `_check_agent_stuck()` | 检测卡顿：>60s 无响应分析原因（等子代理/模型延迟/工具执行） |
| `_build_agent_active_tasks()` | 构建每个 Agent 的活跃任务列表 |
| `_normalize_model_id()` | session 中 model ID 规范化为 `provider/model` 格式（带模块级缓存） |

**性能热点**:
- `_get_recent_model_calls(30)` 是 **最重的操作**：遍历所有 agent 目录 → 所有 session 文件 → 逐行解析 JSONL → 过滤时间窗口。每次调用触发全量扫盘。
- `_model_mapping_cache` 是模块级缓存，但 `_get_recent_model_calls` 的结果没有缓存
- `get_collaboration()` 调用 `_get_recent_model_calls` + `get_active_runs` + `calculate_agent_status`（per agent）+ `_check_agent_stuck`（per agent，可能触发 session 读取）
- `get_collaboration_dynamic()` 同样调用 `_get_recent_model_calls`，**未缓存**

---

### 2.6 `api/performance.py` — 性能统计

**核心职责**: TPM/RPM 聚合统计、调用详情钻取、Token 分析。

**关键端点**:

| 路由 | 方法 | 职责 |
|------|------|------|
| `/performance` | GET | TPM/RPM 时间序列（20m/1h/24h） |
| `/performance/details` | GET | 柱体钻取：指定时间窗口的调用明细 |
| `/tokens/analysis` | GET | 按 Agent/Session 的 Token 汇总 + 成本估算 |

**关键函数**:

| 符号 | 职责 |
|------|------|
| `_compute_real_stats_sync()` | 同步聚合：扫所有 agent sessions → 逐行解析 → 按时间槽统计 |
| `get_real_stats()` | 异步包装 + TTL 12s 缓存 |
| `_compute_minute_details_sync()` | 柱体钻取：扫所有 session → 提取指定窗口内带详情的调用 |
| `parse_session_file_with_details()` | 解析 session 文件，提取 assistant 消息的 token/model/trigger |
| `parse_session_file()` | 轻量解析：仅提取 timestamp + tokens + is_request |

**性能优化（已有）**:
1. **TTL 缓存**: `_perf_stats_cache` 和 `_perf_details_cache` 均为 12s TTL
2. **文件 mtime 启发式**: `parse_session_file` 检查 `session_file.stat().st_mtime < time_ago`，跳过旧文件
3. **快速时间戳过滤**: `_quick_envelope_timestamp_utc` 用正则提取 envelope 时间戳，避免对远早于窗口的行执行 `json.loads`
4. **线程池**: `asyncio.to_thread` 包装所有同步计算
5. **deepcopy**: 缓存返回值使用 `copy.deepcopy` 防止外部修改污染

**性能热点**:
- `_compute_real_stats_sync` 和 `_compute_minute_details_sync` 仍然是 **全量扫盘**：遍历所有 agent 目录的所有 session 文件
- `get_tokens_analysis(range="20m")` 直接内联解析（不走缓存），与 `get_real_stats` 重复扫盘
- `parse_session_file_with_details` 维护 `id_to_msg` 字典追踪 parentId 链，大 session 文件时内存占用高

---

### 2.7 `api/timeline.py` — 会话时序

**核心职责**: Agent 会话的完整交互时序（用户消息、思考、工具调用、错误）。

**关键端点**:

| 路由 | 方法 | 职责 |
|------|------|------|
| `/timeline/{agent_id}` | GET | 完整时序（含步骤、统计、LLM 轮次分组） |
| `/timeline/{agent_id}/steps` | GET | 简化步骤列表（支持类型过滤） |
| `/timeline/{agent_id}/summary` | GET | 摘要统计 |

**性能特征**:
- TTL 5s 缓存（`_timeline_cache`），key 为 `(agent_id, session_key, limit)`
- 数据委托给 `data/timeline_reader.get_timeline_steps()`（`[CROSS_MODULE_DEPENDENCY]`，未在本次解剖范围内）
- `get_timeline_summary` 调用 `get_timeline_steps(limit=10)` 只取前 10 步获取基础信息，**设计合理**

---

## 3. 事件推送链路完整追踪

### 3.1 从 file_watcher 触发到前端收到 WebSocket 消息

```
文件系统变更 (e.g., agents/pm-agent/sessions/xxx.jsonl)
    │
    ▼
watchdog.FileSystemEventHandler.on_modified / on_created
    │ 过滤: 后缀 ∈ {".json", ".jsonl", ".log"} 且非目录
    ▼
DebouncedHandler.trigger(filepath)
    │ 防抖: 1.5s 内多次变更合并
    ▼
_on_file_changed(filepath)
    │
    ├── (1) _touch_activity() → events_processed++
    │
    ├── (2) status_cache.invalidate(agent_id | all)
    │        ├── 有 agent_id: 仅失效该 agent
    │        └── 无 agent_id (filepath 不可解析): 全量失效
    │
    └── (3) asyncio.run_coroutine_threadsafe(broadcast_full_state(), loop)
              │ fire-and-forget，不阻塞 watcher 线程
              ▼
         broadcast_full_state()  [websocket.py]
              │ 节流: FULL_STATE_MIN_INTERVAL_SEC = 2.0s
              │  ├── 2s 内重复调用 → 直接 return
              │  └── 超过 2s → 继续
              ▼
         串行调用 7 个数据源:
              1. get_agents_list()           → agents 状态
              2. get_subagents()             → 子代理运行
              3. get_api_status_list()       → API 状态
              4. get_collaboration_dynamic() → 动态协作数据
              5. get_real_stats()           → 性能统计
              6. list_workflows()           → 工作流
              7. get_tasks()                 → 任务列表
              ▼
         broadcast_message({"type": "full_state", "data": {...}})
              │ 遍历 active_connections
              ▼
         前端 WebSocket 收到完整状态快照
```

### 3.2 `full_state` 的构造路径

`send_initial_state` 和 `broadcast_full_state` 两条路径构造的 `full_state` 数据结构相同：

```
full_state.data = {
    agents:        [AgentStatus...]           ← api/agents.get_agents()
    subagents:     [SubagentRun...]           ← api/subagents.get_subagents()
    apiStatus:     [ApiStatusEntry...]        ← api/api_status.get_api_status_list()
    collaboration: CollaborationDynamic       ← api/collaboration.get_collaboration_dynamic()
    tasks:         [Task...]                  ← api/subagents.get_tasks()
    performance:   {...tpm/rpm stats}         ← api/performance.get_real_stats()
    workflows:     [Workflow...]              ← api/workflow.list_workflows()
}
```

**涉及的 data reader 和计算**:

| 子域 | Data Reader | 关键计算 |
|------|-----------|---------|
| `agents` | `status/status_calculator.get_agents_with_status()` | 遍历 agent 配置 → 读取 session 文件（mtime + 最近错误 + 最近消息） → 计算 idle/working/down |
| `subagents` | `data/subagent_reader.load_subagent_runs()` | 读取 runs.json → 解析 → 排序取 top 20 |
| `apiStatus` | `data/config_reader` + 模型探测 | 遍历配置中的模型列表 → HTTP ping 检测可达性 |
| `collaboration` (dynamic) | 同上 + `data/session_reader` | 遍历所有 agent → calculate_agent_status + check_agent_stuck + get_recent_model_calls(30) |
| `tasks` | `data/subagent_reader` + `data/task_history` | 读取 runs.json → merge_with_history → 对每个 completed run 读 session 取 output/files |
| `performance` | 遍历所有 agent session 文件 | 全量扫盘 → 逐行解析 JSONL → 按时间槽聚合 token/request |
| `workflows` | [CROSS] workflow 模块 | 未知（不在本次解剖范围） |

### 3.3 `state_update` 的构造路径

```
_periodic_broadcast_loop()
    │ 每 5s（空闲退避至 30s）
    ▼
get_changed_agents()  [status/status_calculator.py]
    │
    ├── tracker = get_tracker()         ← 全局单例 ChangeTracker
    ├── agents = get_agents_list()      ← 获取所有 agent 配置列表
    │
    └── for each agent:
           ├── status = calculate_agent_status(agent_id)   ← 有缓存（status_cache）
           ├── current_task = get_current_task(agent_id)   ← 读 session 文件
           ├── last_active = get_last_active_time(agent_id)
           ├── last_error = get_last_error(agent_id)       ← 仅 down 状态
           │
           ├── state_data = {id, name, status, currentTask, lastActiveAt, error}
           │
           └── tracker.update(agent_id, state_data)
                  │ 比较关键字段:
                  │   status / currentTask / lastActiveAt / error
                  ├── 有变化 → changed_agents.append(state_data)
                  └── 无变化 → 跳过
    │
    ▼
tracker.clear_changes()
    ▼
broadcast_state_update(changed_agents)
    │
    └── broadcast_message({
           "type": "state_update",
           "data": { agents: changed_agents, timestamp: ... }
       })
```

**ChangeTracker 工作原理**:
- 单例模式，全局维护 `_last_states: Dict[str, Dict]`（最多 10 个快照，LRU 淘汰）
- `update()` 比较新旧状态的 4 个关键字段：`status`, `currentTask`, `lastActiveAt`, `error`（bool）
- 变化时将 agent_id 加入 `_changed_agents` 集合
- `clear_changes()` 在每次轮询后清空

### 3.4 两者触发条件和性能差异

| 维度 | `full_state` | `state_update` |
|------|-------------|----------------|
| **触发源** | 文件变更（watchdog/轮询）或新 WS 连接 | 周期性轮询（5-30s） |
| **触发频率** | 依赖文件变更频率，节流 ≥2s | 固定周期 |
| **数据量** | 7 个子域完整数据（agents + subagents + apiStatus + collaboration + tasks + performance + workflows） | 仅变化的 agent 列表 |
| **计算量** | **重**：7 个独立数据源串行调用，其中 collaboration 和 performance 各自全量扫盘 | **轻**：遍历 agent 列表，有 status_cache 加速 |
| **推送延迟** | 文件变更后 1.5s（防抖）+ 2s（节流）= 最快 3.5s | 5-30s |
| **覆盖范围** | 全部数据维度 | 仅 agents 的 status/currentTask/lastActiveAt/error |
| **并发影响** | 高频文件变更时可能产生推送风暴（即使有节流） | 稳定可控 |

---

## 4. 问题与瓶颈

### 4.1 全量重算重推的具体触发点

| 触发点 | 位置 | 频率 | 影响 |
|--------|------|------|------|
| 文件变更广播 | `broadcast_full_state()` | 每次文件变更（≥2s 节流） | **串行调用 7 个数据源**，最重的路径 |
| 新 WS 连接 | `send_initial_state()` | 每次客户端连接 | 同上，且无节流保护 |
| 轮询模式 tick | `_start_polling_mode.tick()` | 每 `watcher_poll_interval_sec` | 走 `_on_file_changed(None)` → 全量缓存失效 → full_state |
| watchdog 恢复 | `_try_resume_watchdog()` → `_full_resync_cache_and_push()` | 每 12 个轮询周期尝试 | 全量缓存失效 + full_state |

### 4.2 串行阻塞点

1. **`broadcast_full_state` 中的 7 次串行 `await`**
   - `get_agents_list()` → `get_subagents()` → `get_api_status_list()` → `get_collaboration_dynamic()` → `get_real_stats()` → `list_workflows()` → `get_tasks()`
   - 无 `asyncio.gather` 并行化，总耗时 = 各数据源耗时之和
   - 其中 `get_collaboration_dynamic()` 内部调用 `_get_recent_model_calls(30)` 全量扫盘
   - `get_real_stats()` 内部也全量扫盘
   - **两个扫盘操作串行执行**

2. **`_get_recent_model_calls(30)` 无缓存**
   - `broadcast_full_state` 中调用 `get_collaboration_dynamic()` → `_get_recent_model_calls(30)`
   - `get_collaboration()`（REST 端点）也调用 `_get_recent_model_calls(30)`
   - 两次调用间隔 <12s 时，重复扫盘

3. **`get_collaboration()` 中的 `calculate_agent_status` 逐 agent 串行**
   - 每个 agent 调用 `calculate_agent_status` 可能读取 session 文件
   - 无并行化

### 4.3 缺乏增量能力的具体位置

1. **`full_state` 不区分变更子域**
   - 任何文件变更都触发全部 7 个子域的重算
   - 无法感知"仅 subagents 变了"而跳过 performance 重算

2. **`status_cache.invalidate()` 粒度不足**
   - 可按 agent_id 失效（如果 filepath 可解析），否则全量失效
   - 但即使按 agent_id 失效，后续的 `broadcast_full_state` 仍然重算所有 agent

3. **`state_update` 仅覆盖 agents 维度**
   - 不包含 subagents、tasks、collaboration、performance 的增量变化
   - 前端如果依赖这些维度，必须依赖 `full_state`

4. **`get_tasks()` 中对 completed run 的 output/files 补充是全量遍历**
   - 每次 `get_tasks()` 调用都对所有 completed run 调用 `get_agent_output_for_run` + `get_agent_files_for_run`
   - 即使 run 已经完成且 output 不再变化

5. **`_get_agent_name` 和 `_get_agent_workspace` 无缓存**
   - 在 `_run_to_task` 中每个 run 都调用，但 agent 配置不会频繁变化

---

## 5. 对方案C的适配分析

> 假设方案C 引入事件总线（Event Bus）架构，实现细粒度事件驱动推送。

### 5.1 文件监听应如何接入事件总线

**现状**: `file_watcher` → `cache.invalidate()` → `broadcast_full_state()`（全量）

**改造方向**:

```
file_watcher (watchdog handler)
    │ 事件分类（基于 filepath 解析）
    ▼
EventBus.publish(event_type, payload)
    │
    ├── agent_session_changed  → agent 状态重算 → agents_updated 事件
    ├── subagent_run_changed   → 子代理重算    → subagents_updated 事件
    ├── task_completed         → 任务完成      → tasks_updated 事件
    ├── collaboration_changed  → 协作状态更新  → collaboration_updated 事件
    └── performance_tick       → 性能数据更新  → performance_updated 事件
```

**关键改造点**:
1. `_on_file_changed` 不再直接调用 `broadcast_full_state`，而是发布分类事件到 EventBus
2. `_extract_agent_id_from_path` 已存在，可扩展为 `_classify_change_type(filepath)` 判断事件类型
3. `status_cache.invalidate()` 逻辑保留，但与推送解耦
4. 轮询模式可继续作为 EventBus 的消费者，而非直接触发 broadcast

### 5.2 `full_state` 如何拆分为细粒度事件

**现状 `full_state` 的 7 个子域拆分方案**:

| 子域 | 事件类型 | 数据源 | 触发条件 |
|------|---------|--------|---------|
| `agents` | `agents_updated` | `get_agents_list()` | agent session 文件变更 |
| `subagents` | `subagents_updated` | `get_subagents()` | runs.json 变更 |
| `apiStatus` | `api_status_updated` | `get_api_status_list()` | 配置变更（低频，可保留定时） |
| `collaboration` | `collaboration_updated` | `get_collaboration_dynamic()` | runs.json 或 agent session 变更 |
| `tasks` | `tasks_updated` | `get_tasks()` | runs.json 变更 |
| `performance` | `performance_updated` | `get_real_stats()` | session 文件变更（低频定时即可） |
| `workflows` | `workflows_updated` | `list_workflows()` | workflow 文件变更（低频） |

**合并策略（减少事件数量）**:
- `subagents_changed` + `tasks_changed` + `collaboration_changed` 来源相同（runs.json），可合并为 `subagent_event`
- `agents_changed` 和 `collaboration_changed` 来源部分重叠（agent session），可按需合并
- `performance` 和 `apiStatus` 变更频率低，可保留 5-30s 周期性推送

**前端适配**:
- 前端从单一 `full_state` 处理改为多事件类型处理
- 新连接初始化仍需 `full_state`（或多个初始事件的组合）
- 可考虑 "初始快照 + 增量事件" 模式：连接时发 `full_state`，后续只发细粒度事件

### 5.3 哪些 API 端点需要改造

| 端点 | 改造需求 | 优先级 | 说明 |
|------|---------|--------|------|
| `WS /ws` (websocket_endpoint) | **高** | 初始状态推送逻辑不变，增量推送改为监听 EventBus |
| `broadcast_full_state` | **高** | 拆分为多个细粒度事件发布函数；保留作为"全量快照"接口（初始化/恢复用） |
| `broadcast_state_update` | **高** | 改为 EventBus consumer，不再独立轮询 ChangeTracker |
| `GET /collaboration` | **中** | REST 端点保留，但 `_get_recent_model_calls` 需加缓存 |
| `GET /collaboration/dynamic` | **中** | 作为 EventBus 的事件源之一，结果发布到 bus |
| `GET /performance` | **中** | 保留 REST，但内部扫盘逻辑可由 EventBus 驱动的增量聚合替代 |
| `GET /tokens/analysis` | **中** | 与 `/performance` 共享扫盘结果，避免重复计算 |
| `GET /tasks` | **中** | completed run 的 output/files 补充需缓存，避免每次全量读 session |
| `GET /subagents` | **低** | 作为 EventBus 的事件源之一 |
| `GET /agents` | **低** | REST 端点保留，作为 EventBus 事件源 |
| `GET /timeline/{agent_id}` | **低** | 已有缓存，改造优先级低 |
| `GET /performance/details` | **低** | 已有缓存，改造优先级低 |

### 5.4 跨模块依赖影响

| 被依赖模块 | 影响范围 | 改造建议 |
|-----------|---------|---------|
| `status/status_calculator.py` | `get_changed_agents()` 被 WebSocket 轮询使用 | 方案C下 ChangeTracker 可能被 EventBus 内部使用，或废弃改用事件比对 |
| `status/status_cache.py` | 被 file_watcher 使用 | 保留，作为 EventBus 事件发布前的失效机制 |
| `data/subagent_reader.py` | 被 subagents/collaboration 共用 | 可能需要增加变更检测能力（e.g., runs.json 的 hash/mtime 检查） |
| `data/session_reader.py` | 被多模块共用 | 无需改造，作为底层 data reader 保持稳定 |
| `data/config_reader.py` | 被所有模块依赖 | 无需改造 |

---

## 附录 A: 关键配置参数

| 参数 | 位置 | 值 | 说明 |
|------|------|-----|------|
| `DEBOUNCE_SECONDS` | file_watcher.py | 1.5s | 文件变更防抖 |
| `BROADCAST_INTERVAL_SEC` | websocket.py | 5s | 增量推送基准间隔 |
| `FULL_STATE_MIN_INTERVAL_SEC` | websocket.py | 2.0s | 全量推送最小间隔 |
| `_PERF_STATS_CACHE_TTL_SEC` | performance.py | 12s | 性能统计缓存 TTL |
| `_PERF_DETAILS_CACHE_TTL_SEC` | performance.py | 12s | 调用详情缓存 TTL |
| `_TIMELINE_CACHE_TTL_SEC` | timeline.py | 5s | 时序缓存 TTL |
| `MAX_SNAPSHOTS` | change_tracker.py | 10 | ChangeTracker 最大快照数 |
|退避上限| websocket.py | 30s | 空闲时增量推送最大间隔 |

## 附录 B: 已有的性能优化措施汇总

| 优化 | 位置 | 效果 |
|------|------|------|
| Debounce 防抖 | file_watcher.DebouncedHandler | 1.5s 内多次文件变更合并 |
| Full-state 节流 | websocket.broadcast_full_state | ≥2s 最小间隔 |
| 空闲退避 | websocket._periodic_broadcast_loop | 无变更时拉长至 30s |
| TTL 缓存 | performance._perf_stats_cache | 12s 避免重复扫盘 |
| TTL 缓存 | performance._perf_details_cache | 12s |
| TTL 缓存 | timeline._timeline_cache | 5s |
| mtime 启发式 | performance.parse_session_file | 跳过旧文件避免无效解析 |
| 正则快速过滤 | performance._quick_envelope_timestamp_utc | 避免对远早行的 json.loads |
| 线程池卸载 | agents/performance/timeline 的 asyncio.to_thread | 不阻塞事件循环 |
| fire-and-forget | file_watcher._on_file_changed | 不阻塞 watchdog 线程 |
| deepcopy 缓存隔离 | performance/timeline 缓存返回 | 防止外部修改污染 |
| 模型映射缓存 | collaboration._model_mapping_cache | 模块级，配置变更时清除 |
| Retry wrapper | agents.ErrorHandler.run_with_retry | 2 次重试 |
| watchdog→polling 降级 | file_watcher._switch_to_polling | 高可用保障 |
| 自动恢复 | file_watcher._try_resume_watchdog | 每 12 轮询尝试恢复 watchdog |
| 状态持久化 | file_watcher._persist_watcher_state | 跨进程可读的健康快照 |
