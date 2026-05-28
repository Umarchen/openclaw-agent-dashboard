"""
Event type definitions for the C0 event-driven architecture.

All events inherit from BaseEvent. Events are plain dataclasses (no Pydantic
dependency required in C0) for minimal overhead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class BaseEvent:
    """Common fields for all events."""
    type: str = ""
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class FileChangeEvent(BaseEvent):
    """Emitted when a watched file is created, modified, or deleted."""
    filepath: str = ""
    agent_id: Optional[str] = None
    change_type: str = "modified"  # 'created' | 'modified' | 'deleted'

    def __post_init__(self) -> None:
        if not self.type:
            self.type = "file_change"


@dataclass
class HeartbeatTickEvent(BaseEvent):
    """Emitted on each polling tick (filepath=None)."""
    source: str = "polling"  # 'watchdog' | 'polling'

    def __post_init__(self) -> None:
        if not self.type:
            self.type = "heartbeat_tick"


@dataclass
class AgentStateChangedEvent(BaseEvent):
    """Emitted when an agent's state in StateStore changes."""
    agent_id: str = ""
    status: str = "idle"
    current_task: str = ""
    last_active_at: int = 0
    error: Optional[Dict[str, Any]] = None
    changes: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.type:
            self.type = "agent_state_changed"

    def to_ws_payload(self) -> Dict[str, Any]:
        """Convert to WebSocket payload dict (camelCase for frontend)."""
        return {
            "type": "agent_state_changed",
            "data": {
                "agentId": self.agent_id,
                "status": self.status,
                "currentTask": self.current_task,
                "lastActiveAt": self.last_active_at,
                "error": self.error,
                "changes": self.changes,
                "timestamp": self.timestamp,
            },
        }


@dataclass
class FullStateSnapshotEvent(BaseEvent):
    """C1+ full state snapshot event (replaces full_state for schema-aware clients).

    Used for:
    - Bootstrap when client sends schemaVersion
    - Process restart recovery
    - schemaVersion mismatch
    """
    data: Dict[str, Any] = field(default_factory=dict)
    trigger: str = "bootstrap"  # bootstrap | reconnect | schema_mismatch
    schema_version: int = 2

    def __post_init__(self) -> None:
        if not self.type:
            self.type = "full_state_snapshot"


@dataclass
class CollaborationChangedEvent(BaseEvent):
    """C2: Emitted when collaboration data changes (agent session file change).

    Contains field-level diffs compared to the previous collaboration snapshot.
    Payload size should be < 20% of full collaboration data (AC-010-2).
    """
    diffs: List[Dict[str, Any]] = field(default_factory=list)
    # Each diff: {"field": str, "old_value": Any, "new_value": Any}

    def __post_init__(self) -> None:
        if not self.type:
            self.type = "collaboration_changed"

    def to_ws_payload(self) -> Dict[str, Any]:
        return {
            "type": "CollaborationChanged",
            "payload": {
                "diffs": self.diffs,
                "timestamp": self.timestamp,
            },
        }


@dataclass
class TaskChangedEvent(BaseEvent):
    """C2: Emitted when a task is added, updated, or removed.

    One event per task change. change can be 'added', 'updated', or 'removed'.
    Only changed tasks are included, not unchanged ones (AC-010-3).
    """
    change: str = "added"  # 'added' | 'updated' | 'removed'
    task_id: str = ""
    task_data: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.type:
            self.type = "task_changed"

    def to_ws_payload(self) -> Dict[str, Any]:
        return {
            "type": "TaskChanged",
            "payload": {
                "change": self.change,
                "taskId": self.task_id,
                "taskData": self.task_data,
                "timestamp": self.timestamp,
            },
        }


@dataclass
class PerformanceSnapshotEvent(BaseEvent):
    """C2: Emitted periodically (every 30s) as a slow channel.

    Contains current performance snapshot data. Does not follow file
    change frequency — pushed on a fixed interval (AC-010-4).
    """
    agents: Dict[str, Any] = field(default_factory=dict)
    global_stats: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.type:
            self.type = "performance_snapshot"

    def to_ws_payload(self) -> Dict[str, Any]:
        return {
            "type": "PerformanceSnapshot",
            "payload": {
                "agents": self.agents,
                "globalStats": self.global_stats,
                "timestamp": self.timestamp,
            },
        }
