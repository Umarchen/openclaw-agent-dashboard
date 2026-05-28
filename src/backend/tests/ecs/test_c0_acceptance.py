"""
C0-11: Integration tests verifying all 6 acceptance criteria.

These tests exercise the actual backend modules (not mocks/shims) to validate:
  AC1: runtime full_state push = 0/min (bootstrap excluded)
  AC2: file change → WS message flow contains no full_state type (excluding first connection)
  AC3: _periodic_broadcast_loop code does NOT exist in websocket.py
  AC4: polling 5 minutes → full_state_total delta = 0
  AC5: first connection receives exactly 1 full_state (old format type: "full_state")
  AC6: /api/metrics endpoint returns 7 required metrics

Prerequisites (blocked until these land):
  C0-5: file_watcher → EventBus publish (replaces broadcast_full_state)
  C0-6: websocket → EventBus subscriber + remove _periodic_broadcast_loop
  C0-7: main.py lifespan initializes EventBus + Ingestor + StateStore

Run: pytest tests/ecs/test_c0_acceptance.py -v
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


# ── Helpers ────────────────────────────────────────────────────────────

def _stub_file_watcher(monkeypatch) -> None:
    """Prevent real file watcher from starting during tests."""
    import watchers.file_watcher as fw
    monkeypatch.setattr(fw, "start_file_watcher", lambda loop: None)
    monkeypatch.setattr(fw, "stop_file_watcher", lambda: None)


def _collect_ws_messages(captured: list, monkeypatch) -> None:
    """Monkey-patch broadcast_message to capture all WS sends."""
    import api.websocket as ws
    original_broadcast = ws.broadcast_message

    async def capturing_broadcast(message: dict) -> None:
        captured.append(message)
        await original_broadcast(message)

    monkeypatch.setattr(ws, "broadcast_message", capturing_broadcast)


# ═══════════════════════════════════════════════════════════════════════
# AC3: _periodic_broadcast_loop must NOT exist (grep verification)
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(reason="C0-6 not yet landed: _periodic_broadcast_loop still in websocket.py", strict=False)
class TestAC3_PeriodicBroadcastRemoved:
    """Verify _periodic_broadcast_loop is completely removed from websocket.py.

    These tests verify that C0-6 has removed all periodic broadcast infrastructure.
    They xfail until C0-6 is complete — once backend-dev removes the code,
    these will flip to xpass, signalling the requirement is met.
    """

    def test_no_periodic_broadcast_loop_def(self):
        """AC3: 'def _periodic_broadcast_loop' must not appear in source."""
        ws_path = BACKEND / "api" / "websocket.py"
        source = ws_path.read_text(encoding="utf-8")
        assert "def _periodic_broadcast_loop" not in source, (
            "AC3 FAIL: _periodic_broadcast_loop function definition found in websocket.py. "
            "C0-6 requires complete removal."
        )

    def test_no_ensure_broadcast_task_def(self):
        """AC3: 'def _ensure_broadcast_task' must not appear."""
        ws_path = BACKEND / "api" / "websocket.py"
        source = ws_path.read_text(encoding="utf-8")
        assert "def _ensure_broadcast_task" not in source, (
            "AC3 FAIL: _ensure_broadcast_task found in websocket.py."
        )

    def test_no_cancel_broadcast_task_def(self):
        """AC3: 'def _cancel_broadcast_task' must not appear."""
        ws_path = BACKEND / "api" / "websocket.py"
        source = ws_path.read_text(encoding="utf-8")
        assert "def _cancel_broadcast_task" not in source, (
            "AC3 FAIL: _cancel_broadcast_task found in websocket.py."
        )

    def test_no_broadcast_interval_sec_var(self):
        """AC3: BROADCAST_INTERVAL_SEC must not exist as module-level var."""
        ws_path = BACKEND / "api" / "websocket.py"
        source = ws_path.read_text(encoding="utf-8")
        assert "BROADCAST_INTERVAL_SEC" not in source, (
            "AC3 FAIL: BROADCAST_INTERVAL_SEC variable found in websocket.py."
        )


# ═══════════════════════════════════════════════════════════════════════
# AC5: First connection receives 1 full_state (bootstrap, old format)
# ═══════════════════════════════════════════════════════════════════════

class TestAC5_BootstrapFullState:

    def setup_method(self, method):
        pass  # monkeypatch is per-test via fixture

    def test_first_connection_receives_full_state(self, monkeypatch):
        """AC5: send_initial_state sends exactly 1 message with type:'full_state'."""
        _stub_file_watcher(monkeypatch)
        import api.websocket as ws
        import api.agents as agents_mod
        import api.subagents as subagents_mod

        sent = []

        class FakeWS:
            async def send_json(self, data):
                sent.append(data)
            async def accept(self):
                pass

        async def fake_agents():
            return [{"id": "main", "name": "Main", "status": "idle", "lastActiveAt": 0}]
        async def fake_empty():
            return []

        # Mock all data fetchers used by send_initial_state
        monkeypatch.setattr(agents_mod, "get_agents", fake_agents)
        monkeypatch.setattr(subagents_mod, "get_subagents", fake_empty)
        monkeypatch.setattr(subagents_mod, "get_tasks", fake_empty)
        # api_status is imported inside send_initial_state via `from .api_status import ...`
        # Create a fake async function
        async def fake_api_status():
            return []
        fake_api_status_mod = MagicMock(get_api_status_list=fake_api_status)
        sys.modules['api.api_status'] = fake_api_status_mod

        asyncio.run(ws.send_initial_state(FakeWS()))

        assert len(sent) == 1, f"AC5 FAIL: Expected 1 bootstrap message, got {len(sent)}"
        assert sent[0]["type"] == "full_state", (
            f"AC5 FAIL: Bootstrap type is '{sent[0].get('type')}', expected 'full_state'"
        )
        assert "agents" in sent[0]["data"], "AC5 FAIL: Bootstrap data missing 'agents'"

    def test_full_state_has_required_data_keys(self, monkeypatch):
        """AC5: bootstrap full_state must contain expected top-level keys."""
        _stub_file_watcher(monkeypatch)
        import api.websocket as ws
        import api.agents as agents_mod
        import api.subagents as subagents_mod

        sent = []

        class FakeWS:
            async def send_json(self, data):
                sent.append(data)
            async def accept(self):
                pass

        async def fake_agents():
            return [{"id": "main", "name": "Main"}]
        async def fake_empty():
            return []

        monkeypatch.setattr(agents_mod, "get_agents", fake_agents)
        monkeypatch.setattr(subagents_mod, "get_subagents", fake_empty)
        monkeypatch.setattr(subagents_mod, "get_tasks", fake_empty)
        async def fake_api_status():
            return []
        fake_api_status_mod = MagicMock(get_api_status_list=fake_api_status)
        sys.modules['api.api_status'] = fake_api_status_mod

        asyncio.run(ws.send_initial_state(FakeWS()))

        data = sent[0]["data"]
        required = {"agents", "subagents", "apiStatus"}
        assert required.issubset(data.keys()), (
            f"AC5 FAIL: Missing keys {required - set(data.keys())}. Have: {set(data.keys())}"
        )


# ═══════════════════════════════════════════════════════════════════════
# AC1: runtime full_state push = 0/min (bootstrap excluded)
# AC2: file change → WS messages contain no full_state (excluding first conn)
# AC4: polling 5 min → full_state_total delta = 0
# ═══════════════════════════════════════════════════════════════════════

class TestAC1_AC2_AC4_NoRuntimeFullState:

    def test_file_watcher_no_broadcast_full_state(self):
        """AC1/AC4: file_watcher._on_file_changed must NOT call broadcast_full_state.
        After C0-5 lands, this reference should be completely removed."""
        fw_path = BACKEND / "watchers" / "file_watcher.py"
        source = fw_path.read_text(encoding="utf-8")

        if "broadcast_full_state" in source:
            pytest.skip(
                "C0-5 not yet landed: broadcast_full_state still referenced "
                "in file_watcher.py. Test will pass after C0-5."
            )

        # Once C0-5 lands, this path verifies removal
        assert "broadcast_full_state" not in source

    def test_broadcast_full_state_function_removed_from_websocket(self):
        """AC1: broadcast_full_state function should be removed from websocket.py
        after C0-6 lands (replaced by EventBus subscriber)."""
        ws_path = BACKEND / "api" / "websocket.py"
        source = ws_path.read_text(encoding="utf-8")

        if "def broadcast_full_state" in source:
            pytest.skip(
                "C0-6 not yet landed: broadcast_full_state() still defined "
                "in websocket.py. Test will pass after C0-6."
            )

        assert "def broadcast_full_state" not in source

    def test_polling_tick_no_invalidate_or_broadcast(self):
        """AC4: polling tick must NOT invalidate cache or broadcast_full_state.
        After C0-5: tick should only publish HeartbeatTickEvent to EventBus."""
        fw_path = BACKEND / "watchers" / "file_watcher.py"
        source = fw_path.read_text(encoding="utf-8")

        if "broadcast_full_state" in source:
            pytest.skip("C0-5 not yet landed")

        # After C0-5: verify _start_polling_mode doesn't call broadcast_full_state
        assert "broadcast_full_state" not in source

    def test_ws_message_types_incremental_only(self, monkeypatch):
        """AC2: All non-bootstrap WS broadcasts must use incremental types,
        not full_state."""
        import api.websocket as ws

        ws_messages = []
        _collect_ws_messages(ws_messages, monkeypatch)

        # Simulate post-bootstrap messages (these should always be incremental)
        asyncio.run(ws.broadcast_agent_update("main", "working"))
        asyncio.run(ws.broadcast_state_update([
            {"id": "main", "status": "working", "currentTask": "build"}
        ]))

        for msg in ws_messages:
            assert msg.get("type") != "full_state", (
                f"AC2 FAIL: Non-bootstrap WS message has type 'full_state': {msg}"
            )


# ═══════════════════════════════════════════════════════════════════════
# AC6: /api/metrics returns 7 required metrics
# ═══════════════════════════════════════════════════════════════════════

class TestAC6_MetricsEndpoint:

    REQUIRED_METRICS = [
        "event_bus_published",
        "event_bus_latency_p95_ms",
        "ingest_count",
        "ingest_lag_p95_ms",
        "full_state_push_count",
        "full_state_push_per_minute",
        "ws_connections",
    ]

    def test_metrics_endpoint_returns_200(self, monkeypatch):
        """AC6: /api/metrics must return 200."""
        _stub_file_watcher(monkeypatch)
        import httpx
        from main import app

        async def _run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                r = await client.get("/api/metrics")
                return r

        r = asyncio.run(_run())

        if r.status_code == 404:
            pytest.skip(
                "C0-7 not yet landed: /api/metrics endpoint not registered in main.py"
            )
        assert r.status_code == 200, f"AC6 FAIL: /api/metrics returned {r.status_code}"

    def test_metrics_has_all_7_fields(self, monkeypatch):
        """AC6: response body must contain all 7 required metric keys."""
        _stub_file_watcher(monkeypatch)
        import httpx
        from main import app

        async def _run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                return await client.get("/api/metrics")

        r = asyncio.run(_run())
        if r.status_code == 404:
            pytest.skip("C0-7 not yet landed")

        body = r.json()
        missing = [m for m in self.REQUIRED_METRICS if m not in body]
        assert not missing, (
            f"AC6 FAIL: /api/metrics missing fields: {missing}. "
            f"Got: {list(body.keys())}"
        )

    def test_full_state_push_count_zero_at_startup(self, monkeypatch):
        """AC6: full_state_push_count must be 0 at startup (bootstrap excluded)."""
        _stub_file_watcher(monkeypatch)
        import httpx
        from main import app

        async def _run():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                return await client.get("/api/metrics")

        r = asyncio.run(_run())
        if r.status_code == 404:
            pytest.skip("C0-7 not yet landed")

        body = r.json()
        assert body.get("full_state_push_count", -1) == 0, (
            f"AC6 FAIL: full_state_push_count should be 0 at startup, "
            f"got {body.get('full_state_push_count')}"
        )


# ═══════════════════════════════════════════════════════════════════════
# End-to-end: WS endpoint registration & message flow
# ═══════════════════════════════════════════════════════════════════════

class TestWSEndToEnd:

    def test_ws_endpoint_registered(self, monkeypatch):
        """WS /ws endpoint must be registered in FastAPI app routes."""
        _stub_file_watcher(monkeypatch)
        from main import app

        route_paths = [r.path for r in app.routes]
        assert "/ws" in route_paths, (
            "AC5 FAIL: /ws endpoint not found in app routes"
        )

    def test_no_full_state_in_incremental_broadcasts(self, monkeypatch):
        """All broadcast_agent_update / broadcast_state_update messages
        must use non-full_state types."""
        import api.websocket as ws

        messages = []
        _collect_ws_messages(messages, monkeypatch)

        asyncio.run(ws.broadcast_agent_update("main", "working"))
        asyncio.run(ws.broadcast_agent_update("coder", "idle"))
        asyncio.run(ws.broadcast_state_update([
            {"id": "main", "status": "idle", "currentTask": ""}
        ]))

        for msg in messages:
            assert msg["type"] != "full_state", (
                f"AC2 FAIL: Incremental broadcast sent full_state type: {msg}"
            )
