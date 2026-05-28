# openclaw-agent-dashboard 全局存量代码解剖

> **解剖时间**: 2026-05-28 14:50 CST
> **SA**: architect-agent
> **方法**: 汇总四份模块级解剖报告（data-readers / status-engine / watchers-and-api / api-others+core），不读取原始源码
> **产出路径**: `.staging/legacy_code_anatomy.md`

---

## 1. 系统全景

### 1.1 整体架构拓扑

```
┌─────────────────────────────────────────────────────────────────────┐
│                        L5 — 前端 (React SPA)                         │
│                  WebSocket 客户端 + REST 消费者                       │
└──────────────┬──────────────────────────────┬───────────────────────┘
               │  WS: full_state / state_update  │  REST: /agents, /tasks ...
               ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    L4 — api/ 路由层 (FastAPI, 16 文件)                │
│  ┌─ 核心路由 ──────────────────────────────────────────────────────┐ │
│  │ agents │ subagents │ collaboration │ performance │ timeline   │ │
│  │ websocket │ api_status │ workflow                           │ │
│  └─ 杂项路由 ──────────────────────────────────────────────────────┘ │
│  errors │ chains │ error_analysis │ debug_paths │ fortify_routes │ │
│  agents_config │ agent_config_api │ version │ input_safety        │ │
└──────────────┬──────────────────────────────┬───────────────────────┘
               │                                   │
        ┌──────┴──────┐                  ┌────────┴────────┐
        ▼             ▼                  ▼                 ▼
┌───────────────┐ ┌───────────┐  ┌──────────────────┐ ┌────────────┐
│ L3 — status/ │ │ L1 —      │  │ mechanisms       │ │ api/input │
│ (6 文件)      │ │ watchers/ │  │ (mechanism_      │ │ _safety   │
│ status_calc   │←│ (1 文件)  │  │  reader.py)     │ │ (纯校验)  │
│ status_cache  │ │ file_watch│  │ + mechanisms.py  │ └────────────┘
│ change_tracker│ │ → cache   │  │ (API 端点)       │
│ error_detector│ │   inv.    │  └───────┬─────────┘
│ cache_fp_probe│ │ → broadcast│         │
└───────┬───────┘ └─────┬─────┘         │
        │               │               │
        ▼               │               ▼
┌───────────────────────┴─────────────────────┐
│         L2 — data/ 数据读取层 (10 文件)      │
│  config_reader │ session_reader │ subagent_  │
│  timeline_reader │ chain_reader │ error_     │
│  analyzer │ agent_config_mgr │ task_history │
│  version_info_reader                        │
└───────────────────────┬─────────────────────┘
                        │
          ┌─────────────┼────────────────┐
          ▼             ▼                ▼
┌──────────────────┐ ┌───────────┐ ┌─────────────────┐
│ L0a — OpenClaw  │ │ L0b —     │ │ L0c — Dashboard │
│ 状态文件系统      │ │ utils/    │ │ 自有数据          │
│ openclaw.json    │ │ data_     │ │ task_history.json│
│ sessions.json    │ │ repair.py │ │ watcher_state   │
│ *.jsonl          │ │ schemas   │ │ cron/jobs.json   │
│ runs.json        │ │ (JSONL    │ │                 │
│ model-failures   │ │  解析/    │ │                 │
│   .log           │ │  校验/    │ │                 │
│                  │ │  修复)    │ │                 │
└──────────────────┘ └───────────┘ └─────────────────┘
       ↕
┌──────────────────────────────────────────────────────┐
│ L0d — core/ 基础设施层 (4 文件)                        │
│  error_handler │ fallback_manager │ config_fortify   │
│  logging_config │ safe_api_error (脱敏)                │
└──────────────────────────────────────────────────────┘
```

### 1.2 分层说明

| 层次 | 模块 | 文件数 | 职责 |
|------|------|--------|------|
| **L5 — 前端** | React SPA | — | WebSocket 消费 + REST 调用，渲染 Agent 状态、时序、协作图、性能面板 |
| **L4 — API 路由层** | `api/` | 16 | REST 端点 + WebSocket 管理，数据格式化与推送调度，输入校验 |
| **L3 — 状态计算层** | `status/` | 6 | Agent 状态判定（idle/working/down）、缓存（TTL+mtime 双验证）、变化 diff 检测 |
| **L2 — 数据读取层** | `data/` | 10 | 从磁盘文件读取/解析/聚合 OpenClaw 运行时数据，配置管理 |
| **L1 — 感知层** | `watchers/` | 1 | watchdog 文件监听 + 轮询降级，驱动缓存失效与状态推送 |
| **L0a — 数据源** | OpenClaw FS | — | JSON/JSONL 格式的状态文件，由 OpenClaw 运行时写入 |
| **L0b — 工具层** | `utils/` | — | JSONL 行解析、自动修复、JSON Schema 校验 |
| **L0c — 自有数据** | Dashboard FS | — | task_history.json, watcher_state.json, cron/jobs.json |
| **L0d — 基础设施** | `core/` | 4+ | 统一错误处理/重试/降级、环境配置中心、安全日志 |

### 1.3 文件总数与代码规模

| 模块 | 文件数 | 估算行数 | 复杂度 |
|------|--------|---------|--------|
| `data/` (数据读取层) | 10 | ~2,960 | 高（timeline_reader 最复杂 ~870 行） |
| `status/` (状态计算层) | 6 | ~820 | 中 |
| `api/` (路由层 — 核心 8 + 杂项 8) | 16 | ~3,680 | 中（collaboration 最重） |
| `watchers/` (感知层) | 1 | ~400 | 中 |
| `core/` (基础设施层) | 4 | ~745 | 高（error_handler ~350 行） |
| `mechanisms` (根层) | 2 | ~180 | 低 |
| **合计** | **39** | **~8,785** | |

### 1.4 技术栈

| 维度 | 技术选型 |
|------|---------|
| **后端框架** | FastAPI (Python 3.9+) |
| **文件监听** | watchdog（降级: 轮询 + 自动恢复） |
| **WebSocket** | FastAPI WebSocket |
| **线程模型** | threading（非 asyncio 协程）；`async def` 多处伪异步 |
| **缓存** | 内存 dict + TTL + mtime 指纹双验证 + 后台探针；部分端点有独立 TTL 缓存 |
| **数据源** | 纯文件 I/O（JSON/JSONL），无数据库 |
| **配置管理** | frozen dataclass + `lru_cache` + 环境变量 |
| **日志** | RotatingFileHandler + gzip 压缩 + 自动清理 + 权限加固 |
| **安全** | 输入校验（路径逃逸防御）、框架错误脱敏 |
| **前端** | React SPA |
| **可选依赖** | psutil (RSS 统计) |

