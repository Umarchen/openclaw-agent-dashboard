"""Unit tests for EventBus."""
from __future__ import annotations

import threading

from core.event_bus import EventBus, SubscriptionHandle, TOPIC_FILE_CHANGES, get_event_bus, reset_event_bus_for_tests
from core.event_types import BaseEvent, FileChangeEvent, HeartbeatTickEvent


def _make() -> EventBus:
    reset_event_bus_for_tests()
    return get_event_bus()


class TestEventBusSubscribePublish:
    def test_single_subscriber(self):
        bus = _make()
        received = []
        bus.subscribe(TOPIC_FILE_CHANGES, lambda e: received.append(e))

        event = FileChangeEvent(filepath="/tmp/test.jsonl", agent_id="agent:main")
        count = bus.publish(TOPIC_FILE_CHANGES, event)

        assert count == 1
        assert len(received) == 1
        assert received[0] is event

    def test_multiple_subscribers_same_topic(self):
        bus = _make()
        r1, r2 = [], []
        bus.subscribe(TOPIC_FILE_CHANGES, lambda e: r1.append(e))
        bus.subscribe(TOPIC_FILE_CHANGES, lambda e: r2.append(e))

        event = FileChangeEvent(filepath="/tmp/x.jsonl")
        count = bus.publish(TOPIC_FILE_CHANGES, event)

        assert count == 2
        assert len(r1) == 1 and len(r2) == 1

    def test_different_topics(self):
        bus = _make()
        file_received = []
        hb_received = []
        bus.subscribe("file_changes", lambda e: file_received.append(e))
        bus.subscribe("heartbeat", lambda e: hb_received.append(e))

        bus.publish("file_changes", FileChangeEvent(filepath="/a"))
        bus.publish("heartbeat", HeartbeatTickEvent(source="polling"))

        assert len(file_received) == 1
        assert len(hb_received) == 1
        assert isinstance(file_received[0], FileChangeEvent)
        assert isinstance(hb_received[0], HeartbeatTickEvent)

    def test_publish_to_empty_topic(self):
        bus = _make()
        count = bus.publish("nonexistent", FileChangeEvent(filepath="/x"))
        assert count == 0


class TestEventBusUnsubscribe:
    def test_unsubscribe_removes_callback(self):
        bus = _make()
        received = []
        handle = bus.subscribe(TOPIC_FILE_CHANGES, lambda e: received.append(e))

        bus.publish(TOPIC_FILE_CHANGES, FileChangeEvent(filepath="/a"))
        assert len(received) == 1

        bus.unsubscribe(handle)
        bus.publish(TOPIC_FILE_CHANGES, FileChangeEvent(filepath="/b"))
        assert len(received) == 1  # no new delivery

    def test_unsubscribe_cleans_empty_topic(self):
        bus = _make()
        handle = bus.subscribe("topic_x", lambda e: None)
        assert "topic_x" in bus.get_topics()
        bus.unsubscribe(handle)
        assert "topic_x" not in bus.get_topics()

    def test_double_unsubscribe_is_safe(self):
        bus = _make()
        handle = bus.subscribe("t", lambda e: None)
        bus.unsubscribe(handle)
        bus.unsubscribe(handle)  # no error


class TestEventBusSubscriberCount:
    def test_count(self):
        bus = _make()
        assert bus.get_subscriber_count(TOPIC_FILE_CHANGES) == 0
        h1 = bus.subscribe(TOPIC_FILE_CHANGES, lambda e: None)
        assert bus.get_subscriber_count(TOPIC_FILE_CHANGES) == 1
        h2 = bus.subscribe(TOPIC_FILE_CHANGES, lambda e: None)
        assert bus.get_subscriber_count(TOPIC_FILE_CHANGES) == 2
        bus.unsubscribe(h1)
        assert bus.get_subscriber_count(TOPIC_FILE_CHANGES) == 1


class TestEventBusTopics:
    def test_get_topics(self):
        bus = _make()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        topics = bus.get_topics()
        assert set(topics) == {"a", "b"}


class TestEventBusErrorHandling:
    def test_exception_in_subscriber_doesnt_stop_others(self):
        bus = _make()
        r1 = []
        bus.subscribe("t", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.subscribe("t", lambda e: r1.append(e))

        count = bus.publish("t", FileChangeEvent(filepath="/x"))
        assert count == 2  # both attempted
        assert len(r1) == 1  # second callback still ran


class TestEventBusThreadSafety:
    def test_concurrent_subscribe_unsubscribe(self):
        bus = _make()
        errors = []

        def subscriber_thread():
            try:
                for _ in range(100):
                    handle = bus.subscribe("concurrent", lambda e: None)
                    bus.unsubscribe(handle)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=subscriber_thread) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_concurrent_publish(self):
        bus = _make()
        received = []
        bus.subscribe("pub", lambda e: received.append(1))

        def publisher():
            for _ in range(100):
                bus.publish("pub", FileChangeEvent(filepath="/x"))

        threads = [threading.Thread(target=publisher) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(received) == 400


class TestEventBusClear:
    def test_clear_removes_all(self):
        bus = _make()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        bus.clear()
        assert bus.get_topics() == []
        assert bus.get_subscriber_count("a") == 0


class TestEventTypes:
    def test_file_change_event_defaults(self):
        evt = FileChangeEvent(filepath="/tmp/test.jsonl", agent_id="agent:x")
        assert evt.type == "file_change"
        assert evt.agent_id == "agent:x"
        assert evt.change_type == "modified"
        assert evt.timestamp  # non-empty

    def test_heartbeat_event(self):
        evt = HeartbeatTickEvent(source="watchdog")
        assert evt.type == "heartbeat_tick"
        assert evt.source == "watchdog"

    def test_agent_state_changed_event_ws_payload(self):
        from core.event_types import AgentStateChangedEvent

        evt = AgentStateChangedEvent(
            agent_id="agent:main",
            status="working",
            current_task="reading file",
            last_active_at=1716000000000,
            changes={"status": True, "currentTask": True},
        )
        payload = evt.to_ws_payload()
        assert payload["type"] == "agent_state_changed"
        assert payload["data"]["agentId"] == "agent:main"
        assert payload["data"]["status"] == "working"
        assert payload["data"]["currentTask"] == "reading file"
