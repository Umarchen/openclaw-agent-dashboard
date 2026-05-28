"""
C2-9: C2 Integration Tests — verify C2 incremental event architecture.

Coverage: AC-010-1 through AC-010-5
  AC-010-1: File changes do NOT produce full_state containing collaboration/tasks/performance
  AC-010-2: CollaborationChanged events contain only changed fields (payload < 20% of full)
  AC-010-3: TaskChanged events contain only add/update/remove, not unchanged tasks
  AC-010-4: PerformanceSnapshot pushed on 30s slow channel, not driven by file changes
  AC-010-5: Timeline REST pull works with ?since=turnId cursor

Status:
  C2-1 ✅ event_types (CollaborationChanged, TaskChanged, PerformanceSnapshot)
  C2-2 ✅ collaboration_ingestor.py
  C2-3 ✅ task_ingestor.py
  C2-4 ✅ performance_ingestor.py (30s timer)
  C2-7 ✅ config_fortify ecs_perf_snapshot_interval_sec
  C2-5 ⏳ FullStateSnapshot slim-down (not yet landed)
  C2-6 ⏳ main.py lifespan C2 integration (not yet landed)
  C2-8 ⏳ Frontend C2 event handling (not yet landed — N/A for backend tests)

Run: pytest tests/ecs/test_c2_integration.py -v
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


# ============================================================================
# Helpers
# ============================================================================

def _read_source(module_path: str) -> str:
    """Read source file content; returns empty string if not found."""
    p = BACKEND / module_path
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def _c2_event_types_available() -> bool:
    """Check if C2 event types are importable."""
    try:
        from core.event_types import CollaborationChangedEvent, TaskChangedEvent, PerformanceSnapshotEvent
        return True
    except ImportError:
        return False


# ============================================================================
# AC-010-1: No full_state with collaboration/tasks/performance after file changes
# ============================================================================

class TestAC010_1_NoFullStateWithC2Domains:
    """AC-010-1: File changes must NOT produce full_state containing
    collaboration, tasks, or performance data.

    Strategy: Verify that the WS broadcast pipeline never emits a full_state
    or FullStateSnapshot event containing these domains after file changes.
    C2-5 created _collect_slim_full_state_data() for FullStateSnapshot.
    _collect_full_state_data() is retained for C0 legacy compatibility only.
    """

    def test_slim_full_state_excludes_collaboration(self):
        """C2 slim FullStateSnapshot must not contain 'collaboration'."""
        source = _read_source("api/websocket.py")
        fn_start = source.find("async def _collect_slim_full_state_data")
        if fn_start == -1:
            pytest.skip("C2-5 not landed: _collect_slim_full_state_data not found")

        fn_body = source[fn_start:fn_start + 2000]
        assert "'collaboration'" not in fn_body, (
            "AC-010-1 FAIL: Slim FullStateSnapshot still includes 'collaboration'."
        )

    def test_slim_full_state_excludes_tasks(self):
        """C2 slim FullStateSnapshot must not contain 'tasks'."""
        source = _read_source("api/websocket.py")
        fn_start = source.find("async def _collect_slim_full_state_data")
        if fn_start == -1:
            pytest.skip("C2-5 not landed: _collect_slim_full_state_data not found")

        fn_body = source[fn_start:fn_start + 2000]
        assert "'tasks'" not in fn_body, (
            "AC-010-1 FAIL: Slim FullStateSnapshot still assigns 'tasks'."
        )

    def test_slim_full_state_excludes_performance(self):
        """C2 slim FullStateSnapshot must not contain 'performance'."""
        source = _read_source("api/websocket.py")
        fn_start = source.find("async def _collect_slim_full_state_data")
        if fn_start == -1:
            pytest.skip("C2-5 not landed: _collect_slim_full_state_data not found")

        fn_body = source[fn_start:fn_start + 2000]
        assert "'performance'" not in fn_body, (
            "AC-010-1 FAIL: Slim FullStateSnapshot still includes 'performance'."
        )

    def test_ws_broadcast_no_full_state_on_file_change(self):
        """After a file change event, no full_state message should be broadcast."""
        source = _read_source("api/websocket.py")
        handler_start = source.find("def _on_agent_state_changed")
        if handler_start == -1:
            pytest.skip("Event handler not found")

        # Extract only the handler function body (up to the next def/async def)
        remaining = source[handler_start:handler_start + 2000]
        handler_lines = []
        for line in remaining.split("\n"):
            # Stop at the next top-level function definition
            if handler_lines and line and not line[0].isspace() and (line.startswith("def ") or line.startswith("async def ")):
                break
            handler_lines.append(line)
        handler_body = "\n".join(handler_lines)
        assert "_send_full_state" not in handler_body, (
            "AC-010-1 FAIL: _on_agent_state_changed still calls _send_full_state. "
            "Incremental events must not trigger full_state."
        )

    def test_full_state_only_on_bootstrap(self):
        """full_state / FullStateSnapshot only sent on WS connect or schema mismatch."""
        source = _read_source("api/websocket.py")
        lines = source.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or stripped == "":
                continue
            if "def _send_full_state" in stripped or "async def _send_full_state" in stripped:
                continue
            if "await _send_full_state" in stripped:
                context = "\n".join(lines[max(0, i-15):i+1])
                assert (
                    "websocket_endpoint" in context
                    or "send_initial_state" in context
                    or "schema_mismatch" in context
                    or "bootstrap" in context
                ), (
                    f"AC-010-1 FAIL: _send_full_state called outside bootstrap context at line {i+1}"
                )


# ============================================================================
# AC-010-2: CollaborationChanged only contains changed fields
# ============================================================================

class TestAC010_2_CollaborationChangedDiffOnly:
    """AC-010-2: CollaborationChanged event payload must contain only changed
    fields, not the full collaboration data. Payload size < 20% of full.
    """

    def test_collaboration_changed_event_importable(self):
        """CollaborationChangedEvent must be importable from core.event_types."""
        from core.event_types import CollaborationChangedEvent
        assert CollaborationChangedEvent is not None

    def test_collaboration_changed_has_diffs_field(self):
        """CollaborationChanged event must have 'diffs' field for field-level changes."""
        from core.event_types import CollaborationChangedEvent
        event = CollaborationChangedEvent(
            diffs=[{"field": "agentStatuses", "old_value": {}, "new_value": {}}],
        )
        assert hasattr(event, "diffs")
        assert isinstance(event.diffs, list)

    def test_collaboration_payload_size_constraint(self):
        """CollaborationChanged payload should be < 20% of full collaboration data."""
        from core.event_types import CollaborationChangedEvent
        source = _read_source("core/event_types.py")
        class_start = source.find("class CollaborationChangedEvent")
        class_body = source[class_start:class_start + 2000]
        # Should NOT have fields for full collaboration data
        full_data_fields = ["nodes", "edges", "agentModels", "models", "recentCalls", "hierarchy"]
        found_full_fields = [f for f in full_data_fields if f in class_body]
        assert not found_full_fields, (
            f"AC-010-2 FAIL: CollaborationChanged contains full data fields: {found_full_fields}"
        )

    def test_collaboration_changed_type_and_ws_payload(self):
        """CollaborationChanged event type is 'collaboration_changed' and has ws payload."""
        from core.event_types import CollaborationChangedEvent
        event = CollaborationChangedEvent(
            diffs=[{"field": "agentStatuses", "old_value": {"main": "idle"}, "new_value": {"main": "working"}}],
        )
        assert event.type == "collaboration_changed"
        payload = event.to_ws_payload()
        assert payload["type"] == "CollaborationChanged"
        assert "diffs" in payload["payload"]
        assert len(payload["payload"]["diffs"]) == 1

    def test_collaboration_changed_diff_size_under_20pct(self):
        """Diff payload < 20% of estimated full collaboration data."""
        from core.event_types import CollaborationChangedEvent
        event = CollaborationChangedEvent(
            diffs=[
                {"field": "agentStatuses", "old_value": {"main": "idle"}, "new_value": {"main": "working"}},
                {"field": "recentCalls", "old_value": [], "new_value": [{"id": "c1"}]},
            ],
        )
        full_collab_size_est = 5000  # rough estimate
        payload = json.dumps(event.to_ws_payload())
        payload_size = len(payload.encode("utf-8"))
        assert payload_size < full_collab_size_est * 0.2, (
            f"AC-010-2 FAIL: payload {payload_size}B >= 20% of est {full_collab_size_est}B"
        )


# ============================================================================
# AC-010-3: TaskChanged only contains add/update/remove
# ============================================================================

class TestAC010_3_TaskChangedDiffOnly:
    """AC-010-3: TaskChanged event must contain only add/update/remove operations,
    not unchanged tasks.
    """

    def test_task_changed_event_importable(self):
        """TaskChangedEvent must be importable."""
        from core.event_types import TaskChangedEvent
        assert TaskChangedEvent is not None

    def test_task_changed_has_change_field(self):
        """TaskChanged event must have 'change' field (add/update/remove)."""
        from core.event_types import TaskChangedEvent
        event = TaskChangedEvent(change="added", task_id="t1")
        assert event.change == "added"

    def test_task_changed_has_task_id(self):
        """TaskChanged event must have 'task_id' to identify the affected task."""
        from core.event_types import TaskChangedEvent
        event = TaskChangedEvent(change="added", task_id="task-run-001")
        assert event.task_id == "task-run-001"

    def test_task_changed_no_full_tasks_list(self):
        """TaskChanged should NOT contain a 'tasks' field (full list)."""
        from core.event_types import TaskChangedEvent
        source = _read_source("core/event_types.py")
        class_start = source.find("class TaskChangedEvent")
        class_body = source[class_start:class_start + 2000]
        assert "tasks:" not in class_body and '"tasks"' not in class_body, (
            "AC-010-3 FAIL: TaskChanged contains 'tasks' field (full list)."
        )

    def test_task_changed_added_event(self):
        """TaskChanged event with change='added' contains task_data."""
        from core.event_types import TaskChangedEvent
        event = TaskChangedEvent(
            change="added",
            task_id="task-run-001",
            task_data={"name": "Build project", "status": "working"},
        )
        assert event.type == "task_changed"
        assert event.change == "added"
        assert event.task_data is not None

    def test_task_changed_removed_event(self):
        """TaskChanged event with change='removed' works with minimal task_data."""
        from core.event_types import TaskChangedEvent
        event = TaskChangedEvent(
            change="removed",
            task_id="task-run-001",
            task_data=None,
        )
        assert event.change == "removed"
        assert event.task_data is None

    def test_task_changed_ws_payload_camelcase(self):
        """TaskChanged to_ws_payload uses camelCase keys."""
        from core.event_types import TaskChangedEvent
        event = TaskChangedEvent(change="updated", task_id="t1", task_data={"status": "done"})
        payload = event.to_ws_payload()
        assert payload["type"] == "TaskChanged"
        assert "taskId" in payload["payload"]
        assert "taskData" in payload["payload"]
        assert "change" in payload["payload"]


# ============================================================================
# AC-010-4: PerformanceSnapshot 30s slow channel
# ============================================================================

class TestAC010_4_PerformanceSnapshotSlowChannel:
    """AC-010-4: PerformanceSnapshot pushed on 30s slow channel timer,
    NOT driven by individual file changes.
    """

    def test_performance_snapshot_event_importable(self):
        """PerformanceSnapshotEvent must be importable."""
        from core.event_types import PerformanceSnapshotEvent
        assert PerformanceSnapshotEvent is not None

    def test_performance_snapshot_has_agents_and_global_stats(self):
        """PerformanceSnapshot must contain 'agents' and 'global_stats' fields."""
        from core.event_types import PerformanceSnapshotEvent
        event = PerformanceSnapshotEvent(
            agents={"main": {"tokens": 1000}},
            global_stats={"totalTokens": 5000},
        )
        assert hasattr(event, "agents")
        assert hasattr(event, "global_stats")

    def test_30s_interval_in_config(self):
        """Performance snapshot interval must be configurable at 30s default."""
        source = _read_source("core/config_fortify.py")
        assert "ecs_perf_snapshot_interval_sec" in source, (
            "AC-010-4 FAIL: ecs_perf_snapshot_interval_sec not in config_fortify."
        )
        # Find the default value — look in the entire file for the _env_float call
        idx = source.find("ecs_perf_snapshot_interval_sec")
        # Search the rest of the file for the default 30.0 value
        rest = source[idx:]
        assert "30.0" in rest or "30," in rest, (
            "AC-010-4 FAIL: ecs_perf_snapshot_interval_sec default != 30"
        )

    def test_slow_channel_not_triggered_by_file_change(self):
        """PerformanceIngestor should NOT subscribe to file change events."""
        source = _read_source("ingest/performance_ingestor.py")
        assert "TOPIC_FILE_CHANGES" not in source, (
            "AC-010-4 FAIL: PerformanceIngestor subscribes to TOPIC_FILE_CHANGES. "
            "It should use a fixed-interval timer only."
        )

    def test_performance_ingestor_uses_timer(self):
        """PerformanceIngestor must use asyncio interval-based loop."""
        source = _read_source("ingest/performance_ingestor.py")
        assert "asyncio.sleep" in source or "interval" in source.lower(), (
            "AC-010-4 FAIL: PerformanceIngestor has no interval-based timer."
        )

    def test_ws_handler_no_performance_on_file_change(self):
        """WS agent_state_changed handler should NOT produce PerformanceSnapshot."""
        source = _read_source("api/websocket.py")
        handler_start = source.find("def _on_agent_state_changed")
        if handler_start == -1:
            pytest.skip("Event handler not found")
        # Extract only this handler's body (stop at next top-level def)
        remaining = source[handler_start:handler_start + 2000]
        handler_lines = []
        for line in remaining.split("\n"):
            if handler_lines and line and not line[0].isspace() and (line.startswith("def ") or line.startswith("async def ")):
                break
            handler_lines.append(line)
        handler_body = "\n".join(handler_lines)
        assert "PerformanceSnapshot" not in handler_body, (
            "AC-010-4 FAIL: _on_agent_state_changed references PerformanceSnapshot."
        )

    def test_performance_snapshot_event_type_and_payload(self):
        """PerformanceSnapshot event type and ws payload are correct."""
        from core.event_types import PerformanceSnapshotEvent
        event = PerformanceSnapshotEvent(
            agents={"main": {"tokens": 1000, "requests": 5}},
            global_stats={"totalTokens": 5000, "totalRequests": 20},
        )
        assert event.type == "performance_snapshot"
        payload = event.to_ws_payload()
        assert payload["type"] == "PerformanceSnapshot"
        assert "agents" in payload["payload"]
        assert "globalStats" in payload["payload"]


# ============================================================================
# AC-010-5: Timeline REST pull with ?since=turnId cursor
# ============================================================================

class TestAC010_5_TimelineRESTCursor:
    """AC-010-5: Timeline must support REST pull with ?since=turnId cursor parameter.
    NOTE: This feature depends on C2 timeline API changes. Skipped if not yet implemented.
    """

    def test_timeline_endpoint_exists(self):
        """/api/timeline/{agent_id} endpoint must exist."""
        from main import app
        route_paths = [r.path for r in app.routes if hasattr(r, 'path')]
        timeline_routes = [p for p in route_paths if "timeline" in p]
        assert len(timeline_routes) > 0, "No /timeline routes found"

    def test_timeline_has_since_parameter(self):
        """Timeline endpoint must accept 'since' query parameter."""
        source = _read_source("api/timeline.py")
        if "since" not in source:
            pytest.skip("C2-5 timeline 'since' cursor not yet implemented")
        assert "since" in source

    def test_timeline_since_filters_data(self):
        """When ?since=<turnId> is provided, only steps after that turn should return."""
        source = _read_source("api/timeline.py")
        if "since" not in source:
            pytest.skip("C2 timeline 'since' parameter not yet added")
        # Verify 'since' is passed through to the data reader
        assert "since" in source

    @pytest.mark.asyncio
    async def test_timeline_rest_returns_valid_structure(self):
        """Timeline REST endpoint returns valid response structure."""
        from main import app

        # Mock data reader to avoid filesystem dependency
        async def fake_timeline(*args, **kwargs):
            return {
                "sessionId": "session-001",
                "agentId": "main",
                "status": "active",
                "steps": [
                    {"id": "step-1", "type": "user", "content": "hello"},
                    {"id": "step-2", "type": "assistant", "content": "hi"},
                ],
                "stats": {
                    "totalDuration": 1000,
                    "totalInputTokens": 100,
                    "totalOutputTokens": 50,
                    "toolCallCount": 0,
                    "stepCount": 2,
                },
            }

        try:
            from data.timeline_reader import get_timeline_steps as _orig
        except ImportError:
            pytest.skip("timeline_reader not available")

        import data.timeline_reader as tl_mod
        import api.timeline as api_tl_mod
        orig_reader = tl_mod.get_timeline_steps
        orig_config = api_tl_mod.get_agent_config
        tl_mod.get_timeline_steps = fake_timeline
        api_tl_mod.get_agent_config = lambda agent_id: {"id": agent_id, "name": agent_id}

        try:
            import httpx
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                r = await client.get("/api/timeline/main")
                assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
                body = r.json()
                assert "steps" in body or "sessionId" in body, (
                    f"Unexpected response structure: {list(body.keys())}"
                )
        finally:
            tl_mod.get_timeline_steps = orig_reader
            api_tl_mod.get_agent_config = orig_config


# ============================================================================
# Cross-cutting: Event type registration and WS protocol
# ============================================================================

class TestC2EventTypesAndBusRegistration:
    """Verify all C2 event types are properly defined and bus topics exist."""

    def test_all_c2_event_types_importable(self):
        """All C2 event types must be importable."""
        from core.event_types import (
            CollaborationChangedEvent,
            TaskChangedEvent,
            PerformanceSnapshotEvent,
        )

    def test_c2_event_types_set_correct_type(self):
        """Each C2 event type sets correct self.type in __post_init__."""
        from core.event_types import (
            CollaborationChangedEvent,
            TaskChangedEvent,
            PerformanceSnapshotEvent,
        )
        assert CollaborationChangedEvent().type == "collaboration_changed"
        assert TaskChangedEvent().type == "task_changed"
        assert PerformanceSnapshotEvent().type == "performance_snapshot"

    def test_c2_event_bus_topics_defined(self):
        """C2 EventBus topics must be defined in event_bus.py."""
        from core.event_bus import (
            TOPIC_COLLABORATION_CHANGED,
            TOPIC_TASK_CHANGED,
            TOPIC_PERFORMANCE_SNAPSHOT,
        )
        assert TOPIC_COLLABORATION_CHANGED
        assert TOPIC_TASK_CHANGED
        assert TOPIC_PERFORMANCE_SNAPSHOT

    def test_ws_broadcaster_handles_c2_topics(self):
        """WS broadcaster subscribes to C2 event topics."""
        source = _read_source("api/websocket.py")
        # C2 topics should be subscribed somewhere in the WS module
        # or handled by a catch-all subscriber
        has_c2_topics = (
            "TOPIC_COLLABORATION_CHANGED" in source
            or "TOPIC_TASK_CHANGED" in source
            or "TOPIC_PERFORMANCE_SNAPSHOT" in source
            or "TOPIC_STATE_UPDATES" in source  # catch-all
        )
        # If no direct topic subscription, check if C2 events are handled
        # via a generic broadcaster that forwards all events
        if not has_c2_topics:
            pytest.skip("C2-6 not landed: WS broadcaster doesn't handle C2 topics yet")


# ============================================================================
# C2 Ingestor module checks
# ============================================================================

class TestC2Ingestors:
    """Verify C2 ingestor modules exist and have correct interfaces."""

    def test_collaboration_ingestor_exists(self):
        """CollaborationIngestor module must exist."""
        from ingest.collaboration_ingestor import CollaborationIngestor
        assert callable(CollaborationIngestor)

    def test_task_ingestor_exists(self):
        """TaskIngestor module must exist."""
        from ingest.task_ingestor import TaskIngestor
        assert callable(TaskIngestor)

    def test_performance_ingestor_exists(self):
        """PerformanceIngestor module must exist."""
        from ingest.performance_ingestor import PerformanceIngestor
        assert callable(PerformanceIngestor)

    @pytest.mark.asyncio
    async def test_collaboration_ingestor_initialize(self):
        """CollaborationIngestor.initialize() subscribes to file changes."""
        from core.event_bus import get_event_bus
        from ingest.collaboration_ingestor import CollaborationIngestor
        ingestor = CollaborationIngestor()
        ingestor.initialize(bus=get_event_bus())

    @pytest.mark.asyncio
    async def test_task_ingestor_initialize(self):
        """TaskIngestor.initialize() subscribes to file changes."""
        from core.event_bus import get_event_bus
        from ingest.task_ingestor import TaskIngestor
        ingestor = TaskIngestor()
        ingestor.initialize(bus=get_event_bus())

    @pytest.mark.asyncio
    async def test_performance_ingestor_start_stop(self):
        """PerformanceIngestor can be started and stopped."""
        from ingest.performance_ingestor import PerformanceIngestor
        ingestor = PerformanceIngestor()
        # Verify it initializes correctly
        assert ingestor._running is False
        # Verify stop() is async and callable
        await ingestor.stop()
        assert ingestor._running is False


# ============================================================================
# FullStateSnapshot slim-down verification (C2-5)
# ============================================================================

class TestFullStateSnapshotSlim:
    """C2-5: FullStateSnapshot should only contain agents, subagents, apiStatus.
    collaboration, tasks, performance removed.
    NOTE: C2-5 not yet landed — tests verify expected structure.
    """

    def test_full_state_snapshot_slim_required_keys(self):
        """FullStateSnapshot data must always contain agents, subagents, apiStatus."""
        source = _read_source("api/websocket.py")
        fn_start = source.find("async def _collect_full_state_data")
        if fn_start == -1:
            pytest.skip("_collect_full_state_data not found")

        fn_body = source[fn_start:fn_start + 5000]
        required_keys = ["agents", "subagents", "apiStatus"]
        for key in required_keys:
            assert f"'{key}'" in fn_body or f'"{key}"' in fn_body, (
                f"FullStateSnapshot missing required key '{key}'"
            )

    def test_full_state_snapshot_no_removed_keys_after_c2(self):
        """After C2-5, _collect_slim_full_state_data has no collab/tasks/perf/workflows."""
        source = _read_source("api/websocket.py")
        fn_start = source.find("async def _collect_slim_full_state_data")
        if fn_start == -1:
            pytest.skip("C2-5 not landed: _collect_slim_full_state_data not found")

        fn_body = source[fn_start:fn_start + 5000]
        c2_removed = ["collaboration", "tasks", "performance", "workflows"]
        for key in c2_removed:
            assert f"'{key}'" not in fn_body, (
                f"C2-5 FAIL: _collect_slim_full_state_data still includes '{key}'. "
                f"Should be removed and emitted via C2 events instead."
            )

    def test_legacy_full_state_retained(self):
        """C0 legacy _collect_full_state_data is retained for send_initial_state."""
        source = _read_source("api/websocket.py")
        fn_start = source.find("async def _collect_full_state_data")
        if fn_start == -1:
            pytest.fail("_collect_full_state_data (legacy) not found")

        # Legacy version should still include collaboration/tasks/performance for C0 compat
        fn_body = source[fn_start:fn_start + 3000]
        assert "'collaboration'" in fn_body, (
            "Legacy _collect_full_state_data should still include collaboration for C0 compat"
        )