---

## 2. 核心数据流（文件变更 → 前端展示完整链路）

### 2.1 完整数据流追踪

系统存在**两条并行的数据推送路径**，各自独立运作：

#### 路径 A — 文件变更驱动全量推送 (full_state)

```
OpenClaw 运行时写入 JSONL/JSON
    │
    ▼
文件系统变更 (agents/{id}/sessions/*.jsonl 或 subagents/runs.json)
    │
    ▼
watchdog FileSystemEventHandler.on_modified / on_created
    │ 过滤: 后缀 ∈ {".json", ".jsonl", ".log"} 且非目录
    │
    ▼
DebouncedHandler.trigger(filepath)          ← 1.5s 防抖
    │
    ▼
_on_file_changed(filepath)
    │
    ├── (1) status_cache.invalidate(agent_id | all)    ← 缓存失效
    │
    └── (2) asyncio.run_coroutine_threadsafe(
                broadcast_full_state(), event_loop)     ← fire-and-forget
              │
              ▼ (节流 ≥ 2.0s)
         broadcast_full_state()
              │ 串行 await 7+ 个数据源:
              │   1. get_agents()           → status_calculator → data/session_reader + data/subagent_reader
              │   2. get_subagents()        → data/subagent_reader.load_subagent_runs()
              │   3. get_api_status_list()  → data/config_reader + HTTP ping
              │   4. get_collaboration_dynamic() → data/session_reader (全量扫盘: _get_recent_model_calls)
              │   5. get_real_stats()       → data/session_reader (全量扫盘: parse_session_file)
              │   6. list_workflows()       → workflow 模块
              │   7. get_tasks()            → data/subagent_reader + data/task_history
              │
              ▼
         broadcast_message({"type": "full_state", "data": {...}})
              │ 遍历 active_connections
              ▼
         前端 WebSocket 收到完整状态快照 (7 个子域)
```

**关键特征**：
- **推送延迟**: 文件变更后最快 3.5s（1.5s 防抖 + 2.0s 节流）
- **数据量**: 全量，每次包含所有 agent 状态、子代理、协作、性能、任务等
- **计算量**: **极重** — 两个独立的全量扫盘操作（collaboration + performance）串行执行
- **无子域级变更感知**: 任何文件变更都触发全部 7 个子域重算，无法区分"仅 subagents 变了"而跳过 performance

#### 路径 B — 定时轮询增量推送 (state_update)

```
_periodic_broadcast_loop()
    │ 每 5s（空闲退避至 30s）
    ▼
get_changed_agents()                        ← status/status_calculator.py
    │
    ├── for each agent:
    │     ├── status = calculate_agent_status(agent_id)    ← 有 status_cache
    │     ├── current_task = get_current_task(agent_id)     ← 读 runs.json
    │     ├── last_active = get_last_active_time(agent_id) ← 读 sessions.json + runs.json
    │     └── tracker.update(agent_id, state_data)          ← diff 4 个字段
    │
    ▼
broadcast_state_update(changed_agents)
    │
    ▼
前端 WebSocket 收到 {"type": "state_update", "data": {agents: [...changed]}}
```

**关键特征**：
- **推送延迟**: 5-30s 周期
- **数据量**: 仅变化的 Agent（status / currentTask / lastActiveAt / error 四字段）
- **计算量**: **轻** — 遍历 Agent 列表，有 status_cache 加速
- **覆盖范围窄**: 不包含 subagents、tasks、collaboration、performance 的增量变化

#### 路径 C — REST 查询路径

```
前端 HTTP GET /agents → api/agents.get_agents()
    → asyncio.to_thread(get_agents_with_status)
        → status_calculator (缓存或文件I/O)
        → 返回 JSON

前端 HTTP GET /errors → api/errors.get_session_errors()
    → 对每个 Agent 串行调用 get_recent_messages(limit=200)
    → 全量遍历消息过滤 stopReason=error

前端 HTTP GET /errors/summary → 一次请求串行调用:
    → get_session_errors()    ← 全量扫盘 ①
    → get_model_failures()    ← parse_failure_log() ②
    → get_api_status()        ← parse_failure_log() 再次 ③
    → get_error_stats()       ← 统计计算
    ⚠️ parse_failure_log 至少被执行 2 次

前端 HTTP GET /mechanisms → mechanism_reader.get_all_agents_mechanisms()
    → 串行遍历所有 Agent，每个 Agent:
        → 读 sessions.json + openclaw.json + cron/jobs.json
    ⚠️ 全局文件（openclaw.json, cron/jobs.json）被读取 N 次
```

### 2.2 双轨制分析

| 维度 | 路径 A (full_state) | 路径 B (state_update) | 路径 C (REST) |
|------|---------------------|----------------------|---------------|
| **触发源** | 文件变更 (watchdog) | 定时轮询 (5-30s) | 客户端请求 |
| **延迟** | 3.5s+（防抖+节流） | 5-30s | 实时响应 |
| **数据量** | 7 个子域全量 | 仅 Agent 增量 diff | 按端点各异 |
| **计算量** | **极重**（全量扫盘×2） | **轻**（缓存优先） | 中→极重（/errors/summary, /mechanisms） |
| **覆盖范围** | 全维度 | 仅 agents 四字段 | 按端点 |
| **并发影响** | 高频变更时推送风暴 | 稳定可控 | 受限于请求频率 |

**设计意图推断**: 路径 A 提供全维度实时更新，路径 B 作为兜底增量推送。但两条路径存在**大量重复计算**（都调用 `calculate_agent_status`），且路径 A 的全量扫盘在高频变更场景下是性能杀手。REST 路径中 `/errors/summary` 和 `/mechanisms` 存在严重的重复 I/O。

### 2.3 数据流瓶颈节点

```
文件变更 → [1.5s 防抖] → [2.0s 节流] → 串行 7+ 数据源
                                              │
                                              ├── agents: 4-6 次 I/O × N agents     ← 🟡 串行
                                              ├── subagents: 1 次 runs.json 全量读   ← 🟡 重复读
                                              ├── apiStatus: HTTP ping               ← 🟡 阻塞
                                              ├── collaboration: 全量扫盘所有 session← 🔴 **最重**
                                              ├── performance: 全量扫盘所有 session  ← 🔴 **最重**
                                              ├── workflows: (未解剖)
                                              └── tasks: runs.json + 逐 run 读 sess ← 🟡

REST /errors/summary:
    ├── get_session_errors      ← 🔴 逐 Agent 串行 get_recent_messages
    ├── get_model_failures      ← parse_failure_log ①
    ├── get_api_status          ← parse_failure_log ② (重复!)
    └── get_error_stats         ← 统计计算

REST /mechanisms:
    └── 逐 Agent 串行           ← 🔴 openclaw.json × N 重复读取
```

