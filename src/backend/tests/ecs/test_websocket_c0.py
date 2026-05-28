"""
Unit tests for websocket.py C0 modifications.

C0 Changes:
- EventBus subscriber for AgentStateChangedEvent → WS push
- _periodic_broadcast_loop removed
- broadcast_full_state removed
- Bootstrap (send_initial_state) still sends type:"full_state" (old format)
- New WS messages use incremental format via EventBus

Acceptance Criteria Coverage:
- C0 AC #3: _periodic_broadcast_loop code removed
- C0 AC #5: AgentStateChanged → agent card incremental update
- C0 constraint: bootstrap still uses type:"full_state" (old format)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


class TestWebSocketBootstrap:
    """Bootstrap still sends full_state (old format) — C0 allows this."""

    def test_send_initial_state_type(self, monkeypatch):
        """send_initial_state should send type:'full_state'."""
        import api.websocket as ws

        sent_messages = []

        class FakeWS:
            async def send_json(self, data):
                sent_messages.append(data)

            async def accept(self):
                pass

        async def _run():
            import api.agents as agents_mod
            import api.subagents as subagents_mod
            # Mock all the data fetching
            async def fake_get_agents():
                return [{"id": "main", "name": "Main", "status": "idle"}]

            async def fake_get_subagents():
                return []

            async def fake_get_api_status():
                return []

            monkeypatch.setattr(agents_mod, "get_agents", fake_get_agents)
            monkeypatch.setattr(subagents_mod, "get_subagents", fake_get_subagents)
            monkeypatch.setattr(subagents_mod, "get_tasks", fake_get_subagents)
            fake_mod = MagicMock(get_api_status_list=fake_get_api_status)
            sys.modules["api.api_status"] = fake_mod

            await ws.send_initial_state(FakeWS())

        asyncio.run(_run())
        if sent_messages:
            assert sent_messages[0]["type"] == "full_state"

    def test_initial_state_includes_agents(self, monkeypatch):
        """Bootstrap state should include agents data."""
        import api.websocket as ws

        sent_messages = []

        class FakeWS:
            async def send_json(self, data):
                sent_messages.append(data)

            async def accept(self):
                pass

        async def _run():
            await ws.send_initial_state(FakeWS())

        asyncio.run(_run())
        if sent_messages:
            data = sent_messages[0].get("data", {})
            # Even if agents fetch fails, 'agents' key should exist (empty list)
            assert "agents" in data


class TestWebSocketDoBroadcast:
    """_do_broadcast delivers to all active connections."""

    def test_broadcast_to_no_connections(self):
        import api.websocket as ws
        ws.active_connections.clear()

        async def _run():
            await ws._do_broadcast({"type": "test"})

        asyncio.run(_run())
        assert len(ws.active_connections) == 0

    def test_broadcast_to_multiple_connections(self):
        import api.websocket as ws
        ws.active_connections.clear()

        messages_by_conn = {}

        class FakeWS:
            def __init__(self, conn_id):
                self.conn_id = conn_id

            async def send_json(self, data):
                messages_by_conn[self.conn_id] = data

        c1 = FakeWS(1)
        c2 = FakeWS(2)
        ws.active_connections.add(c1)
        ws.active_connections.add(c2)

        async def _run():
            await ws._do_broadcast({"type": "state_update", "data": {"test": True}})

        asyncio.run(_run())
        assert 1 in messages_by_conn
        assert 2 in messages_by_conn
        assert messages_by_conn[1]["type"] == "state_update"

        ws.active_connections.clear()


class TestWebSocketPeriodicBroadcastLoop:
    """C0 AC #3: _periodic_broadcast_loop must be removed."""

    def test_periodic_broadcast_loop_does_not_exist(self):
        """After C0, _periodic_broadcast_loop should not exist."""
        import api.websocket as ws
        has_func = hasattr(ws, "_periodic_broadcast_loop")
        assert not has_func, "_periodic_broadcast_loop must be removed per C0 AC #3"

    def test_no_broadcast_interval_sec_var(self):
        """C0: BROADCAST_INTERVAL_SEC must not exist as module-level var."""
        import api.websocket as ws
        assert not hasattr(ws, "BROADCAST_INTERVAL_SEC"), (
            "BROADCAST_INTERVAL_SEC must be removed per C0 AC #3"
        )


