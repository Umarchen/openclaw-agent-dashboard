"""
EventBus — in-process publish/subscribe for C0 event-driven architecture.

Thread-safe. Synchronous dispatch (runs callbacks in publisher's thread).
No dependency on asyncio event loop.
"""
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional

from core.event_types import BaseEvent

_LOG = logging.getLogger(__name__)

# Well-known topic names
TOPIC_FILE_CHANGES = "file_changes"
TOPIC_HEARTBEAT = "heartbeat"
TOPIC_AGENT_STATE_CHANGED = "agent_state_changed"
TOPIC_STATE_UPDATES = "state_updates"


class SubscriptionHandle:
    """Opaque handle returned by subscribe(); pass to unsubscribe()."""

    __slots__ = ("id", "topic", "_bus")

    def __init__(self, topic: str, bus: EventBus) -> None:
        self.id = str(uuid.uuid4())[:8]
        self.topic = topic
        self._bus = bus


class EventBus:
    """In-process pub/sub. Thread-safe, synchronous dispatch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: Dict[str, Dict[str, Callable[[BaseEvent], None]]] = {}

    # ── public API ──────────────────────────────────────────────

    def subscribe(
        self,
        topic: str,
        callback: Callable[[BaseEvent], None],
    ) -> SubscriptionHandle:
        """Register *callback* for *topic*. Returns a handle for unsubscribe."""
        with self._lock:
            subs = self._subs.setdefault(topic, {})
            handle = SubscriptionHandle(topic, self)
            subs[handle.id] = callback
        return handle

    def unsubscribe(self, handle: SubscriptionHandle) -> None:
        """Remove a previously registered subscription."""
        with self._lock:
            topic_subs = self._subs.get(handle.topic)
            if topic_subs is not None:
                topic_subs.pop(handle.id, None)
                if not topic_subs:
                    self._subs.pop(handle.topic, None)

    def publish(self, topic: str, event: BaseEvent) -> int:
        """Dispatch *event* to all subscribers of *topic*.

        Returns the number of subscribers notified.
        Callbacks are invoked synchronously in the calling thread while
        holding no locks (the subscriber list is snapshot-ed first).
        """
        with self._lock:
            subs = self._subs.get(topic)
            if not subs:
                return 0
            callbacks = list(subs.values())

        count = 0
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                _LOG.exception("EventBus subscriber error on topic=%r", topic)
            count += 1
        return count

    def get_subscriber_count(self, topic: str) -> int:
        with self._lock:
            return len(self._subs.get(topic, {}))

    def get_topics(self) -> List[str]:
        with self._lock:
            return list(self._subs.keys())

    def clear(self) -> None:
        """Remove all subscriptions (useful for tests)."""
        with self._lock:
            self._subs.clear()


# ── module-level singleton ─────────────────────────────────────

_bus: Optional[EventBus] = None
_bus_lock = threading.Lock()


def get_event_bus() -> EventBus:
    """Return (or create) the global EventBus singleton."""
    global _bus
    if _bus is None:
        with _bus_lock:
            if _bus is None:
                _bus = EventBus()
    return _bus


def reset_event_bus_for_tests() -> None:
    global _bus
    with _bus_lock:
        if _bus is not None:
            _bus.clear()
        _bus = None