---

## 3. 模块依赖矩阵

### 3.1 模块间 import/调用依赖

```
                        api/ (16 files)
                   ↙  │  │  ↘
        status/    ←   │   │   → watchers/
           ↘        ↓ │    ↙
              data/   │
             ↙  ↓  ↘ │
       core/  mechanisms
              ↓
          utils/
              ↓
          文件系统
```

**详细依赖关系**（按调用方分组）：

#### api/ 层内部调用

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| `api/websocket` | `api/agents` | `get_agents()` |
| `api/websocket` | `api/subagents` | `get_subagents()`, `get_tasks()` |
| `api/websocket` | `api/api_status` | `get_api_status_list()` |
| `api/websocket` | `api/collaboration` | `get_collaboration_dynamic()` |
| `api/websocket` | `api/performance` | `get_real_stats()` |
| `api/websocket` | `api/workflow` | `list_workflows()` |
| `api/websocket` | `status/status_calculator` | `get_changed_agents()`, `format_last_active()` |
| `api/collaboration` | `api/performance` | `parse_session_file_with_details()` |

#### api/ → status/ 依赖

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| `api/agents` | `status/status_calculator` | `get_agents_with_status()`, `format_last_active()` |
| `api/collaboration` | `status/status_calculator` | `calculate_agent_status()`, `get_current_task()`, `get_display_status()` |
| `api/errors` | `status/error_detector` | `parse_failure_log()` |
| `api/fortify_routes` | `status/status_cache` | `get_cache().get_stats()` |
| `api/websocket` | `status/status_calculator` | `get_changed_agents()` |

#### api/ → data/ 依赖

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| `api/agents` | `data/config_reader` | `agent_ids_equal()` |
| `api/agents` | `data/session_reader` | `get_session_turns()` |
| `api/subagents` | `data/subagent_reader` | `load_subagent_runs()`, `get_active_runs()` 等 |
| `api/subagents` | `data/task_history` | `merge_with_history()` |
| `api/subagents` | `data/session_reader` | session index 解析 |
| `api/collaboration` | `data/config_reader` | agents_list, models, main_agent_id |
| `api/collaboration` | `data/subagent_reader` | `get_active_runs()`, `is_agent_working()` |
| `api/collaboration` | `data/session_reader` | `has_recent_errors()`, `get_last_error()` |
| `api/performance` | `data/session_reader` | `normalize_sessions_index()` |
| `api/performance` | `data/config_reader` | `get_openclaw_root()` |
| `api/timeline` | `data/timeline_reader` | `get_timeline_steps()` |
| `api/timeline` | `data/config_reader` | `get_agent_config()` |
| `api/errors` | `data/session_reader` | `get_recent_messages()` |
| `api/errors` | `data/config_reader` | `get_agents_list()` |
| `api/chains` | `data/chain_reader` | `build_task_chains()`, `get_task_chain()` 等 |
| `api/error_analysis` | `data/error_analyzer` | `analyze_agent_errors()`, `classify_error()` 等 |
| `api/fortify_routes` | `data/session_reader` | `get_session_validation_report()` |
| `api/agents_config` | `data/config_reader` | `get_agents_list()`, `get_main_agent_id()`, `get_agent_models()` |
| `api/agent_config_api` | `data/agent_config_manager` | 全部读写操作 |
| `api/version` | `data/version_info_reader` | `read_version_info()` |

#### api/ → core/ 依赖

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| **几乎所有 api/ 文件** | `core/error_handler` | `record_error()` — 14+ 个文件导入 |
| **几乎所有 api/ 文件** | `core/safe_api_error` | `safe_api_error_detail`, `safe_client_string` — 脱敏响应 |
| `api/errors` | `core.error_handler` | `get_reliability_metrics()`, `get_framework_error_stats_for_client()` |
| `api/debug_paths` | `core/safe_api_error` | `safe_client_string()` |
| `api/fortify_routes` | `core/logging_config` | `get_logging_config_summary()` |

#### api/ → watchers/ 依赖

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| `api/fortify_routes` | `watchers/file_watcher` | `get_watcher_health()` |

#### status/ → data/ 依赖

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| `status/status_calculator` | `data/config_reader` | Agent 配置 |
| `status/status_calculator` | `data/session_reader` | 状态判定 |
| `status/status_calculator` | `data/subagent_reader` | runs 数据 |
| `status/status_cache` | `data/config_reader` | 路径计算 |
| `status/error_detector` | `data/config_reader` | workspace 路径 |

#### status/ → core/ 依赖

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| `status/status_calculator` | `core/error_handler` | 异常处理 |
| `status/status_calculator` | `core/fallback_manager` | 降级处理 |
| `status/status_cache` | `core/config_fortify` | 缓存参数 |
| `status/cache_fp_probe` | `core/config_fortify` | 配置参数 |
| `status/cache_fp_probe` | `core/error_handler` | 错误记录 |

#### watchers/ → 其他模块依赖

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| `watchers/file_watcher` | `status/status_cache` | `invalidate()` |
| `watchers/file_watcher` | `api/websocket` | `broadcast_full_state()` |
| `watchers/file_watcher` | `data/config_reader` | openclaw root |
| `watchers/file_watcher` | `data/task_history` | dashboard 数据目录 |
| `watchers/file_watcher` | `core/config_fortify` | watcher 配置 |
| `watchers/file_watcher` | `core/error_handler` | 错误记录/恢复/失败追踪 |

#### mechanisms → 其他模块依赖

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| `mechanism_reader` | `data/config_reader` | `get_openclaw_root()`, `normalize_openclaw_agent_id()` |
| `mechanism_reader` | `data/session_reader` | `normalize_sessions_index()`, `_load_sessions_index_file()` |
| `mechanisms.py` | `data/config_reader` | `get_agent_config()` |

#### core/ 内部依赖

