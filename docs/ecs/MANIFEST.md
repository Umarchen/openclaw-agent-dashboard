# ECS Design Manifest — IDSST v4.5

> **项目**: openclaw-agent-dashboard  
> **特性**: ECS (Event-Driven ChangeStream)  
> **日期**: 2026-05-28  
> **SA**: architect-agent  

| Requirement ID | Target File (Planned) | Change Intent | Allowed Symbols |
|----------------|----------------------|---------------|-----------------|
| [REQ_ECS_001] | `src/backend/events/event_bus.py` | NEW | `EventBus`, `Event`, `FileChangeEvent`, `AgentStateChangedEvent`, `HeartbeatTickEvent`, `FullStateSnapshotEvent`, `get_event_bus` |
| [REQ_ECS_001] | `src/backend/events/__init__.py` | NEW | — |
| [REQ_ECS_001] | `src/backend/watchers/file_watcher.py` | MODIFY | `_on_file_changed` |
| [REQ_ECS_001] | `src/backend/main.py` (或等效入口) | MODIFY | lifespan 初始化代码 |
| [REQ_ECS_002] | `src/backend/events/file_change_classifier.py` | NEW | `classify_file_change`, `FileChangeEvent` |
| [REQ_ECS_003] | `src/backend/state/state_store.py` | NEW | `StateStore`, `AgentState`, `FieldDiff`, `get_state_store` |
| [REQ_ECS_003] | `src/backend/state/__init__.py` | NEW | — |
| [REQ_ECS_004] | `src/backend/ingest/agent_ingestor.py` | NEW | `AgentStateIngestor` |
| [REQ_ECS_004] | `src/backend/ingest/__init__.py` | NEW | — |
| [REQ_ECS_005] | `src/backend/api/websocket.py` | MODIFY | `websocket_endpoint`, `send_initial_state`, `broadcast_full_state`, `_ws_broadcast_event`(NEW)；C0 移除 `_periodic_broadcast_loop` 和 `broadcast_state_update()` |
| [REQ_ECS_005] | `src/backend/events/event_bus.py` | NEW | `_ws_broadcast_event` 由 WS 模块注册为 subscriber |
| [REQ_ECS_006] | `src/backend/watchers/file_watcher.py` | MODIFY | `_on_file_changed` — 移除 `broadcast_full_state` import 和调用 |
| [REQ_ECS_006] | `src/backend/api/websocket.py` | MODIFY | `broadcast_full_state` — 新增审计日志 |
| [REQ_ECS_007] | `src/backend/metrics/metrics.py` | NEW | `MetricsCollector`, `Counter`, `Histogram`, `get_metrics` |
| [REQ_ECS_007] | `src/backend/metrics/__init__.py` | NEW | — |
| [REQ_ECS_007] | `src/backend/api/metrics.py` | NEW | `router.get("/metrics")` |
| [REQ_ECS_007] | `src/backend/api/websocket.py` | MODIFY | `_ws_broadcast_event` 中记录 metrics |
| [REQ_ECS_007] | `src/backend/ingest/agent_ingestor.py` | MODIFY | `_record_ingest_lag` |
| [REQ_ECS_008] | `src/backend/ingest/checkpoint_manager.py` | NEW | `CheckpointManager` (C1) |
| [REQ_ECS_008] | `src/backend/ingest/agent_ingestor.py` | MODIFY | `_handle_agent_session` — offset-read 替代 tail-read (C1) |
| [REQ_ECS_009] | `src/backend/status/status_calculator.py` | MODIFY | `get_changed_agents` — asyncio.gather + to_thread (C1) |
| [REQ_ECS_009] | `src/backend/core/error_handler.py` | MODIFY | `run_with_retry_async` (C1) |
| [REQ_ECS_010] | `src/backend/ingest/collaboration_ingestor.py` | NEW | `CollaborationIngestor` (C2) |
| [REQ_ECS_010] | `src/backend/api/collaboration.py` | MODIFY | 拆分为独立事件源 (C2) |
| [REQ_ECS_010] | `src/backend/api/performance.py` | MODIFY | 拆分为独立慢通道 (C2) |
| [REQ_ECS_010] | `src/backend/api/websocket.py` | MODIFY | `FullStateSnapshot` 瘦身 (C2) |
| [REQ_ECS_011] | `frontend/src/managers/RealtimeDataManager.ts` | MODIFY | `handleMessage` — 统一事件处理 (C3) |
| [REQ_ECS_011] | `frontend/src/managers/StateManager.ts` | MODIFY | Patch 模型 + version 防重放 (C3) |
| [REQ_ECS_012] | `src/backend/core/config_fortify.py` | MODIFY | `FortifyConfig` — 新增 8 个 ECS 配置字段 |
| P2-1 (MAX_SNAPSHOTS 修复) | `src/backend/status/change_tracker.py` | MODIFY | `ChangeTracker.__init__` — MAX_SNAPSHOTS 提升至 50 |

---

**分期标记**: C0 = 无后缀 | C1 = (C1) | C2 = (C2) | C3 = (C3)

| session_reader 新增接口 | `src/backend/data/session_reader.py` | MODIFY | `tail_read` (C0: 新增公开接口，基于 `_read_tail_lines()` 封装) |
| C0 前端改动 | `frontend/src/managers/RealtimeDataManager.ts` | MODIFY | `handleMessage` — 新增 AgentStateChanged 处理 (C0) |

---

**总计**: NEW 12 文件 | MODIFY 13 文件 | 不动 1 文件 (status_cache.py)
- session_reader.py 从“不动”改为“修改”（C0 新增 tail_read() 公开接口）
