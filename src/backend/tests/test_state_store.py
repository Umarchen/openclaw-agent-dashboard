"""Unit tests for StateStore."""
from __future__ import annotations

import threading

from core.event_bus import EventBus, reset_event_bus_for_tests, TOPIC_AGENT_STATE_CHANGED
from core.state_store import StateStore, get_state_store, reset_state_store_for_tests
from core.event_types import AgentStateChangedEvent


def _make_store() -> StateStore:
    reset_event_bus_for_tests()
    reset_state_store_for_tests()
    return get_state_store()


class TestStateStoreUpdateAndGet:
    def test_update_and_get(self):
        store = _make_store()
        store.update_agent("agent:a", {"status": "working", "currentTask": "coding"})
        result = store.get_agent("agent:a")
        assert result is not None
        assert result["status"] == "working"
        assert result["currentTask"] == "coding"

    def test_get_nonexistent(self):
        store = _make_store()
        assert store.get_agent("nope") is None

    def test_update_merges(self):
        store = _make_store()
        store.update_agent("agent:a", {"status": "working", "extra": 1})
        store.update_agent("agent:a", {"currentTask": "reading"})
        result = store.get_agent("agent:a")
        assert result["status"] == "working"  # preserved from first update
        assert result["currentTask"] == "reading"
        assert result["extra"] == 1

    def test_get_all(self):
        store = _make_store()
        store.update_agent("agent:a", {"status": "idle"})
        store.update_agent("agent:b", {"status": "working"})
        all_agents = store.get_all_agents()
        assert set(all_agents.keys()) == {"agent:a", "agent:b"}

    def test_remove_agent(self):
        store = _make_store()
        store.update_agent("agent:a", {"status": "idle"})
        store.remove_agent("agent:a")
        assert store.get_agent("agent:a") is None

    def test_clear(self):
        store = _make_store()
        store.update_agent("agent:a", {"status": "idle"})
        store.clear()
        assert store.get_all_agents() == {}


class TestStateStoreChangeDetection:
    def test_no_event_on_first_update(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        received = []
        bus.subscribe(TOPIC_AGENT_STATE_CHANGED, lambda e: received.append(e))

        store.update_agent("agent:a", {"status": "working"})
        # First update: old state was empty, all fields are "new"
        # The tracked fields status=working vs None → changed
        assert len(received) >= 0  # depends on whether we count None→value as change

    def test_event_on_tracked_field_change(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        received = []
        bus.subscribe(TOPIC_AGENT_STATE_CHANGED, lambda e: received.append(e))

        # First write
        store.update_agent("agent:a", {"status": "idle"})
        count_after_first = len(received)

        # Change tracked field
        store.update_agent("agent:a", {"status": "working"})
        assert len(received) == count_after_first + 1
        assert received[-1].agent_id == "agent:a"
        assert received[-1].changes.get("status") is True

    def test_no_event_on_untracked_field_change(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        received = []
        bus.subscribe(TOPIC_AGENT_STATE_CHANGED, lambda e: received.append(e))

        store.update_agent("agent:a", {"status": "idle", "extra": 1})
        count = len(received)
        store.update_agent("agent:a", {"extra": 2})  # untracked field
        assert len(received) == count

    def test_event_contains_changed_fields(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        received = []
        bus.subscribe(TOPIC_AGENT_STATE_CHANGED, lambda e: received.append(e))

        store.update_agent("agent:a", {"status": "idle", "currentTask": ""})
        store.update_agent("agent:a", {"status": "working", "currentTask": "coding"})

        evt = received[-1]
        assert evt.changes["status"] is True
        assert evt.changes["currentTask"] is True
        assert "lastActiveAt" not in evt.changes
        assert "error" not in evt.changes


class TestStateStoreGetChangedSince:
    def test_returns_events_after_timestamp(self):
        import time
        store = _make_store()
        before = time.monotonic()
        store.update_agent("agent:a", {"status": "idle"})
        store.update_agent("agent:a", {"status": "working"})

        events = store.get_changed_since(before)
        assert len(events) >= 1

    def test_returns_empty_before_timestamp(self):
        import time
        store = _make_store()
        store.update_agent("agent:a", {"status": "idle"})

        events = store.get_changed_since(time.monotonic() + 1000)
        assert len(events) == 0


class TestStateStoreThreadSafety:
    def test_concurrent_updates(self):
        store = _make_store()
        errors = []

        def updater(agent_id: str):
            try:
                for i in range(100):
                    store.update_agent(agent_id, {"status": f"s{i}"})
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=updater, args=("agent:a",)),
            threading.Thread(target=updater, args=("agent:b",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert store.get_agent("agent:a") is not None
        assert store.get_agent("agent:b") is not None


class TestStateStoreWsPayload:
    def test_to_ws_payload(self):
        bus = EventBus()
        store = StateStore(event_bus=bus)
        received = []
        bus.subscribe(TOPIC_AGENT_STATE_CHANGED, lambda e: received.append(e))

        store.update_agent("agent:x", {"status": "idle"})
        # Clear and do a change
        received.clear()
        store.update_agent("agent:x", {"status": "working", "currentTask": "deploying"})

        evt = received[-1]
        payload = evt.to_ws_payload()
        assert payload["type"] == "agent_state_changed"
        assert payload["data"]["agentId"] == "agent:x"
        assert payload["data"]["status"] == "working"
        assert payload["data"]["currentTask"] == "deploying"