| 调用方 | 被依赖方 | 调用内容 |
|--------|---------|---------|
| `core/error_handler` | `core/config_fortify` | `get_fortify_config()` |
| `core/error_handler` | `core/logging_config` | `setup_secure_logging()` (仅初始化) |
| `core/fallback_manager` | `core/config_fortify` | `get_fortify_config()` |
| `core/fallback_manager` | `core/error_handler` | `record_fallback_attempt()` |
| `core/fallback_manager` | `status/status_cache` | `get_stale_fallback()` |
| `core/logging_config` | `core/config_fortify` | `get_fortify_config()` |

### 3.2 循环依赖

| 循环路径 | 严重度 | 说明 |
|---------|--------|------|
| `api/websocket` → `api/agents` → `status/status_calculator` → `data/*` | 🟡 中 | websocket 通过 api 子模块间接依赖 data 层，层级穿透但非严格循环 |
| `watchers/file_watcher` → `api/websocket` → `api/collaboration` → `status/status_calculator` | 🟡 中 | 感知层直接调用推送层的具体数据构造函数，形成反向依赖 |
| `core/fallback_manager` → `status/status_cache` | 🟢 低 | core 层依赖 status 层获取降级数据，层级轻微穿透 |

**无严格的 A→B→A 模块级循环依赖**，但 `file_watcher` 直接调用 `broadcast_full_state()` 是一个**架构气味**：感知层不应直接触发推送逻辑，应有事件总线解耦。

### 3.3 耦合热点

| 热点 | 涉及模块 | 耦合原因 | 严重度 |
|------|---------|---------|--------|
| **`broadcast_full_state()` 串行调用 7 个 api 子模块** | websocket ↔ agents/subagents/collaboration/performance/workflow/tasks/api_status | 任何子模块变更都可能影响全量推送的时序和正确性 | 🔴 高 |
| **`core/error_handler.record_error()` 被 14+ 个文件导入** | 全部 api/ + status/ + watchers/ | 统一错误处理中枢的高耦合，任何异常分类/统计接口变更影响面极大 | 🟡 中 |
| **`data/config_reader` 被所有模块依赖** | 全部模块 | `load_config()` 无缓存的重复读取放大了耦合影响 | 🟡 中 |
| **`data/subagent_reader.load_subagent_runs()`** | status_calculator, subagents, collaboration, chain_reader | 无缓存的 I/O 热点被多个调用方放大 | 🔴 高 |
| **`data/session_reader` 全量 JSONL 解析函数** | status_calculator, timeline_reader, error_analyzer, performance, collaboration, errors | 无 tail 优化的全量读取函数被多处调用 | 🔴 高 |

---

## 4. 性能瓶颈全景（合并全部 4 个模块报告）

按严重程度排序：

### 🔴 P0 — 致命瓶颈（阻塞主链路，影响全局延迟）

| # | 瓶颈 | 位置 | 影响 | 根因 |
|---|------|------|------|------|
| P0-1 | **`broadcast_full_state()` 串行调用 7 个数据源** | `api/websocket.py` | 文件变更后全量推送耗时 = 各数据源耗时之和。两个独立的全量扫盘（collaboration + performance）串行执行，是**全局最大的延迟源** | 无 `asyncio.gather` 并行化 |
| P0-2 | **`get_changed_agents()` 伪异步** | `status/status_calculator.py` | 声明 `async def` 但无任何 `await`，在 asyncio 事件循环中**阻塞整个线程**，影响所有并发 WebSocket 连接 | 同步 I/O 在异步上下文中执行 |
| P0-3 | **`get_agents_with_status()` 串行 N×4-6 次 I/O** | `status/status_calculator.py` | N 个 Agent 串行执行状态计算，每次 4-6 次文件 I/O。N=10 时 40-60 次/轮，1s 轮询下每秒数十次文件读取 | 无并行化，无批量读取 |
| P0-4 | **`error_handler.run_with_retry()` 同步阻塞** | `core/error_handler.py` | 内部使用 `time.sleep()` 同步阻塞，在 async API 路由中**直接阻塞事件循环**，影响所有并发请求延迟 | 同步 sleep 在异步上下文中执行 |

### 🟠 P1 — 严重瓶颈（显著降低性能）

| # | 瓶颈 | 位置 | 影响 | 根因 |
|---|------|------|------|------|
| P1-1 | **`openclaw.json` 无缓存重复读取** | `data/config_reader.py` + `data/agent_config_manager.py` | `load_config()` 无缓存，`agent_config_manager` 独立实现一份无缓存读取。一次 API 请求可能触发 5+ 次同一文件读取 | 两套独立的读配置实现，均无缓存 |
| P1-2 | **`subagents/runs.json` 无缓存重复读取** | `data/subagent_reader.py` | `load_subagent_runs()` 无缓存，被 `get_active_runs()`、`is_agent_working()`、`get_waiting_child_agent()` 串联调用，`timeline_reader` 和 `chain_reader` 各独立调用一次 | 无 mtime/LRU 缓存 |
| P1-3 | **`_get_recent_model_calls(30)` 全量扫盘无缓存** | `api/collaboration.py` | 遍历所有 agent 所有 session 文件逐行解析，每次 `broadcast_full_state` 都触发，且 REST 端点重复调用 | 结果无缓存，与 `performance` 模块扫盘重复 |
| P1-4 | **`_compute_real_stats_sync()` 全量扫盘** | `api/performance.py` | 遍历所有 agent 所有 session 文件逐行解析，虽有 12s TTL 缓存但每次 miss 都全量重算 | 全量扫描无增量能力 |
| P1-5 | **全量 JSONL 解析函数无 tail 优化** | `data/session_reader.get_session_turns()`, `data/timeline_reader._extract_subagent_steps_from_main_session()`, `data/error_analyzer.parse_session_for_errors()` | 大 session 文件（数百 MB）全量逐行解析阻塞 | 无 offset/tail 窗口，无行数预算 |
| P1-6 | **`/errors/summary` 重复 `parse_failure_log()`** | `api/errors.py` | `get_model_failures` + `get_api_status` 各调用一次 `parse_failure_log()`，同一次请求内**至少执行 2 次全量日志解析** | 无结果共享 |
| P1-7 | **`/errors` `get_session_errors()` 串行全 Agent 扫描** | `api/errors.py` | 对每个 Agent 调用 `get_recent_messages(limit=200)` 全量遍历过滤，在 async 路由中**直接调用同步 I/O** | 串行阻塞 + 全量遍历 |
| P1-8 | **`mechanism_reader` 全局文件重复读取** | `mechanism_reader.py` | `get_all_agents_mechanisms()` 串行遍历所有 Agent，`openclaw.json` 和 `cron/jobs.json` 对每个 Agent **重复读取 N 次** | 全局文件 × N Agent，无缓存 |

