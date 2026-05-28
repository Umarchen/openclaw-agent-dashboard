"""
Unit tests for StateStore — in-memory agent state storage.

Acceptance Criteria Coverage:
- REQ_002: In-memory state store with update/get/get_all/remove
- REQ_006: State change notifications via EventBus
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

from core.event_bus import EventBus
from core.state_store import StateStore


# ── StateStore Unit Tests ──────────────────────────────────────────────

class TestStateStoreBasicOps:
    """Basic get/update/get_all/remove operations."""

    def test_empty_store_returns_none(self):
        store = StateStore(event_bus=EventBus())
        assert store.get_agent("main") is None

    def test_update_and_get(self):
        store = StateStore(event_bus=EventBus())
        store.update_agent("main", {"status": "idle", "currentTask": "", "lastActiveAt": 1000})
        state = store.get_agent("main")
        assert state is not None
        assert state["status"] == "idle"
        assert state["currentTask"] == ""
        assert state["lastActiveAt"] == 1000

    def test_update_merges(self):
        store = StateStore(event_bus=EventBus())
        store.update_agent("main", {"status": "idle"})
        store.update_agent("main", {"status": "working", "currentTask": "build"})
        state = store.get_agent("main")
        assert state["status"] == "working"
        assert state["currentTask"] == "build"

    def test_get_all_agents(self):
        store = StateStore(event_bus=EventBus())
        store.update_agent("main", {"status": "idle"})
        store.update_agent("coder", {"status": "working"})
        all_states = store.get_all_agents()
        assert len(all_states) == 2
        assert all_states["main"]["status"] == "idle"
        assert all_states["coder"]["status"] == "working"

    def test_get_all_agents_empty(self):
        store = StateStore(event_bus=EventBus())
        assert store.get_all_agents() == {}

    def test_get_all_agents_returns_copy(self):
        """get_all_agents returns independent copies — mutations don't affect store."""
        store = StateStore(event_bus=EventBus())
        store.update_agent("main", {"status": "idle"})
        snapshot = store.get_all_agents()
        snapshot["main"]["status"] = "hacked"
        assert store.get_agent("main")["status"] == "idle"

    def test_remove_agent(self):
        store = StateStore(event_bus=EventBus())
        store.update_agent("main", {"status": "idle"})
        store.update_agent("coder", {"status": "working"})
        store.remove_agent("main")
        assert store.get_agent("main") is None
        assert store.get_agent("coder") is not None

    def test_remove_agent_nonexistent(self):
        """Removing a nonexistent agent is a no-op."""
        store = StateStore(event_bus=EventBus())
        store.remove_agent("nonexistent")  # should not raise

    def test_clear(self):
        store = StateStore(event_bus=EventBus())
        store.update_agent("main", {"status": "idle"})
        store.update_agent("coder", {"status": "working"})
        store.clear()
        assert store.get_agent("main") is None
        assert store.get_agent("coder") is None
        assert store.get_all_agents() == {}


class TestStateStoreUpdateMerge:
    """update_agent merges partial updates with existing state."""

    def test_update_partial_existing(self):
        store = StateStore(event_bus=EventBus())
        store.update_agent("main", {"status": "idle", "currentTask": "", "lastActiveAt": 1000})
        store.update_agent("main", {"status": "working"})
        result = store.get_agent("main")
        assert result["status"] == "working"
        assert result["currentTask"] == ""  # unchanged
        assert result["lastActiveAt"] == 1000  # unchanged

    def test_update_creates_if_not_exist(self):
        """update_agent creates agent if it doesn't exist (upsert)."""
        store = StateStore(event_bus=EventBus())
        store.update_agent("new", {"status": "working"})
        result = store.get_agent("new")
        assert result is not None
        assert result["status"] == "working"

    def test_update_multiple_fields(self):
        store = StateStore(event_bus=EventBus())
        store.update_agent("main", {"status": "idle", "currentTask": "", "lastActiveAt": 1000})
        store.update_agent("main", {
            "status": "working",
            "currentTask": "deploy",
            "lastActiveAt": 2000,
        })
        result = store.get_agent("main")
        assert result["status"] == "working"
        assert result["currentTask"] == "deploy"
        assert result["lastActiveAt"] == 2000


