# ECS C0 Technical Specification

## Overview

Transform the openclaw-agent-dashboard backend from a "file change → full recalculation → full_state push" architecture to an event-driven architecture with EventBus + StateStore, eliminating runtime full_state WebSocket pushes.

## Architecture

```
File Change (watchdog/polling)
    │
    ▼
FileChangeClassifier ──── FileChangeEvent
    │                           │
    ▼                           ▼
FileChangeEvent ───────► EventBus (topic: 'file_changes')
                            │
                            ▼
                    AgentStateIngestor
                    │  - tail_read (session_reader)
                    │  - fallback: calculate_agent_status (single agent)
                    ▼
                    StateStore (in-memory)
                    │  - publishes AgentStateChangedEvent
                    ▼
                    EventBus (topic: 'agent_state_changed')
                            │
                            ▼
                    WebSocket subscriber ──► WS client (agent_state_changed)

Polling tick (filepath=None)
    │
    ▼
HeartbeatTickEvent ────► EventBus (topic: 'heartbeat')
    (NO cache invalidation, NO broadcast_full_state, NO full-agent recalculation)
```

## C0 New Files (6)

| File | Purpose |
|------|---------|
| `src/backend/core/event_types.py` | Event dataclass definitions |
| `src/backend/core/event_bus.py` | In-process pub/sub |
| `src/backend/core/state_store.py` | In-memory agent state storage |
| `src/backend/core/agent_state_ingestor.py` | FileChangeEvent → StateStore pipeline |
| `src/backend/core/file_change_classifier.py` | Path → FileChangeEvent classification |
| `src/backend/core/metrics_collector.py` | Simple in-memory metrics |
| `src/backend/core/checkpoint_manager.py` | C1 placeholder (no-op) |

## C0 Modified Files (5)

| File | Changes |
|------|---------|
| `src/backend/watchers/file_watcher.py` | Remove broadcast_full_state, emit FileChangeEvent via EventBus |
| `src/backend/api/websocket.py` | Remove _periodic_broadcast_loop, add EventBus subscriber, keep bootstrap |
| `src/backend/data/session_reader.py` | Add tail_read_session() public interface |
| `src/backend/status/status_calculator.py` | Add get_agent_status_snapshot() convenience wrapper |
| `frontend/src/managers/RealtimeDataManager.ts` | Add AgentStateChanged handler (~20 lines) |

## Event Types

```python
# event_types.py

@dataclass
class BaseEvent:
    type: str
    timestamp: str  # ISO8601

@dataclass
class FileChangeEvent(BaseEvent):
    filepath: str
    agent_id: Optional[str]
    change_type: str  # 'created' | 'modified' | 'deleted'

@dataclass
class HeartbeatTickEvent(BaseEvent):
    source: str  # 'watchdog' | 'polling'

@dataclass
class AgentStateChangedEvent(BaseEvent):
    agent_id: str
    status: str
    current_task: str
    last_active_at: int
    error: Optional[dict]
    changes: dict  # { field_name: bool }
```

## WS Message Formats

### Bootstrap (unchanged)
```json
{ "type": "full_state", "data": { "agents": [...], "subagents": [...], ... } }
```

### Agent State Changed (NEW)
```json
{
  "type": "agent_state_changed",
  "data": {
    "agentId": "agent:xxx",
    "status": "working",
    "currentTask": "Reading file...",
    "lastActiveAt": 1716000000000,
    "error": null,
    "changes": { "status": true, "currentTask": true },
    "timestamp": "2024-05-18T12:00:00Z"
  }
}
```

## Key Constraints

1. **Bootstrap still sends full_state** (old format) — FullStateSnapshot protocol is C1
2. **Polling tick → HeartbeatTickEvent** — no cache invalidation, no broadcast, no full-agent recalc
3. **Ingestor fallback** — tail_read first; on failure, only single-agent calculate_agent_status()
4. **Single process** — no multi-instance/distributed concerns
5. **MetricsCollector** — simple in-memory counters, no persistence in C0

## C0 Acceptance Criteria (6 items)

1. Runtime full_state pushes = 0/min (bootstrap excluded)
2. File change → UI update p95 < 2s (including 1.5s debounce)
3. `_periodic_broadcast_loop` code completely removed from websocket.py
4. 5min polling: full_state_total delta = 0
5. Frontend AgentStateChanged → agent card incremental update
6. Ingest lag p95 < 200ms (excluding debounce)

## Task Dependency Graph

```
T1: MetricsCollector          (no deps)
T2: EventBus + Event Types   (no deps)
T6: session_reader tail_read (no deps)

T3: FileChangeClassifier     (blocked by T2)
T4: StateStore               (blocked by T2)
T11: CheckpointManager       (blocked by T4)

T5: AgentStateIngestor       (blocked by T2, T4)
T10: status_calculator expose (blocked by T5)

T7: file_watcher refactor    (blocked by T2, T3)
T8: websocket refactor       (blocked by T2)

T9: Frontend handler         (blocked by T2)

T12: Integration tests       (blocked by T7, T8, T9)
```

## Parallel Workstreams

**Stream A (backend-dev):** T1 → T2 → T3+T4 (parallel) → T5 → T10
**Stream B (backend-dev):** T6 (parallel with Stream A)
**Stream C (frontend-dev):** T9 (after T2)
**Stream D (backend-dev):** T7 (after T3), T8 (after T2), T11 (after T4)
**Stream E (qa-engineer):** T12 (after T7+T8+T9)