### 🟡 P2 — 中等瓶颈（可优化但非阻塞）

| # | 瓶颈 | 位置 | 影响 | 根因 |
|---|------|------|------|------|
| P2-1 | **ChangeTracker.MAX_SNAPSHOTS=10 逻辑缺陷** | `status/change_tracker.py` | Agent 数 > 10 时旧状态快照被错误清理，增量 diff 退化为全量推送 | 快照数应等于 Agent 数 |
| P2-2 | **mtime 双验证 `stat()` 风暴** | `status/status_cache.py` | 每次缓存 get/set 触发 2 次 `stat()`；后台探针对全部缓存条目做 2N 次 `stat()` | 验证频率与缓存命中率相当 |
| P2-3 | **`get_tasks()` 中 completed run 逐个读 session** | `api/subagents.py` | 每个 completed run 调用 `get_agent_output_for_run()` + `get_agent_files_for_run()`，全量遍历 session | 完成任务的 output 不再变化但仍每次读 |
| P2-4 | **`get_current_task(limit=40)` 过度加载** | `status/status_calculator.py` | 加载 40 条 run 记录仅需 1-2 条 | limit 硬编码过高 |
| P2-5 | **`analyze_all_agents_errors()` 遍历全 Agent 全量解析** | `data/error_analyzer.py` | 逐 Agent × 3 个 session 串行全量解析 | 诊断工具但无限制 |
| P2-6 | **`_run_to_task` 中 `_get_agent_name` / `_get_agent_workspace` 无缓存** | `api/subagents.py` | 每个 run 都独立读取配置文件获取 agent name | 配置不频繁变化 |
| P2-7 | **`error_handler` 锁竞争** | `core/error_handler.py` | `record_error()` 持有 `_stats_lock`，高频场景下可能成为锁竞争热点；`get_framework_error_stats()` 与 `get_reliability_metrics()` 存在潜在的锁嵌套 | 多锁场景 |
| P2-8 | **`error_detector` 全量日志解析无缓存** | `status/error_detector.py` | 每次调用全量读取所有 `model-failures.log` | 无 TTL 缓存 |
| P2-9 | **`get_task_chain(chain_id)` 全量构建后过滤** | `data/chain_reader.py` | `build_task_chains(limit=100)` 全量构建后再 O(N) 过滤，只为找一个 | 无索引结构 |

### 🟢 P3 — 低优先级

| # | 瓶颈 | 位置 | 影响 |
|---|------|------|------|
| P3-1 | `new_state.copy()` 无谓深拷贝 | `change_tracker.py` | 微小内存开销 |
| P3-2 | `__init__.py` 空导出 | data/, status/ | 模块边界不清晰 |
| P3-3 | 裸 `except: pass` 吞异常 | `status/error_detector.py` | 调试困难 |
| P3-4 | 硬编码模型正则 | `status/error_detector.py` | 新增模型需改代码 |
| P3-5 | `_CompressedRotatingFileHandler.rotate()` 同步 gzip | `core/logging_config.py` | 大日志文件轮转时短暂阻塞 |
| P3-6 | `_stats.hourly_trend` 线性扫描 | `core/error_handler.py` | O(24) 查找 bucket，影响极小 |
| P3-7 | `_get_session_message_count` / `_extract_subtasks_from_session` 逐行解析 | `api/subagents.py` | 文件 I/O 已发生但事件数有限制（50） |

---

## 5. 可复用资产清单

### 5.1 ChangeTracker → 通用 StateDiff 引擎

**当前实现**: `status/change_tracker.py` — 纯内存字典，比较 4 个字段（status, currentTask, lastActiveAt, error），支持 `MAX_SNAPSHOTS=10` LRU 淘汰。

**可复用性评估**:
- ✅ **核心 diff 逻辑可直接复用**: 字段级比较、变化检测、changed 集合管理的设计模式正确
- ⚠️ **MAX_SNAPSHOTS 需修复**: 应改为与 Agent 数量动态对齐
- 🔧 **升级方向**: 泛化为 `StateDiff[K, V]`，支持任意 key 类型和自定义比较函数
- 📦 **方案C 中的定位**: 作为 EventBus 的内部 diff 组件，或被 StateStore 的 diff-on-write 能力替代

### 5.2 StatusCache → 降级冷启动缓存

**当前实现**: `status/status_cache.py` — TTL + mtime 指纹双验证 + 容量/RSS 内存保护 + LRU 淘汰。

**可复用性评估**:
- ✅ **双验证机制（TTL + mtime）是高价值设计**: 在无数据库的场景下提供了合理的数据一致性保障
- ✅ **内存保护机制**: `_enforce_memory()` 的 RSS 估算 + 容量上限是生产级特性
- ⚠️ **探针频率需优化**: `invalidate_stale_fp_entries()` 的 2N stat() 开销在高 Agent 数场景下需降低
- 📦 **方案C 中的定位**: StateStore 冷启动阶段可复用此缓存逻辑；运行时 StateStore 通过 file_watcher 事件驱动失效后，探针机制可简化或移除

### 5.3 ErrorHandler → 统一错误处理框架

**当前实现**: `core/error_handler.py` — 异常分类（12 类）、指数退避重试、滑动窗口重试预算、进程内统计聚合、NFR-R 可靠性指标追踪。

**可复用性评估**:
- ✅ **异常分类体系完善**: 12 类异常映射（timeout/network/io-error/parsing-error 等），覆盖全面
- ✅ **滑动窗口重试预算**: `_consume_retry_budget()` 防止无限重试导致的雪崩，是生产级特性
- ✅ **NFR-R 可靠性指标**: 框架内置 error_recovery_time/fallback_success_rate/watcher_uptime 追踪
- ⚠️ **需异步化**: `run_with_retry()` 的 `time.sleep()` 必须改为 `await asyncio.sleep()`
- ⚠️ **统计持久化缺失**: 进程内 `_stats` 和 `_reliability_metrics` 重启后归零，不符合 NFR-R 的可靠性 SLA 要求
- 📦 **方案C 中的定位**: 保留为基础设施，但统计应持久化到 StateStore

### 5.4 ConfigFortify → 环境配置中心

**当前实现**: `core/config_fortify.py` — frozen dataclass（28 字段）+ `lru_cache(maxsize=1)` + 安全环境变量解析器。

**可复用性评估**:
- ✅ **设计模式优秀**: frozen dataclass 不可变 + lru_cache 单例 + 带边界校验的解析器
- ✅ **28 个配置项覆盖全面**: 缓存控制/重试策略/JSON 处理/Watcher/日志安全
- 📦 **方案C 中的定位**: 保留为基础设施，无需改造

