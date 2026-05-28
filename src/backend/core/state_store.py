"""
StateStore — in-memory agent state storage for C0 event-driven architecture.

Stores per-agent state dicts. Detects changes in key fields and publishes
AgentStateChangedEvent via EventBus when changes occur.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from core.event_bus import EventBus, get_event_bus, TOPIC_AGENT_STATE_CHANGED
from core.event_types import AgentStateChangedEvent

_LOG = logging.getLogger(__name__)

# Fields tracked for change detection
_TRACKED_FIELDS = ("status", "currentTask", "lastActiveAt", "error")


class StateStore:
    """Thread-safe in-memory store for agent states.

    Publishes AgentStateChangedEvent on key field changes.
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._lock = threading.RLock()  # re-entrant for event emission
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._event_bus = event_bus or get_event_bus()
        self._change_log: List[AgentStateChangedEvent] = []
        self._change_log_max = 500

    def update_agent(self, agent_id: str, state: Dict[str, Any]) -> None:
        """Upsert agent state. Publishes event if tracked fields changed."""
        with self._lock:
            old = self._agents.get(agent_id, {})
            changes = self._detect_changes(old, state)
            self._agents[agent_id] = {**old, **state}

            if changes:
                event = AgentStateChangedEvent(
                    agent_id=agent_id,
                    status=state.get("status", old.get("status", "idle")),
                    current_task=state.get("currentTask", old.get("currentTask", "")),
                    last_active_at=state.get("lastActiveAt", old.get("lastActiveAt", 0)),
                    error=state.get("error", old.get("error")),
                    changes=changes,
                )
                self._change_log.append(event)
                if len(self._change_log) > self._change_log_max:
                    self._change_log = self._change_log[-self._change_log_max:]
                # Publish outside the scope of change detection, but still in lock
                # (RLock allows re-entrant calls if event emission triggers a callback)
                self._event_bus.publish(TOPIC_AGENT_STATE_CHANGED, event)

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._agents.get(agent_id)
            return dict(data) if data else None

    def get_all_agents(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._agents.items()}

    def remove_agent(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)

    def get_changed_since(self, since_monotonic: float) -> List[AgentStateChangedEvent]:
        """Return events for agents changed since the given monotonic timestamp."""
        with self._lock:
            return [e for e in self._change_log if _parse_monotonic(e.timestamp) > since_monotonic]

    def clear(self) -> None:
        with self._lock:
            self._agents.clear()
            self._change_log.clear()

    @staticmethod
    def _detect_changes(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, bool]:
        """Compare tracked fields between old and new state."""
        changes: Dict[str, bool] = {}
        for field in _TRACKED_FIELDS:
            old_val = old.get(field)
            new_val = new.get(field)
            if old_val != new_val:
                changes[field] = True
        return changes


def _parse_monotonic(iso_ts: str) -> float:
    """Parse ISO timestamp to approximate monotonic time (best-effort).

    For change-log filtering, we store creation time and compare roughly.
    A more precise approach would store monotonic timestamps directly.
    """
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0


# ── module-level singleton ─────────────────────────────────────

_store: Optional[StateStore] = None


def get_state_store() -> StateStore:
    global _store
    if _store is None:
        _store = StateStore()
    return _store


def reset_state_store_for_tests() -> None:
    global _store
    if _store is not None:
        _store.clear()
    _store = None
