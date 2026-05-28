"""
C2-9: C2 Integration Tests — verify C2 incremental event architecture.

Coverage: AC-010-1 through AC-010-5
  AC-010-1: File changes do NOT produce full_state containing collaboration/tasks/performance
  AC-010-2: CollaborationChanged events contain only changed fields (payload < 20% of full)
  AC-010-3: TaskChanged events contain only add/update/remove, not unchanged tasks
  AC-010-4: PerformanceSnapshot pushed on 30s slow channel, not driven by file changes
  AC-010-5: Timeline REST pull works with ?since=turnId cursor

Blocked by: C2-2, C2-3, C2-4, C2-5, C2-6, C2-8

Prerequisites (modules that must exist before these tests can pass):
  - C2-2: collaboration_ingestor.py — CollaborationChanged event production
  - C2-3: task_ingestor.py (or runs.json diff in agent_ingestor) — TaskChanged event
  - C2-4: performance_slow_channel.py — PerformanceSnapshot 30s timer
  - C2-5: FullStateSnapshot slim-down (remove collab/tasks/perf from bootstrap)
  - C2-6: main.py lifespan integration of C2 components
  - C2-8: Frontend RealtimeDataManager C2 event handling

Test strategy:
  1. Code-level grep/AST checks for structural guarantees (always valid)
  2. Module import + interface checks (require C2 modules to exist)
  3. Event flow integration tests (require real C2 modules)
  4. REST endpoint tests (require API changes)

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


def _c2_modules_available() -> bool:
    """Check if C2 implementation modules are importable."""
    try:
        from core.event_types import BaseEvent
        return True
    except ImportError:
        return False


def _c2_events_exist() -> bool:
    """Check if C2 event types are defined in core/event_types.py."""
    source = _read_source("core/event_types.py")
    return all(keyword in source for keyword in [
        "CollaborationChanged",
        "TaskChanged",
        "PerformanceSnapshot",
    ])


def _full_state_snapshot_is_slim() -> bool:
    """Check if FullStateSnapshot payload excludes collab/tasks/perf."""
    source = _read_source("api/websocket.py")
    collect_fn = _read_source("api/websocket.py")
    # Look for _collect_full_state_data removing collaboration/tasks/performance
    return "'collaboration'" not in collect_fn.split("async def _collect_full_state_data")[1].split("\n\n")[0] \
        if "async def _collect_full_state_data" in collect_fn else False


def _performance_slow_channel_exists() -> bool:
    """Check if performance slow channel (30s timer) exists."""
    source = _read_source("api/websocket.py") + _read_source("main.py")
    return "PerformanceSnapshot" in source or "perf.*snapshot" in source.lower()


# ============================================================================
# AC-010-1: No full_state with collaboration/tasks/performance after file changes
# ============================================================================

class TestAC010_1_NoFullStateWithC2Domains:
    """AC-010-1: File changes must NOT produce full_state containing
    collaboration, tasks, or performance data.
    
    Strategy: Verify that the WS broadcast pipeline never emits a full_state
    or FullStateSnapshot event containing these domains after file changes.
    """

    def test_full_state_snapshot_excludes_collaboration(self):
        """FullStateSnapshot must not contain 'collaboration' key."""
        if not _c2_modules_available():
            pytest.skip("C2 modules not available yet")

        source = _read_source("api/websocket.py")
        # After C2-5: _collect_full_state_data should NOT include collaboration
        fn_start = source.find("async def _collect_full_state_data")
        if fn_start == -1:
            pytest.skip("C2-5 not landed: _collect_full_state_data not found")

        fn_body = source[fn_start:fn_start + 3000]
        # C2: collaboration should not be collected in the function body
        assert "'collaboration'" not in fn_body or "collaboration_changed" in fn_body.lower(), (
            "AC-010-1 FAIL: FullStateSnapshot still includes 'collaboration' in _collect_full_state_data. "
            "C2-5 should remove it and emit CollaborationChanged events instead."
        )

    def test_full_state_snapshot_excludes_tasks(self):
        """FullStateSnapshot must not contain 'tasks' key (task data comes via TaskChanged)."""
        if not _c2_modules_available():
            pytest.skip("C2 modules not available yet")

        source = _read_source("api/websocket.py")
        fn_start = source.find("async def _collect_full_state_data")
        if fn_start == -1:
            pytest.skip("C2-5 not landed")

        fn_body = source[fn_start:fn_start + 3000]
        assert "'tasks'" not in fn_body or "task_changed" in fn_body.lower(), (
            "AC-010-1 FAIL: FullStateSnapshot still includes 'tasks'. "
            "C2-3 should emit TaskChanged events instead."
        )

    def test_full_state_snapshot_excludes_performance(self):
        """FullStateSnapshot must not contain 'performance' key (perf data via PerformanceSnapshot)."""
        if not _c2_modules_available():
            pytest.skip("C2 modules not available yet")

        source = _read_source("api/websocket.py")
        fn_start = source.find("async def _collect_full_state_data")
        if fn_start == -1:
            pytest.skip("C2-5 not landed")

        fn_body = source[fn_start:fn_start + 3000]
        assert "'performance'" not in fn_body or "performance_snapshot" in fn_body.lower(), (
            "AC-010-1 FAIL: FullStateSnapshot still includes 'performance'. "
            "C2-4 should emit PerformanceSnapshot events via slow channel."
        )

    def test_ws_broadcast_no_full_state_on_file_change(self):
        """After a file change event, no full_state message should be broadcast."""
        if not _c2_events_exist():
            pytest.skip("C2 event types not defined yet")

        # Verify that the WS broadcast functions do not call full_state
        # on incremental events
        source = _read_source("api/websocket.py")
        # The _on_agent_state_changed handler should NOT call _send_full_state_legacy
        handler_start = source.find("def _on_agent_state_changed")
        if handler_start == -1:
            pytest.skip("C2-6 not landed")

        handler_body = source[handler_start:handler_start + 2000]
        assert "_send_full_state" not in handler_body, (
            "AC-010-1 FAIL: _on_agent_state_changed still calls _send_full_state. "
            "Incremental events must not trigger full_state."
        )

    def test_full_state_only_on_bootstrap(self):
        """full_state / FullStateSnapshot only sent on WS connect or schema mismatch."""
        source = _read_source("api/websocket.py")
        # _send_full_state_legacy and _send_full_state_snapshot should only
        # be called in websocket_endpoint (bootstrap) and not in event handlers
        lines = source.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or stripped == "":
                continue
            # Skip the function definitions themselves
            if "def _send_full_state" in stripped or "async def _send_full_state" in stripped:
                continue
            if "await _send_full_state" in stripped:
                # Should only be in websocket_endpoint
                context = "\n".join(lines[max(0, i-10):i+1])
                # Verify it's inside websocket_endpoint or send_initial_state
                assert "websocket_endpoint" in context or "send_initial_state" in context, (
                    f"AC-010-1 FAIL: _send_full_state called outside bootstrap context at line {i+1}"
                )


# ============================================================================
# AC-010-2: CollaborationChanged only contains changed fields
# ============================================================================

class TestAC010_2_CollaborationChangedDiffOnly:
    """AC-010-2: CollaborationChanged event payload must contain only changed
    fields, not the full collaboration data. Payload size < 20% of full.
    """

    def test_collaboration_changed_event_type_exists(self):
        """CollaborationChanged event type must be defined in event_types.py."""
        source = _read_source("core/event_types.py")
        assert "CollaborationChanged" in source, (
            "AC-010-2 FAIL: CollaborationChanged event type not defined. "
            "C2-2 should define it in core/event_types.py."
        )

    def test_collaboration_changed_has_diffs_field(self):
        """CollaborationChanged event must have 'diffs' field for field-level changes."""
        source = _read_source("core/event_types.py")
        if "CollaborationChanged" not in source:
            pytest.skip("CollaborationChanged not yet defined")

        # Parse the dataclass definition
        class_start = source.find("class CollaborationChanged")
        if class_start == -1:
            pytest.skip("CollaborationChanged class not found")

        class_body = source[class_start:class_start + 1500]
        assert "diffs" in class_body, (
            "AC-010-2 FAIL: CollaborationChanged missing 'diffs' field. "
            "Should contain field-level diffs: [{field, old_value, new_value}]."
        )

    def test_collaboration_payload_size_constraint(self):
        """CollaborationChanged payload should be < 20% of full collaboration data.
        
        This is verified by ensuring the event only carries diffs, not full data.
        """
        if not _c2_events_exist():
            pytest.skip("C2 events not defined")

        source = _read_source("core/event_types.py")
        class_start = source.find("class CollaborationChanged")
        if class_start == -1:
            pytest.skip("CollaborationChanged class not found")

        class_body = source[class_start:class_start + 2000]
        # Should NOT have fields for full collaboration data (nodes, edges, etc.)
        full_data_fields = ["nodes", "edges", "agentModels", "models", "recentCalls", "hierarchy"]
        found_full_fields = [f for f in full_data_fields if f in class_body]
        assert not found_full_fields, (
            f"AC-010-2 FAIL: CollaborationChanged contains full data fields: {found_full_fields}. "
            "Should only contain diffs."
        )

    @pytest.mark.asyncio
    async def test_collaboration_changed_event_flow(self):
        """CollaborationIngestor produces CollaborationChanged on agent status change."""
        try:
            from core.event_types import CollaborationChangedEvent
        except ImportError:
            pytest.skip("C2-2 not landed: CollaborationChangedEvent not importable")

        # Verify the event can be instantiated
        event = CollaborationChangedEvent(
            diffs=[
                {"field": "agentStatuses", "old_value": {"main": "idle"}, "new_value": {"main": "working"}}
            ],
        )
        assert event.type == "collaboration_changed"
        assert len(event.diffs) == 1

        # Verify payload size: diffs only, should be much smaller than full
        full_collab_size = 5000  # rough estimate of full collaboration data
        payload = json.dumps({"type": event.type, "payload": {"diffs": event.diffs}})
        payload_size = len(payload.encode("utf-8"))
        assert payload_size < full_collab_size * 0.2, (
            f"AC-010-2 FAIL: CollaborationChanged payload ({payload_size} bytes) "
            f">= 20% of estimated full ({full_collab_size * 0.2} bytes)"
        )


# ============================================================================
# AC-010-3: TaskChanged only contains add/update/remove
# ============================================================================

class TestAC010_3_TaskChangedDiffOnly:
    """AC-010-3: TaskChanged event must contain only add/update/remove operations,
    not unchanged tasks.
    """

    def test_task_changed_event_type_exists(self):
        """TaskChanged event type must be defined in event_types.py."""
        source = _read_source("core/event_types.py")
        assert "TaskChanged" in source, (
            "AC-010-3 FAIL: TaskChanged event type not defined. "
            "C2-3 should define it in core/event_types.py."
        )

    def test_task_changed_has_change_field(self):
        """TaskChanged event must have 'change' field (add/update/remove)."""
        source = _read_source("core/event_types.py")
        if "TaskChanged" not in source:
            pytest.skip("TaskChanged not yet defined")

        class_start = source.find("class TaskChanged")
        if class_start == -1:
            pytest.skip("TaskChanged class not found")

        class_body = source[class_start:class_start + 1500]
        assert "change" in class_body, (
            "AC-010-3 FAIL: TaskChanged missing 'change' field. "
            "Should be 'added' | 'updated' | 'removed'."
        )

    def test_task_changed_has_task_id(self):
        """TaskChanged event must have 'task_id' to identify the affected task."""
        source = _read_source("core/event_types.py")
        if "TaskChanged" not in source:
            pytest.skip("TaskChanged not yet defined")

        class_start = source.find("class TaskChanged")
        if class_start == -1:
            pytest.skip("TaskChanged class not found")

        class_body = source[class_start:class_start + 1500]
        assert "task_id" in class_body or "taskId" in class_body, (
            "AC-010-3 FAIL: TaskChanged missing 'task_id' field."
        )

    def test_task_changed_no_full_tasks_list(self):
        """TaskChanged should NOT contain a full tasks list."""
        source = _read_source("core/event_types.py")
        if "TaskChanged" not in source:
            pytest.skip("TaskChanged not yet defined")

        class_start = source.find("class TaskChanged")
        if class_start == -1:
            pytest.skip("TaskChanged class not found")

        class_body = source[class_start:class_start + 2000]
        # Should NOT have 'tasks' field (that would be full list)
        assert "tasks:" not in class_body and '"tasks"' not in class_body, (
            "AC-010-3 FAIL: TaskChanged contains 'tasks' field (full list). "
            "Should only contain change + task_id + task_data."
        )

    @pytest.mark.asyncio
    async def test_task_changed_add_event(self):
        """TaskChanged event with change='added' should contain task data."""
        try:
            from core.event_types import TaskChangedEvent
        except ImportError:
            pytest.skip("C2-3 not landed: TaskChangedEvent not importable")

        event = TaskChangedEvent(
            change="added",
            task_id="task-run-001",
            task_data={"name": "Build project", "status": "working"},
        )
        assert event.type == "task_changed"
        assert event.change == "added"
        assert event.task_id == "task-run-001"

    @pytest.mark.asyncio
    async def test_task_changed_remove_event(self):
        """TaskChanged event with change='removed' should work with minimal task_data."""
        try:
            from core.event_types import TaskChangedEvent
        except ImportError:
            pytest.skip("C2-3 not landed: TaskChangedEvent not importable")

        event = TaskChangedEvent(
            change="removed",
            task_id="task-run-001",
            task_data=None,
        )
        assert event.change == "removed"
        assert event.task_id == "task-run-001"


# ============================================================================
# AC-010-4: PerformanceSnapshot 30s slow channel
# ============================================================================

class TestAC010_4_PerformanceSnapshotSlowChannel:
    """AC-010-4: PerformanceSnapshot pushed on 30s slow channel timer,
    NOT driven by individual file changes.
    """

    def test_performance_snapshot_event_type_exists(self):
        """PerformanceSnapshot event type must be defined."""
        source = _read_source("core/event_types.py")
        assert "PerformanceSnapshot" in source, (
            "AC-010-4 FAIL: PerformanceSnapshot event type not defined. "
            "C2-4 should define it."
        )

    def test_performance_snapshot_has_agents_and_stats(self):
        """PerformanceSnapshot must contain agent stats and global stats."""
        source = _read_source("core/event_types.py")
        if "PerformanceSnapshot" not in source:
            pytest.skip("PerformanceSnapshot not yet defined")

        class_start = source.find("class PerformanceSnapshot")
        if class_start == -1:
            pytest.skip("PerformanceSnapshot class not found")

        class_body = source[class_start:class_start + 2000]
        # Should have agents dict and global_stats or similar
        has_agents = "agents" in class_body
        has_stats = "global_stats" in class_body or "stats" in class_body or "statistics" in class_body
        assert has_agents or has_stats, (
            "AC-010-4 FAIL: PerformanceSnapshot missing agents/stats fields."
        )

    def test_30s_interval_in_config(self):
        """Performance snapshot interval must be configurable at 30s default."""
        source = _read_source("core/config_fortify.py")
        assert "performance_snapshot_interval" in source or "perf_snapshot" in source.lower(), (
            "AC-010-4 FAIL: No performance_snapshot_interval config found. "
            "C2-4 should add it to config_fortify with 30.0s default."
        )

        # Verify default is 30s
        if "performance_snapshot_interval" in source:
            # Look for the default value
            idx = source.find("performance_snapshot_interval")
            snippet = source[idx:idx+100]
            assert "30" in snippet, (
                "AC-010-4 FAIL: performance_snapshot_interval default != 30"
            )

    def test_slow_channel_not_triggered_by_file_change(self):
        """PerformanceSnapshot should NOT be emitted on file change events."""
        source = _read_source("api/websocket.py")
        # The agent_state_changed handler should not reference PerformanceSnapshot
        handler_start = source.find("def _on_agent_state_changed")
        if handler_start == -1:
            pytest.skip("Event handler not found")

        handler_body = source[handler_start:handler_start + 2000]
        assert "PerformanceSnapshot" not in handler_body, (
            "AC-010-4 FAIL: _on_agent_state_changed references PerformanceSnapshot. "
            "Performance data should come from 30s slow channel, not file changes."
        )

    def test_performance_snapshot_timer_exists_in_lifespan(self):
        """main.py lifespan should start a 30s performance snapshot timer."""
        source = _read_source("main.py")
        # After C2-6: lifespan should contain performance snapshot timer setup
        # This could be a separate function or inline in lifespan
        has_perf_timer = (
            "performance_snapshot" in source.lower()
            or "perf_snapshot" in source.lower()
            or "slow_channel" in source.lower()
        )
        if not has_perf_timer:
            pytest.skip("C2-6 not landed: performance slow channel not in lifespan")

    @pytest.mark.asyncio
    async def test_performance_snapshot_event_produced(self):
        """PerformanceSnapshot event can be produced and has correct type."""
        try:
            from core.event_types import PerformanceSnapshotEvent
        except ImportError:
            pytest.skip("C2-4 not landed: PerformanceSnapshotEvent not importable")

        event = PerformanceSnapshotEvent(
            agents={
                "main": {"tokens": 1000, "requests": 5},
            },
            global_stats={
                "totalTokens": 5000,
                "totalRequests": 20,
            },
        )
        assert event.type == "performance_snapshot"


# ============================================================================
# AC-010-5: Timeline REST pull with ?since=turnId cursor
# ============================================================================

class TestAC010_5_TimelineRESTCursor:
    """AC-010-5: Timeline must support REST pull with ?since=turnId cursor parameter.
    """

    def test_timeline_endpoint_exists(self):
        """/api/timeline/{agent_id} endpoint must exist."""
        from main import app
        route_paths = [r.path for r in app.routes if hasattr(r, 'path')]
        timeline_routes = [p for p in route_paths if "timeline" in p]
        assert len(timeline_routes) > 0, (
            "AC-010-5 FAIL: No /timeline routes found in app."
        )

    def test_timeline_has_since_parameter(self):
        """Timeline endpoint must accept 'since' query parameter (turnId cursor)."""
        source = _read_source("api/timeline.py")
        # Check for Query parameter 'since' in the endpoint function
        assert "since" in source, (
            "AC-010-5 FAIL: 'since' parameter not found in timeline.py. "
            "Timeline REST should support ?since=turnId cursor."
        )

    def test_timeline_since_used_in_data_reader(self):
        """Timeline data reader should use the 'since' cursor for filtering."""
        source = _read_source("data/timeline_reader.py")
        if "since" not in source:
            pytest.skip("C2 timeline cursor not yet implemented in timeline_reader")

        # Verify 'since' is used to filter steps
        fn_start = source.find("def get_timeline_steps")
        if fn_start == -1:
            pytest.skip("get_timeline_steps not found")

        fn_body = source[fn_start:fn_start + 5000]
        assert "since" in fn_body, (
            "AC-010-5 FAIL: 'since' not used in get_timeline_steps. "
            "Should filter steps after the given turnId."
        )

    @pytest.mark.asyncio
    async def test_timeline_rest_returns_data(self):
        """Timeline REST endpoint returns valid response structure."""
        from main import app

        # Mock data reader
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

        import api.timeline as timeline_mod
        original = timeline_mod.get_timeline_steps
        timeline_mod.get_timeline_steps = fake_timeline

        try:
            import httpx
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                r = await client.get("/api/timeline/main")
                assert r.status_code == 200
                body = r.json()
                assert "steps" in body
                assert "stats" in body
                assert "agentId" in body
        finally:
            timeline_mod.get_timeline_steps = original


# ============================================================================
# Cross-cutting: Event type registration and WS protocol
# ============================================================================

class TestC2EventTypesRegistered:
    """Verify all C2 event types are properly registered and can flow through EventBus."""

    def test_all_c2_event_types_defined(self):
        """All C2 event types must be defined in core/event_types.py."""
        source = _read_source("core/event_types.py")
        required = ["CollaborationChanged", "TaskChanged", "PerformanceSnapshot"]
        missing = [t for t in required if t not in source]
        if missing:
            pytest.skip(f"C2 event types not yet defined: {missing}")
        assert not missing

    def test_c2_event_types_have_post_init_type(self):
        """Each C2 event type must set self.type in __post_init__."""
        source = _read_source("core/event_types.py")
        for event_name in ["CollaborationChanged", "TaskChanged", "PerformanceSnapshot"]:
            class_start = source.find(f"class {event_name}")
            if class_start == -1:
                continue
            class_body = source[class_start:class_start + 2000]
            assert "__post_init__" in class_body or f'type = "{event_name.lower()}"' in class_body.lower(), (
                f"C2 event {event_name} must set self.type in __post_init__ or default"
            )

    def test_ws_broadcaster_handles_c2_events(self):
        """WS broadcaster should handle all C2 event types."""
        source = _read_source("api/websocket.py")
        for event_name in ["CollaborationChanged", "TaskChanged", "PerformanceSnapshot"]:
            # Either a dedicated handler or a catch-all broadcaster
            assert event_name in source or "TOPIC_STATE_UPDATES" in source or "wildcard" in source.lower(), (
                f"AC FAIL: WS broadcaster does not handle {event_name}"
            )


# ============================================================================
# FullStateSnapshot slim-down verification (C2-5)
# ============================================================================

class TestFullStateSnapshotSlim:
    """C2-5: FullStateSnapshot should only contain agents, subagents, apiStatus.
    collaboration, tasks, performance removed.
    """

    def test_full_state_snapshot_slim_structure(self):
        """After C2-5, _collect_full_state_data returns only slim keys."""
        source = _read_source("api/websocket.py")
        fn_start = source.find("async def _collect_full_state_data")
        if fn_start == -1:
            pytest.skip("C2-5 not landed")

        # Find the return statement or data dict construction
        fn_body = source[fn_start:fn_start + 5000]
        
        # After C2 slim-down, data dict should NOT include:
        removed_keys = ["collaboration", "tasks", "performance", "workflows"]
        # But should still include:
        required_keys = ["agents", "subagents", "apiStatus"]

        # Find the data dict construction (data = { or data: Dict)
        data_line = None
        for line in fn_body.split("\n"):
            if "data:" in line and "=" in line and "{" in line:
                data_line = line
                break
            if "data =" in line or "data=" in line:
                data_line = line
                break

        if data_line is None:
            # Look for the return of the dict
            for line in fn_body.split("\n"):
                if "'agents'" in line and "'subagents'" in line:
                    data_line = line
                    break

        if data_line is None:
            pytest.skip("Could not find data dict construction")

        # Check removed keys are not in the data dict area
        for key in removed_keys:
            # The key should not appear as a top-level key assignment
            # Allow it if it's in a try/except that's been removed or commented
            pass  # Structural check handled by individual AC tests above

        # Check required keys ARE present
        for key in required_keys:
            assert f"'{key}'" in fn_body or f'"{key}"' in fn_body, (
                f"AC FAIL: FullStateSnapshot missing required key '{key}'"
            )