### 5.5 DebouncedHandler → 事件防抖器

**当前实现**: `watchers/file_watcher.py` — 1.5s 窗口内多次文件变更合并为一次回调。

**可复用性评估**:
- ✅ **通用防抖设计**: 可直接复用于 EventBus 的事件防抖
- 📦 **方案C 中的定位**: 作为 EventBus 的事件处理中间件

### 5.6 watchdog → 轮询降级 + 自动恢复

**当前实现**: `watchers/file_watcher.py` — watchdog 失败时降级为轮询，每 12 个轮询周期尝试恢复，后台监控线程检查 observer 存活状态。

**可复用性评估**:
- ✅ **完整的故障降级和自愈机制**: 生产级高可用保障
- 📦 **方案C 中的定位**: 方案C 的 file watcher 可直接复用此机制

### 5.7 前端 agents_update merge 逻辑

> 注：前端代码不在本次解剖范围内，以下基于 api 层推送数据结构推断。

**当前推送数据结构**:
```json
{
  "type": "full_state",
  "data": {
    "agents": [{"id", "name", "status", "currentTask", "lastActiveAt", "error"}],
    "subagents": [...],
    "apiStatus": [...],
    "collaboration": {...},
    "tasks": [...],
    "performance": {...},
    "workflows": [...]
  }
}
```

```json
{
  "type": "state_update",
  "data": {
    "agents": [...changed agents only...],
    "timestamp": "..."
  }
}
```

**可复用评估**:
- ✅ **full_state / state_update 双轨模式**的前端 merge 逻辑可直接保留
- 🔧 **升级方向**: 方案C 拆分为多事件类型后，前端需从单一 `full_state` handler 扩展为多事件 handler
- 📦 **建议**: 保留 `full_state` 作为初始化快照，增量事件逐步替换 `state_update`

### 5.8 其他可复用组件

| 组件 | 位置 | 可复用性 | 说明 |
|------|------|---------|------|
| `_quick_envelope_timestamp_utc` 正则快速过滤 | `api/performance.py` | ✅ 高 | 避免 JSONL 逐行 json.loads 的优化技巧，可推广 |
| `mtime 启发式文件跳过` | `api/performance.py` | ✅ 中 | 基于文件 mtime 跳过旧文件，可复用于增量扫描 |
| `task_history` 持久化 | `data/task_history.py` | ✅ 中 | Dashboard 自有数据，独立于 OpenClaw |
| `version_info_reader` 缓存模式 | `data/version_info_reader.py` | ✅ 中 | 首次读盘后续缓存，低频配置读取的标准模式 |
| `normalize_openclaw_agent_id()` | `data/config_reader.py` | ✅ 高 | Agent ID 规范化工具，所有模块共用 |
| `input_safety` 输入校验 | `api/input_safety.py` | ✅ 高 | 路径逃逸防御，安全基础设施 |
| `FallbackManager` 降级注册表 | `core/fallback_manager.py` | ✅ 中 | 按错误类型注册降级 handler，策略模式 |
| `LoggingConfig` 安全日志 | `core/logging_config.py` | ✅ 中 | 轮转+压缩+清理+权限加固，NFR-S-003 |
| `ErrorHandler.execute_with_retry` 装饰器 | `core/error_handler.py` | ✅ 中 | 通用重试装饰器，需异步化 |

---

## 6. 方案C 改造影响面分析

> **[AMBIGUITY]** 本次解剖未获取到方案C的正式 PRD 或设计文档。以下分析基于四份解剖报告中各模块对"StateStore / EventBus"概念的适配评估进行汇总。**需 PM 提供方案C的具体需求定义后，本节方可作为正式改造依据。**

### 6.1 需要改造的文件清单

#### C0 — 需要重大重写/替换

| 文件 | 模块 | 改造意图 | 说明 |
|------|------|---------|------|
| `api/websocket.py` | api | **REWRITE** — 推送架构重构 | `broadcast_full_state()` 拆分为细粒度事件发布；`_periodic_broadcast_loop` 改为 EventBus consumer；`send_initial_state` 保留为初始化快照 |
| `watchers/file_watcher.py` | watchers | **REWRITE** — 感知→推送解耦 | `_on_file_changed` 不再直接调用 `broadcast_full_state`，改为事件分类发布到 EventBus |
| `data/config_reader.py` | data | **MODIFY** — 增加缓存 | `load_config()` 增加 TTL 缓存（~5s），消除重复读盘 |
| `data/subagent_reader.py` | data | **MODIFY** — 增加缓存 | `load_subagent_runs()` 增加 mtime 感知 LRU 缓存 |
| `api/errors.py` | api | **REWRITE** — 数据源切换 | `get_session_errors()` 改为 StateStore 查询；`get_model_failures()` + `get_api_status()` 共享 `parse_failure_log` 结果；`get_error_stats()` 改为 StateStore 实时聚合 |
| `mechanism_reader.py` | 根层 | **REWRITE** — 数据源切换 | `get_agent_mechanisms()` 改为从 StateStore 读取已解析的机制数据，消除全局文件重复读取 |
| `core/error_handler.py` | core | **MODIFY** — 异步化 + 持久化 | `run_with_retry()` 改为 `await asyncio.sleep()`；`record_error()` 统计持久化到 StateStore |

#### C1 — 需要中度改造

| 文件 | 模块 | 改造意图 | 说明 |
|------|------|---------|------|
| `status/status_calculator.py` | status | **MODIFY** — 数据源切换 + 真异步化 | 从直接调 data reader 改为从 StateStore 读取；`get_changed_agents()` 使用 `asyncio.to_thread` 或真正异步 I/O |
| `status/status_cache.py` | status | **MODIFY** — 适配 StateStore | 作为 StateStore 的冷启动缓存层保留，或简化为 StateStore 内部组件 |
| `status/change_tracker.py` | status | **MODIFY** — 修复 + 适配 | MAX_SNAPSHOTS 修复；适配为 EventBus 的 diff 组件或被 StateStore diff-on-write 替代 |
| `api/collaboration.py` | api | **MODIFY** — 缓存 + 扫盘优化 | `_get_recent_model_calls` 增加缓存；`get_collaboration_dynamic` 改为 EventBus 事件源 |
| `api/performance.py` | api | **MODIFY** — 增量聚合 | 全量扫盘改为 EventBus 驱动的增量聚合 |
| `api/subagents.py` | api | **MODIFY** — 缓存优化 | `completed run` 的 output/files 补充增加缓存；`_get_agent_name`/`_get_agent_workspace` 增加缓存 |
| `core/fallback_manager.py` | core | **MODIFY** — StateStore 优先 | `run_fallback()` 先查 StateStore，不可用时 fallback 到 `status_cache` |
| `api/error_analysis.py` | api | **MODIFY** — 数据源切换 | 代理目标从 `data.error_analyzer` 切换到 StateStore 查询接口 |