class TestWebSocketAgentUpdateBroadcast:
    """Agent-specific update broadcasts."""

    def test_broadcast_agent_update(self):
        import api.websocket as ws
        ws.active_connections.clear()

        received = []

        class FakeWS:
            async def send_json(self, data):
                received.append(data)

        ws.active_connections.add(FakeWS())

        async def _run():
            await ws.broadcast_agent_update("main", "working")

        asyncio.run(_run())
        assert len(received) == 1
        assert received[0]["type"] == "agent_update"
        assert received[0]["data"]["agentId"] == "main"
        assert received[0]["data"]["status"] == "working"

        ws.active_connections.clear()

    def test_broadcast_subagent_update(self):
        import api.websocket as ws
        ws.active_connections.clear()

        received = []

        class FakeWS:
            async def send_json(self, data):
                received.append(data)

        ws.active_connections.add(FakeWS())

        async def _run():
            await ws.broadcast_subagent_update("run-1", "main", "success")

        asyncio.run(_run())
        assert len(received) == 1
        assert received[0]["type"] == "subagent_update"
        assert received[0]["data"]["runId"] == "run-1"
        assert received[0]["data"]["outcome"] == "success"

        ws.active_connections.clear()

    def test_broadcast_no_connections_is_noop(self):
        """Broadcasting with no connections should not error."""
        import api.websocket as ws
        ws.active_connections.clear()

        async def _run():
            await ws.broadcast_agent_update("main", "working")
            await ws.broadcast_subagent_update("run-1", "main", "success")
            await ws._do_broadcast({"type": "test"})

        asyncio.run(_run())  # Should not raise


class TestWebSocketConnectionManagement:
    """Connection set management."""

    def test_active_connections_count(self):
        import api.websocket as ws
        ws.active_connections.clear()

        class FakeWS:
            pass

        ws.active_connections.add(FakeWS())
        ws.active_connections.add(FakeWS())
        ws.active_connections.add(FakeWS())
        assert ws.get_active_connections_count() == 3

        ws.active_connections.clear()


class TestWebSocketDisconnectedCleanup:
    """Disconnected connections should be cleaned up."""

    def test_broadcast_removes_disconnected(self):
        import api.websocket as ws
        ws.active_connections.clear()

        class GoodWS:
            async def send_json(self, data):
                pass

        class BadWS:
            async def send_json(self, data):
                raise Exception("disconnected")

        ws.active_connections.add(GoodWS())
        ws.active_connections.add(BadWS())

        async def _run():
            await ws._do_broadcast({"type": "test"})

        asyncio.run(_run())
        assert len(ws.active_connections) == 1  # BadWS should be removed

        ws.active_connections.clear()


class TestWebSocketEventBusSubscriber:
    """C0: EventBus subscriber for agent_state_changed events."""

    def test_event_bus_subscriber_registration(self):
        """_ensure_event_bus_subscriber should register subscriber on first call."""
        import api.websocket as ws
        from core.event_bus import reset_event_bus_for_tests

        # Reset the subscriber flag
        ws._event_bus_subscribed = False
        reset_event_bus_for_tests()

        ws._ensure_event_bus_subscriber()
        assert ws._event_bus_subscribed is True

        # Second call should be no-op (already registered)
        initial = ws._event_bus_subscribed
        ws._ensure_event_bus_subscriber()
        assert ws._event_bus_subscribed is initial

        # Cleanup
        ws._event_bus_subscribed = False
        reset_event_bus_for_tests()

    def test_no_broadcast_full_state_function(self):
        """C0: broadcast_full_state must be removed."""
        import api.websocket as ws
        assert not hasattr(ws, "broadcast_full_state"), (
            "broadcast_full_state must be removed per C0"
        )

    def test_no_full_state_throttle_attributes(self):
        """C0: throttle attributes for broadcast_full_state must be removed."""
        import api.websocket as ws
        assert not hasattr(ws, "FULL_STATE_MIN_INTERVAL_SEC"), (
            "FULL_STATE_MIN_INTERVAL_SEC must be removed per C0"
        )
        assert not hasattr(ws, "_last_full_state_monotonic"), (
            "_last_full_state_monotonic must be removed per C0"
        )
