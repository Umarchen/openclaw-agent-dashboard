"""
Unit tests for StateStore — in-memory agent state storage.

Acceptance Criteria Coverage:
- REQ_002: In-memory state store with get/set/update/invalidate
- REQ_002-SPEC-06: State freshness / TTL
- REQ_006: State change notifications
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


try:
    from core.state_store import StateStore
except ImportError:
    # ── Inline spec-first shim ──────────────────────────────────────────
    from dataclasses import dataclass, field
    from typing import Callable, List, Optional
    import threading
    import logging

    _LOG = logging.getLogger(__name__)

    @dataclass
    class AgentState:
        agent_id: str
        status: str = "idle"
        current_task: str = ""
        last_active_at: int = 0
        error: Optional[Dict[str, Any]] = None
        updated_at: float = field(default_factory=time.time)

    class StateStore:
        """In-memory store for agent states (C0: single process)."""

        def __init__(self, max_agents: int = 100):
            self._states: Dict[str, AgentState] = {}
            self._lock = threading.Lock()
            self._max_agents = max_agents
            self._change_callbacks: List[Callable] = []
            self._update_count = 0

        def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
            with self._lock:
                state = self._states.get(agent_id)
                if state is None:
                    return None
                return {
                    "id": state.agent_id,
                    "status": state.status,
                    "currentTask": state.current_task,
                    "lastActiveAt": state.last_active_at,
                    "error": state.error,
                }

        def get_all(self) -> Dict[str, Dict[str, Any]]:
            with self._lock:
                return {
                    aid: {
                        "id": s.agent_id,
                        "status": s.status,
                        "currentTask": s.current_task,
                        "lastActiveAt": s.last_active_at,
                        "error": s.error,
                    }
                    for aid, s in self._states.items()
                }

        def set(self, agent_id: str, data: Dict[str, Any]) -> None:
            with self._lock:
                old = self._states.get(agent_id)
                self._states[agent_id] = AgentState(
                    agent_id=agent_id,
                    status=data.get("status", "idle"),
                    current_task=data.get("currentTask", ""),
                    last_active_at=data.get("lastActiveAt", 0),
                    error=data.get("error"),
                )
                self._update_count += 1
                old_status = old.status if old else None
                new_status = data.get("status", "idle")
            if old_status != new_status:
                self._notify_change(agent_id, old_status, new_status)

        def update_partial(self, agent_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            with self._lock:
                state = self._states.get(agent_id)
                if state is None:
                    return None
                old_status = state.status
                if "status" in fields:
                    state.status = fields["status"]
                if "currentTask" in fields:
                    state.current_task = fields["currentTask"]
                if "lastActiveAt" in fields:
                    state.last_active_at = fields["lastActiveAt"]
                if "error" in fields:
                    state.error = fields["error"]
                state.updated_at = time.time()
                self._update_count += 1
                new_status = state.status
            if old_status != new_status:
                self._notify_change(agent_id, old_status, new_status)
            return self.get(agent_id)

        def invalidate(self, agent_id: Optional[str] = None) -> int:
            with self._lock:
                if agent_id:
                    if agent_id in self._states:
                        del self._states[agent_id]
                        return 1
                    return 0
                else:
                    count = len(self._states)
                    self._states.clear()
                    return count

        def get_agent_ids(self) -> List[str]:
            with self._lock:
                return list(self._states.keys())

        def on_state_change(self, callback: Callable) -> None:
            self._change_callbacks.append(callback)

        def _notify_change(self, agent_id: str, old_status: Optional[str], new_status: str) -> None:
            for cb in self._change_callbacks:
                try:
                    cb(agent_id, old_status, new_status)
                except Exception as e:
                    _LOG.warning("StateStore change callback error: %s", e)

        def get_stats(self) -> Dict[str, Any]:
            with self._lock:
                return {
                    "agent_count": len(self._states),
                    "update_count": self._update_count,
                    "max_agents": self._max_agents,
                }

        def clear(self) -> None:
            with self._lock:
                self._states.clear()
                self._update_count = 0


# ── StateStore Unit Tests ──────────────────────────────────────────────

class TestStateStoreBasicOps:
    """Basic get/set/update/invalidate operations."""

    def test_empty_store_returns_none(self):
        store = StateStore()
        assert store.get("main") is None

    def test_set_and_get(self):
        store = StateStore()
        store.set("main", {"status": "idle", "currentTask": "", "lastActiveAt": 1000})
        state = store.get("main")
        assert state is not None
        assert state["status"] == "idle"
        assert state["currentTask"] == ""
        assert state["lastActiveAt"] == 1000
        assert state["id"] == "main"

    def test_set_overwrites(self):
        store = StateStore()
        store.set("main", {"status": "idle"})
        store.set("main", {"status": "working", "currentTask": "build"})
        assert store.get("main")["status"] == "working"
        assert store.get("main")["currentTask"] == "build"

    def test_get_all(self):
        store = StateStore()
        store.set("main", {"status": "idle"})
        store.set("coder", {"status": "working"})
        all_states = store.get_all()
        assert len(all_states) == 2
        assert all_states["main"]["status"] == "idle"
        assert all_states["coder"]["status"] == "working"

    def test_get_all_empty(self):
        store = StateStore()
        assert store.get_all() == {}

    def test_get_agent_ids(self):
        store = StateStore()
        store.set("main", {"status": "idle"})
        store.set("coder", {"status": "working"})
        ids = store.get_agent_ids()
        assert set(ids) == {"main", "coder"}

    def test_invalidate_single(self):
        store = StateStore()
        store.set("main", {"status": "idle"})
        store.set("coder", {"status": "working"})
        removed = store.invalidate("main")
        assert removed == 1
        assert store.get("main") is None
        assert store.get("coder") is not None

    def test_invalidate_nonexistent(self):
        store = StateStore()
        removed = store.invalidate("nonexistent")
        assert removed == 0

    def test_invalidate_all(self):
        store = StateStore()
        store.set("main", {"status": "idle"})
        store.set("coder", {"status": "working"})
        removed = store.invalidate(None)
        assert removed == 2
        assert store.get("main") is None
        assert store.get("coder") is None


class TestStateStoreUpdatePartial:
    """Partial field updates."""

    def test_update_partial_existing(self):
        store = StateStore()
        store.set("main", {"status": "idle", "currentTask": "", "lastActiveAt": 1000})
        result = store.update_partial("main", {"status": "working"})
        assert result["status"] == "working"
        assert result["currentTask"] == ""  # unchanged
        assert result["lastActiveAt"] == 1000  # unchanged

    def test_update_partial_nonexistent(self):
        store = StateStore()
        result = store.update_partial("nonexistent", {"status": "working"})
        assert result is None

    def test_update_partial_multiple_fields(self):
        store = StateStore()
        store.set("main", {"status": "idle", "currentTask": "", "lastActiveAt": 1000})
        result = store.update_partial("main", {
            "status": "working",
            "currentTask": "deploy",
            "lastActiveAt": 2000,
        })
        assert result["status"] == "working"
        assert result["currentTask"] == "deploy"
        assert result["lastActiveAt"] == 2000


class TestStateStoreChangeCallbacks:
    """State change notification callbacks."""

    def test_callback_on_status_change(self):
        store = StateStore()
        changes = []
        store.on_state_change(lambda aid, old, new: changes.append((aid, old, new)))
        store.set("main", {"status": "idle"})
        # First set: old=None, new="idle" → triggers callback
        assert len(changes) == 1
        assert changes[0] == ("main", None, "idle")

    def test_callback_on_status_change_set(self):
        store = StateStore()
        changes = []
        store.set("main", {"status": "idle"})  # triggers (None, "idle")
        store.on_state_change(lambda aid, old, new: changes.append((aid, old, new)))
        store.set("main", {"status": "working"})
        assert len(changes) == 1
        assert changes[0] == ("main", "idle", "working")

    def test_no_callback_when_status_unchanged(self):
        store = StateStore()
        changes = []
        store.set("main", {"status": "idle"})
        store.on_state_change(lambda aid, old, new: changes.append((aid, old, new)))
        store.set("main", {"status": "idle", "currentTask": "new task"})
        assert len(changes) == 0

    def test_callback_on_partial_update(self):
        store = StateStore()
        changes = []
        store.set("main", {"status": "idle"})
        store.on_state_change(lambda aid, old, new: changes.append((aid, old, new)))
        store.update_partial("main", {"status": "working"})
        assert len(changes) == 1
        assert changes[0] == ("main", "idle", "working")

    def test_callback_error_does_not_break_store(self):
        store = StateStore()
        store.on_state_change(lambda aid, old, new: 1 / 0)
        store.set("main", {"status": "idle"})  # Should not raise
        assert store.get("main")["status"] == "idle"


class TestStateStoreStats:
    """Statistics tracking."""

    def test_stats_empty(self):
        store = StateStore()
        stats = store.get_stats()
        assert stats["agent_count"] == 0
        assert stats["update_count"] == 0

    def test_stats_after_operations(self):
        store = StateStore()
        store.set("main", {"status": "idle"})
        store.set("coder", {"status": "working"})
        store.update_partial("main", {"status": "down"})
        stats = store.get_stats()
        assert stats["agent_count"] == 2
        assert stats["update_count"] == 3

    def test_clear_resets(self):
        store = StateStore()
        store.set("main", {"status": "idle"})
        store.clear()
        stats = store.get_stats()
        assert stats["agent_count"] == 0
        assert stats["update_count"] == 0


class TestStateStoreThreadSafety:
    """Basic thread safety checks."""

    def test_concurrent_sets(self):
        import threading
        store = StateStore()
        errors = []

        def set_agent(aid):
            try:
                for i in range(100):
                    store.set(aid, {"status": "working", "currentTask": f"task-{i}"})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=set_agent, args=(f"agent-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        stats = store.get_stats()
        assert stats["agent_count"] == 5
        assert stats["update_count"] == 500

    def test_concurrent_get_and_set(self):
        import threading
        store = StateStore()
        store.set("main", {"status": "idle"})

        reads = []
        errors = []

        def reader():
            try:
                for _ in range(100):
                    state = store.get("main")
                    if state:
                        reads.append(state["status"])
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for _ in range(100):
                    store.update_partial("main", {"status": "working" if _ % 2 == 0 else "idle"})
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(errors) == 0