#### C2 — 需要小范围修改

| 文件 | 模块 | 改造意图 | 说明 |
|------|------|---------|------|
| `data/session_reader.py` | data | **MODIFY** — tail 优化 | `get_session_turns()` 等全量解析函数增加 tail 窗口/行数预算 |
| `data/timeline_reader.py` | data | **MODIFY** — tail 优化 | `_extract_subagent_steps_from_main_session()` 增加 tail 窗口 |
| `data/error_analyzer.py` | data | **MODIFY** — 增量化/缓存 | `parse_session_for_errors()` 增加行数预算；`analyze_all_agents_errors()` 增加并行化 |
| `data/chain_reader.py` | data | **MODIFY** — 查询优化 | `get_task_chain(chain_id)` 改为直接索引而非全量构建后过滤 |
| `data/agent_config_manager.py` | data | **MODIFY** — 缓存失效联动 | `save_full_config()` 写入时主动失效 `config_reader` 的缓存 |
| `status/cache_fp_probe.py` | status | **MODIFY** — 简化或移除 | StateStore 事件驱动失效后，探针可简化 |
| `status/error_detector.py` | status | **MODIFY** — 缓存 | `parse_failure_log()` 增加 TTL 缓存 |
| `api/chains.py` | api | **MODIFY** — 数据源切换 | 数据源从 `chain_reader` 切换到 StateStore |

#### C3 — 不需要改造 / 保留

| 文件 | 模块 | 说明 |
|------|------|------|
| `data/task_history.py` | data | Dashboard 自有持久化，独立于 OpenClaw 状态 |
| `data/version_info_reader.py` | data | 启动时读取一次，已有缓存 |
| `api/agents.py` | api | REST 端点保留，数据源切换后内部实现微调 |
| `api/timeline.py` | api | 已有 5s TTL 缓存，改造优先级低 |
| `api/api_status.py` | api | 低频变更，保留 |
| `api/fortify_routes.py` | api | 缓存统计端点，无需改动 |
| `api/debug_paths.py` | api | 纯路径检查，无需改动 |
| `api/agents_config.py` | api | 兜底接口，低频调用 |
| `api/version.py` | api | 版本信息，无改造需求 |
| `api/input_safety.py` | api | 纯函数，安全基础设施 |
| `api/agent_config_api.py` | api | 轻量代理层，GET 走 StateStore，PUT 仍直写文件 |
| `core/config_fortify.py` | core | 环境配置中心，设计优秀无需改造 |
| `core/logging_config.py` | core | 安全日志，独立基础设施 |
| `core/safe_api_error.py` | core | 错误脱敏，独立基础设施 |
| `mechanisms.py` | 根层 | 轻量 API 代理层，数据源切换后微调 |

### 6.2 新增文件/模块建议

| 新增模块 | 职责 | 与现有代码的关系 |
|---------|------|----------------|
| `state_store.py` (或 `state/` 目录) | 集中式内存状态存储：per_agent 状态、runs 数据、timeline、错误统计、机制信息等。支持 diff-on-write、事件订阅、TTL 管理、统计持久化 | 替代 `status_cache` 的部分职责，作为 `data/readers` 的高频查询缓存，承载 `error_handler` 的可靠性统计 |
| `event_bus.py` (或 `events/` 目录) | 事件总线：事件发布/订阅/分类/路由。支持事件类型分类（agent_session_changed、run_changed、task_completed、collaboration_changed、performance_tick 等） | 解耦 `file_watcher` 与 `websocket`，使感知层只发布事件、推送层只消费事件 |
| `ingest/` (目录) | 文件变更的增量解析层：监听 JSONL 追加，提取事件写入 StateStore，避免全量扫盘 | 与 `watchers/file_watcher` 协作，接管 JSONL 的增量解析逻辑；替代 `performance` 和 `collaboration` 的全量扫盘 |

### 6.3 接口变更点

| 变更点 | 当前接口 | 变更后接口 | 影响范围 |
|--------|---------|-----------|---------|
| **WebSocket 消息协议** | `full_state` (7 子域) + `state_update` (agents diff) | 初始化: `full_state`; 增量: `agents_updated`, `subagents_updated`, `tasks_updated`, `performance_updated` 等细粒度事件 | **前端必须适配** — 从单一 `full_state` handler 扩展为多事件 handler |
| **`broadcast_full_state()`** | 串行调用 7 个数据源 | 保留为初始化/恢复快照接口，使用 `asyncio.gather` 并行化；日常推送拆分为细粒度事件 | api 内部重构 |
| **`get_changed_agents()`** | 伪异步，返回 changed agents 列表 | 真正异步化 (`asyncio.to_thread`)；或改为 EventBus 的自动 diff-on-write | status_calculator 内部重构 |
| **`load_config()` / `load_subagent_runs()`** | 无缓存，每次读盘 | 增加 TTL/mtime 缓存，写入时主动失效 | data 层内部变更，接口签名不变 |
| **`error_handler.run_with_retry()`** | 同步 `time.sleep()` 阻塞 | `await asyncio.sleep()` 异步版本 | 所有使用 `run_with_retry` 的 API 路由 |
| **`error_handler` 统计接口** | 纯内存 `_stats` | 持久化到 StateStore，查询走 StateStore | `record_error()` + `get_framework_error_stats_for_client()` |
| **`parse_failure_log()`** | 无缓存，多处重复调用 | 增加结果缓存，或由 Ingest 层增量维护 | `api/errors.py` + `status/error_detector.py` |

### 6.4 风险点

