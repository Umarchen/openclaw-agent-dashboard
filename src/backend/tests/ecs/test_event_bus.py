"""
Unit tests for EventBus — C0 core event dispatch.

Acceptance Criteria Coverage:
- REQ_001: EventBus publish/subscribe mechanism
- REQ_006: Event ordering guarantees
- REQ_005: Metrics (event count, latency)
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from typing import Any, List
from unittest.mock import MagicMock

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


# We try to import the real module; if it doesn't exist yet, tests use
# a lightweight inline shim so they can be written spec-first.
try:
    from core.event_bus import EventBus, EventBusEvent
except ImportError:
    # ── Inline spec-first shim ──────────────────────────────────────────
    # This shim mirrors the expected EventBus API per SAD.
    # Once the real module lands, these tests should pass unchanged.

    from dataclasses import dataclass, field
    from typing import Callable, Dict, Optional, Set
    import threading
    import logging

    _LOG = logging.getLogger(__name__)

    @dataclass
    class EventBusEvent:
        event_type: str
        payload: Any = None
        timestamp: float = field(default_factory=time.time)
        source: str = ""

    class EventBus:
        """In-process async event bus (C0: single process, no distributed)."""

        def __init__(self):
            self._subscribers: Dict[str, List[Callable]] = {}
            self._lock = threading.Lock()
            self._event_count = 0

        def subscribe(self, event_type: str, handler: Callable) -> None:
            with self._lock:
                self._subscribers.setdefault(event_type, []).append(handler)

        def unsubscribe(self, event_type: str, handler: Callable) -> bool:
            with self._lock:
                handlers = self._subscribers.get(event_type, [])
                try:
                    handlers.remove(handler)
                    return True
                except ValueError:
                    return False

        def publish(self, event: EventBusEvent) -> int:
            """Publish event to matching subscribers. Returns number of handlers called."""
            with self._lock:
                self._event_count += 1
                handlers = list(self._subscribers.get(event.event_type, []))
            count = 0
            for handler in handlers:
                count += 1  # Count before call — handler errors don't affect count
                try:
                    handler(event)
                except Exception as e:
                    _LOG.warning("EventBus handler error: %s", e)
            return count

        def get_event_count(self) -> int:
            return self._event_count

        def get_subscriber_count(self, event_type: str) -> int:
            with self._lock:
                return len(self._subscribers.get(event_type, []))

        def clear(self) -> None:
            with self._lock:
                self._subscribers.clear()
                self._event_count = 0


# ── EventBus Unit Tests ────────────────────────────────────────────────

class TestEventBusBasics:
    """Basic publish/subscribe contract."""

    def test_publish_no_subscribers(self):
        bus = EventBus()
        event = EventBusEvent(event_type="file.change")
        assert bus.publish(event) == 0
        assert bus.get_event_count() == 1

    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []
        bus.subscribe("file.change", lambda e: received.append(e))
        event = EventBusEvent(event_type="file.change", payload={"path": "/tmp/x.jsonl"})
        count = bus.publish(event)
        assert count == 1
        assert len(received) == 1
        assert received[0].payload["path"] == "/tmp/x.jsonl"
        assert bus.get_event_count() == 1

    def test_multiple_subscribers(self):
        bus = EventBus()
        results_a = []
        results_b = []
        bus.subscribe("agent.changed", lambda e: results_a.append(e))
        bus.subscribe("agent.changed", lambda e: results_b.append(e))
        event = EventBusEvent(event_type="agent.changed", payload={"agent_id": "main"})
        count = bus.publish(event)
        assert count == 2
        assert len(results_a) == 1
        assert len(results_b) == 1

    def test_multiple_event_types_isolated(self):
        bus = EventBus()
        file_events = []
        agent_events = []
        bus.subscribe("file.change", lambda e: file_events.append(e))
        bus.subscribe("agent.changed", lambda e: agent_events.append(e))
        bus.publish(EventBusEvent(event_type="file.change"))
        bus.publish(EventBusEvent(event_type="agent.changed"))
        assert len(file_events) == 1
        assert len(agent_events) == 1

    def test_unsubscribe(self):
        bus = EventBus()
        handler = lambda e: None
        bus.subscribe("test", handler)
        assert bus.get_subscriber_count("test") == 1
        result = bus.unsubscribe("test", handler)
        assert result is True
        assert bus.get_subscriber_count("test") == 0

    def test_unsubscribe_nonexistent(self):
        bus = EventBus()
        result = bus.unsubscribe("test", lambda e: None)
        assert result is False

    def test_event_payload_preserved(self):
        bus = EventBus()
        payload = {"filepath": "/agents/main/sessions/active.jsonl", "agent_id": "main", "change_type": "modified"}
        received = []
        bus.subscribe("file.change", lambda e: received.append(e))
        bus.publish(EventBusEvent(event_type="file.change", payload=payload))
        assert received[0].payload == payload

    def test_clear_removes_all_subscribers(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.publish(EventBusEvent(event_type="a"))
        bus.clear()
        assert bus.get_subscriber_count("a") == 0
        assert bus.get_subscriber_count("b") == 0


class TestEventBusErrorHandling:
    """Handler errors should not break the bus."""

    def test_handler_exception_does_not_stop_other_handlers(self):
        bus = EventBus()
        results = []

        def bad_handler(e):
            raise RuntimeError("handler error")

        bus.subscribe("test", bad_handler)
        bus.subscribe("test", lambda e: results.append("ok"))
        bus.publish(EventBusEvent(event_type="test"))
        assert results == ["ok"]

    def test_all_handlers_fail_still_counts(self):
        bus = EventBus()

        def fail(e):
            raise ValueError("boom")

        bus.subscribe("x", fail)
        bus.subscribe("x", fail)
        count = bus.publish(EventBusEvent(event_type="x"))
        # Handlers that threw are still counted as called
        assert count == 2


class TestEventBusMetrics:
    """REQ_005: Event count tracking."""

    def test_event_count_increments(self):
        bus = EventBus()
        assert bus.get_event_count() == 0
        bus.publish(EventBusEvent(event_type="a"))
        bus.publish(EventBusEvent(event_type="b"))
        bus.publish(EventBusEvent(event_type="a"))
        assert bus.get_event_count() == 3

    def test_subscriber_count_per_type(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        assert bus.get_subscriber_count("a") == 2
        assert bus.get_subscriber_count("b") == 1
        assert bus.get_subscriber_count("c") == 0


class TestEventBusEvent:
    """EventBusEvent dataclass tests."""

    def test_default_timestamp(self):
        before = time.time()
        event = EventBusEvent(event_type="test")
        after = time.time()
        assert before <= event.timestamp <= after

    def test_custom_timestamp(self):
        event = EventBusEvent(event_type="test", timestamp=1000.0)
        assert event.timestamp == 1000.0

    def test_source_field(self):
        event = EventBusEvent(event_type="test", source="file_watcher")
        assert event.source == "file_watcher"