class TestStateStoreChangeEvents:
    """State change events published via EventBus."""

    def test_event_on_status_change(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        events = []
        bus.subscribe("agent_state_changed", lambda e: events.append(e))
        store.update_agent("main", {"status": "idle"})
        # First update: from nothing → "idle" (status changed from None→"idle")
        assert len(events) == 1
        assert events[0].agent_id == "main"
        assert events[0].status == "idle"

    def test_event_on_status_change_second_update(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        store.update_agent("main", {"status": "idle"})  # triggers event
        events = []
        bus.subscribe("agent_state_changed", lambda e: events.append(e))
        store.update_agent("main", {"status": "working"})
        assert len(events) == 1
        assert events[0].status == "working"

    def test_no_event_when_all_tracked_fields_unchanged(self):
        """No event when no tracked fields (status, currentTask, lastActiveAt, error) change."""
        bus = EventBus()
        store = StateStore(event_bus=bus)
        store.update_agent("main", {"status": "idle", "currentTask": "task1", "lastActiveAt": 1000})
        events = []
        bus.subscribe("agent_state_changed", lambda e: events.append(e))
        # Update only untracked fields — should not trigger event
        store.update_agent("main", {"name": "updated", "extra": "field"})
        assert len(events) == 0

    def test_event_on_tracked_field_change(self):
        """Events fire on changes to any tracked field (status, currentTask, lastActiveAt, error)."""
        bus = EventBus()
        store = StateStore(event_bus=bus)
        store.update_agent("main", {"status": "idle"})
        events = []
        bus.subscribe("agent_state_changed", lambda e: events.append(e))
        store.update_agent("main", {"lastActiveAt": 9999})
        assert len(events) == 1
        assert events[0].changes.get("lastActiveAt") is True

    def test_event_callback_error_does_not_break_store(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        bus.subscribe("agent_state_changed", lambda e: 1 / 0)
        store.update_agent("main", {"status": "idle"})  # Should not raise
        assert store.get_agent("main")["status"] == "idle"

    def test_event_has_changes_dict(self):
        """Event includes a dict indicating which tracked fields changed."""
        bus = EventBus()
        store = StateStore(event_bus=bus)
        events = []
        bus.subscribe("agent_state_changed", lambda e: events.append(e))
        store.update_agent("main", {"status": "working", "currentTask": "build"})
        assert len(events) == 1
        assert events[0].changes == {"status": True, "currentTask": True}


class TestStateStoreGetChangedSince:
    """get_changed_since returns events newer than a monotonic timestamp."""

    def test_get_changed_since_returns_recent(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        marker = time.monotonic()
        store.update_agent("main", {"status": "working"})
        events = store.get_changed_since(marker)
        assert len(events) == 1
        assert events[0].agent_id == "main"

    def test_get_changed_since_no_events(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        store.update_agent("main", {"status": "working"})
        events = store.get_changed_since(time.monotonic() + 1000)
        assert len(events) == 0

    def test_get_changed_since_multiple(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        marker = time.monotonic()
        store.update_agent("main", {"status": "working"})
        store.update_agent("coder", {"status": "idle"})
        events = store.get_changed_since(marker)
        assert len(events) == 2

    def test_get_changed_since_excludes_unchanged(self):
        """No event for update_agent that doesn't change tracked fields."""
        bus = EventBus()
        store = StateStore(event_bus=bus)
        store.update_agent("main", {"status": "idle"})
        marker = time.monotonic()
        store.update_agent("main", {"status": "idle"})  # no tracked field change
        events = store.get_changed_since(marker)
        assert len(events) == 0

    def test_clear_empties_change_log(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        store.update_agent("main", {"status": "working"})
        store.clear()
        events = store.get_changed_since(0)
        assert len(events) == 0


class TestStateStoreThreadSafety:
    """Basic thread safety checks."""

    def test_concurrent_updates(self):
        import threading
        bus = EventBus()
        store = StateStore(event_bus=bus)
        errors = []

        def update_agent(aid):
            try:
                for i in range(100):
                    store.update_agent(aid, {"status": "working", "currentTask": f"task-{i}"})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_agent, args=(f"agent-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        assert len(store.get_all_agents()) == 5

    def test_concurrent_get_and_update(self):
        import threading
        bus = EventBus()
        store = StateStore(event_bus=bus)
        store.update_agent("main", {"status": "idle"})

        reads = []
        errors = []

        def reader():
            try:
                for _ in range(100):
                    state = store.get_agent("main")
                    if state:
                        reads.append(state["status"])
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    store.update_agent("main", {"status": "working" if i % 2 == 0 else "idle"})
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=reader)
        t2 = threading.Thread(target=writer)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(errors) == 0