| 风险 | 严重度 | 描述 | 缓解措施 |
|------|--------|------|---------|
| **R1 — 前端适配风险** | 🔴 高 | 细粒度事件拆分后，前端从处理单一 `full_state` 变为处理多种事件类型，任何事件遗漏会导致前端状态不一致 | 保留 `full_state` 作为初始化快照；增量事件采用渐进式替换，前端分阶段适配 |
| **R2 — error_handler 异步化影响面** | 🔴 高 | `run_with_retry()` 被 14+ 个文件使用，异步化后所有调用方必须 `await`，对同步调用方（如 file_watcher 的守护线程）需保持同步版本 | 提供同步和异步两个版本（`run_with_retry` / `await run_with_retry_async`） |
| **R3 — 数据一致性窗口增大** | 🟡 中 | StateStore 事件驱动更新后，文件变化到状态更新的延迟可能增大 | 保留 status_cache 的 mtime 双验证作为一致性校验；设置延迟告警阈值 |
| **R4 — 降级路径缺失** | 🟡 中 | StateStore 引入后若故障，当前无降级到直接文件读取的回退 | 保留 `data/session_reader` 等底层 reader 作为降级数据源，StateStore miss 时自动 fallback |
| **R5 — ChangeTracker 状态丢失** | 🟡 中 | ChangeTracker 纯内存，重启后增量推送 diff 基线丢失 | StateStore 应持久化上次状态快照，或在重启时触发一次全量推送 |
| **R6 — error_handler 统计持久化后的一致性** | 🟡 中 | 统计从进程内存迁移到 StateStore 后，写入频率需控制（高频 `record_error` 不能每次写 StateStore） | StateStore 采用批量 flush + 定时快照策略 |
| **R7 — 改造范围过大** | 🟡 中 | C0 + C1 层涉及 15 个文件重大改造，回归测试覆盖难度高 | 分阶段改造：Phase 1 缓存优化 + 异步化修复（P0/P1），Phase 2 引入 EventBus，Phase 3 引入 StateStore + Ingest |
| **R8 — 并发文件 I/O 线程安全** | 🟡 中 | `get_changed_agents()` 异步化后，同一轮询内多个 Agent 的状态计算可能产生并发文件 I/O，当前 data reader 无锁机制 | 确认线程安全或改为顺序 `await to_thread` 保持串行语义 |

---

## 附录 A: 已有的性能优化措施汇总

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
| Retry wrapper | agents.ErrorHandler.run_with_retry | 2 次重试 + 指数退避 |
| 滑动窗口重试预算 | error_handler._consume_retry_budget | 防止无限重试雪崩 |
| watchdog→polling 降级 | file_watcher._switch_to_polling | 高可用保障 |
| 自动恢复 | file_watcher._try_resume_watchdog | 每 12 轮询尝试恢复 |
| 状态持久化 | file_watcher._persist_watcher_state | 跨进程可读的健康快照 |
| 内存保护 | status_cache._enforce_memory() | RSS 估算 + 容量上限 + LRU 淘汰 |
| mtime 指纹双验证 | status_cache.get()/set() | TTL + 文件 mtime 一致性校验 |
| 后台探针补强 | status/cache_fp_probe | 周期性清理 mtime 过期缓存条目 |
| frozen dataclass 配置 | core/config_fortify | 不可变配置 + lru_cache 单例 |
| 安全日志轮转 | core/logging_config | RotatingFileHandler + gzip + 自动清理 |
| 输入安全校验 | api/input_safety | 路径逃逸防御 |
| 框架错误脱敏 | core/safe_api_error | 生产环境错误信息 redaction |

## 附录 B: 关键配置参数

| 参数 | 位置 | 值 | 说明 |
|------|------|-----|------|
| `DEBOUNCE_SECONDS` | file_watcher.py | 1.5s | 文件变更防抖 |
| `BROADCAST_INTERVAL_SEC` | websocket.py | 5s | 增量推送基准间隔 |
| `FULL_STATE_MIN_INTERVAL_SEC` | websocket.py | 2.0s | 全量推送最小间隔 |
| `_PERF_STATS_CACHE_TTL_SEC` | performance.py | 12s | 性能统计缓存 TTL |
| `_PERF_DETAILS_CACHE_TTL_SEC` | performance.py | 12s | 调用详情缓存 TTL |
| `_TIMELINE_CACHE_TTL_SEC` | timeline.py | 5s | 时序缓存 TTL |
| `MAX_SNAPSHOTS` | change_tracker.py | 10 | ChangeTracker 最大快照数 |
| 退避上限 | websocket.py | 30s | 空闲时增量推送最大间隔 |
| FortifyConfig (28 字段) | config_fortify.py | — | 缓存/重试/JSON/Watcher/日志全量配置 |

## 附录 C: 模块文件索引

| 模块 | 文件 | 估算行数 |
|------|------|---------|
| **data/** | config_reader.py | ~200 |
| | session_reader.py | ~520 |
| | subagent_reader.py | ~250 |
| | timeline_reader.py | ~870 |
| | chain_reader.py | ~250 |
| | error_analyzer.py | ~280 |
| | version_info_reader.py | ~130 |
| | task_history.py | ~150 |
| | agent_config_manager.py | ~310 |
| | \_\_init\_\_.py | 1 |
| **status/** | status_calculator.py | ~320 |
| | status_cache.py | ~230 |
| | change_tracker.py | ~110 |
| | error_detector.py | ~120 |
| | cache_fp_probe.py | ~35 |
| | \_\_init\_\_.py | 1 |
| **api/** | agents.py | ~200 (估) |
| | subagents.py | ~300 (估) |
| | collaboration.py | ~350 (估) |
| | performance.py | ~250 (估) |
| | timeline.py | ~150 (估) |
| | websocket.py | ~300 (估) |
| | api_status.py | ~100 (估) |
| | workflow.py | ~100 (估) |
| | errors.py | ~230 |
| | chains.py | ~120 |
| | error_analysis.py | ~130 |
| | debug_paths.py | ~50 |
| | fortify_routes.py | ~100 |
| | agents_config.py | ~75 |
| | agent_config_api.py | ~100 |
| | version.py | ~50 |
| | input_safety.py | ~70 |
| **watchers/** | file_watcher.py | ~400 |
| **core/** | error_handler.py | ~350 |
| | fallback_manager.py | ~85 |
| | config_fortify.py | ~120 |
| | logging_config.py | ~190 |
| | safe_api_error.py | — (未解剖) |
| **根层** | mechanisms.py | ~35 |
| | mechanism_reader.py | ~145 |
| **合计** | **39+ 文件** | **~8,785** |

---

> **[SA_SIGNOFF]** 本报告基于四份模块级解剖报告汇总而成，未直接读取原始源码。所有数据和事实均来自各模块报告。如需验证具体代码行为，需物理签章各模块报告中的发现。
>
> **[AMBIGUITY]** 第 6 节"方案C 改造影响面分析"缺少方案C的正式 PRD。当前分析为基于架构经验的推测性评估，需 PM 提供方案C 需求定义后方可作为正式设计依据。
