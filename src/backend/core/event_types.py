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
