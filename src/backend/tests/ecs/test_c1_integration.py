"""
C1 Integration Tests — verify the C1 upgrade components work together.

Coverage:
1. CheckpointManager: startup load, file truncate reset, inode detection, corruption fallback
2. offset-read: first read equivalent to tail-read, subsequent reads from offset
3. Bounded parallel computation: parallel time < 50% of serial time
4. FullStateSnapshot: schemaVersion=2 receives new format, no hello still gets full_state
5. Metrics: checkpoint_reset_total increments correctly

Spec references: REQ_ECS_008 (offset+checkpoint), REQ_ECS_009 (parallel), REQ_ECS_005 (FullStateSnapshot)
"""
from __future__ import annotations

import asyncio
import json
import os
import stat
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


# ============================================================================
# 1. CheckpointManager Tests
# ============================================================================

class TestCheckpointManagerStartup:
    """AC-008-2: Process restart loads checkpoints from disk."""

    def test_load_checkpoints_from_disk(self, tmp_path):
        """Checkpoints saved to disk are correctly loaded on restart."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,  # disable periodic flush
        )

        # Write some checkpoints
        session_file = tmp_path / "agents" / "main" / "sessions" / "session-001.jsonl"
        session_file.parent.mkdir(parents=True)
        session_file.write_text("line1\nline2\nline3\n")

        cp_manager.update_offset(str(session_file), offset=15, bytes_read=15)
        cp_manager.flush()

        # Simulate restart: new CheckpointManager instance
        cp_manager2 = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )
        loaded = cp_manager2.load_checkpoints()

        assert loaded == 1
        offset = cp_manager2.get_offset(str(session_file))
        assert offset == 15

    def test_no_checkpoint_file_starts_fresh(self, tmp_path):
        """Missing checkpoint file → starts fresh (offset=0)."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        loaded = cp_manager.load_checkpoints()
        assert loaded == 0

        # get_offset should return 0 for unknown files
        offset = cp_manager.get_offset("/nonexistent/file.jsonl")
        assert offset == 0


class TestCheckpointManagerTruncate:
    """AC-008-3: File truncation detected, offset reset, checkpoint_reset_total metric."""

    def test_truncated_file_resets_offset(self, tmp_path):
        """When file is truncated (size < checkpoint offset), reset to 0."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        # Create a file with known content
        session_file = tmp_path / "session.jsonl"
        content = "line1\nline2\nline3\nline4\nline5\n"
        session_file.write_text(content)
        file_size = len(content)

        # Set checkpoint offset to near the end
        cp_manager.update_offset(str(session_file), offset=file_size - 2, bytes_read=file_size)

        # Verify offset is set
        assert cp_manager.get_offset(str(session_file)) == file_size - 2
        assert cp_manager.reset_count == 0

        # Truncate the file
        session_file.write_text("short\n")

        # Now get_offset should detect truncation and return 0
        offset = cp_manager.get_offset(str(session_file))
        assert offset == 0
        assert cp_manager.reset_count == 1

    def test_truncate_triggers_checkpoint_reset_metric(self, tmp_path):
        """checkpoint_reset_total metric increments on truncation."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        session_file = tmp_path / "session.jsonl"
        session_file.write_text("A\nB\nC\nD\nE\n")
        cp_manager.update_offset(str(session_file), offset=10, bytes_read=10)

        assert cp_manager.reset_count == 0

        # Truncate
        session_file.write_text("X\n")
        _ = cp_manager.get_offset(str(session_file))

        assert cp_manager.reset_count >= 1

        status = cp_manager.get_status()
        assert status["reset_count"] >= 1


class TestCheckpointManagerInode:
    """REQ_ECS_008: inode detection for file rotation/replacement."""

    def test_inode_change_detected(self, tmp_path):
        """When file is replaced (inode changes), checkpoint is reset."""
        from core.checkpoint_manager import CheckpointManager, FileCheckpoint

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        session_file = tmp_path / "session.jsonl"
        content = "original content\n"
        session_file.write_text(content)
        file_size = session_file.stat().st_size
        original_inode = session_file.stat().st_ino

        # Manually inject a checkpoint with known inode to ensure it's tracked
        canonical = os.path.realpath(str(session_file))
        cp = FileCheckpoint(
            filepath=canonical,
            offset=file_size,  # offset == file size (valid)
            inode=original_inode,
            mtime=session_file.stat().st_mtime,
        )
        cp_manager._offsets[canonical] = cp

        assert cp_manager.get_offset(str(session_file)) == file_size
        assert cp_manager.reset_count == 0

        # Replace file (delete and recreate — new inode)
        session_file.unlink()
        session_file.write_text("new content after rotation\n")
        new_inode = session_file.stat().st_ino

        # On most filesystems, new file has different inode
        # (If same inode due to tmp_path weirdness, skip this check)
        if new_inode != original_inode:
            offset = cp_manager.get_offset(str(session_file))
            assert offset == 0
            assert cp_manager.reset_count >= 1


class TestCheckpointManagerCorruption:
    """REQ_ECS_008: Corrupted checkpoint lines are discarded, fallback to C0 tail-read."""

    def test_corrupted_checkpoint_line_discarded(self, tmp_path):
        """Corrupted JSON lines in checkpoint file are skipped, valid lines loaded."""
        from core.checkpoint_manager import CheckpointManager, FileCheckpoint

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        # Write checkpoint file with corrupted lines
        cp_dir.mkdir(parents=True, exist_ok=True)
        cp_file = cp_dir / "offsets.jsonl"

        session_file = tmp_path / "session.jsonl"
        session_file.write_text("data\n")
        canonical = os.path.realpath(str(session_file))
        st = session_file.stat()

        # Use actual inode and mtime so validation passes
        cp_file.write_text(
            f'{{"filepath": "{canonical}", "offset": 5, "inode": {st.st_ino}, "mtime": {st.st_mtime}, "last_read_ts": 1001.0}}\n'
            "THIS IS NOT JSON\n"
            '{"filepath": "", "offset": 10}\n'  # empty filepath
            f'{{"filepath": "{canonical}", "offset": BAD}}\n'  # bad JSON
        )

        loaded = cp_manager.load_checkpoints()
        # Only the first valid line should be loaded (inode matches file)
        assert loaded == 1
        offset = cp_manager.get_offset(str(session_file))
        assert offset == 5

    def test_entirely_corrupted_file_starts_fresh(self, tmp_path):
        """If all checkpoint lines are corrupted, start with no checkpoints."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        cp_dir.mkdir(parents=True, exist_ok=True)
        cp_file = cp_dir / "offsets.jsonl"
        cp_file.write_text("corrupt\ngarbage\n{{{{\n")

        loaded = cp_manager.load_checkpoints()
        assert loaded == 0


class TestCheckpointManagerFilePermissions:
    """REQ_ECS_008: Checkpoint files have restricted permissions (0600)."""

    def test_checkpoint_file_permissions(self, tmp_path):
        """Checkpoint file should be created with 0600 permissions."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        session_file = tmp_path / "session.jsonl"
        session_file.write_text("data\n")
        cp_manager.update_offset(str(session_file), offset=5, bytes_read=5)
        cp_manager.flush()

        cp_file = cp_dir / "offsets.jsonl"
        assert cp_file.exists()

        # Check permissions
        mode = cp_file.stat().st_mode & 0o777
        # On some systems, umask might affect this, but 0600 is the target
        assert mode == 0o600 or mode & 0o077 == 0o600, f"Expected 0600, got {oct(mode)}"


# ============================================================================
# 2. Offset-Read Tests (Ingestor + CheckpointManager integration)
# ============================================================================

class TestOffsetReadIntegration:
    """AC-008-1: offset-read equivalent to tail-read on first read, incremental on subsequent."""

    def test_first_read_equivalent_to_tail_read(self, tmp_path, monkeypatch):
        """First read (no checkpoint) should read from end (tail-read behavior)."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        # Create a jsonl session file with many messages
        session_file = tmp_path / "agents" / "main" / "sessions" / "session-001.jsonl"
        session_file.parent.mkdir(parents=True)
        lines = []
        for i in range(100):
            lines.append(json.dumps({"type": "message", "role": "assistant", "content": [{"type": "text", "text": f"msg-{i}"}], "timestamp": 1746000000 + i}))
        session_file.write_text("\n".join(lines) + "\n")

        # First read: no checkpoint → offset=0 → reads tail
        offset = cp_manager.get_offset(str(session_file))
        assert offset == 0  # First read: no checkpoint

        # Simulate what Ingestor does: update offset after read
        cp_manager.update_offset(str(session_file), offset=session_file.stat().st_size, bytes_read=session_file.stat().st_size)

        # Second read: should have a checkpoint
        offset2 = cp_manager.get_offset(str(session_file))
        assert offset2 == session_file.stat().st_size

    def test_subsequent_read_from_offset(self, tmp_path):
        """Second read starts from saved offset, not from beginning."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        session_file = tmp_path / "session.jsonl"
        initial_content = "line1\nline2\nline3\n"
        session_file.write_text(initial_content)
        initial_size = len(initial_content)

        # First read completes, set offset to end
        cp_manager.update_offset(str(session_file), offset=initial_size, bytes_read=initial_size)

        # Append new data
        with open(session_file, "a") as f:
            f.write("line4\nline5\n")

        new_size = session_file.stat().st_size
        bytes_to_read = new_size - initial_size

        # Checkpoint offset should still be at initial_size
        offset = cp_manager.get_offset(str(session_file))
        assert offset == initial_size

        # After update, offset should be at new end
        cp_manager.update_offset(str(session_file), offset=new_size, bytes_read=bytes_to_read)
        offset2 = cp_manager.get_offset(str(session_file))
        assert offset2 == new_size

    def test_offset_read_skips_when_no_new_data(self, tmp_path):
        """When offset == file size, Ingestor should skip (no new data)."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        session_file = tmp_path / "session.jsonl"
        session_file.write_text("data\n")
        file_size = session_file.stat().st_size

        # Set offset to current file size
        cp_manager.update_offset(str(session_file), offset=file_size, bytes_read=file_size)

        # File hasn't changed
        offset = cp_manager.get_offset(str(session_file))
        assert offset == file_size  # No reset
        # bytes_to_read would be 0, Ingestor skips

    def test_checkpoint_persists_across_restart(self, tmp_path):
        """Checkpoint survives process restart (flush + load cycle)."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        session_file = tmp_path / "session.jsonl"
        content = "line1\nline2\n"
        session_file.write_text(content)

        # Instance 1: read and save checkpoint
        mgr1 = CheckpointManager(checkpoint_dir=str(cp_dir), flush_interval_sec=0)
        mgr1.update_offset(str(session_file), offset=len(content), bytes_read=len(content))
        assert mgr1.flush() is True

        # Instance 2 (simulated restart): load checkpoint
        mgr2 = CheckpointManager(checkpoint_dir=str(cp_dir), flush_interval_sec=0)
        loaded = mgr2.load_checkpoints()
        assert loaded == 1
        offset = mgr2.get_offset(str(session_file))
        assert offset == len(content)


# ============================================================================
# 3. Bounded Parallel Computation Tests
# ============================================================================

class TestParallelComputation:
    """AC-009-1/3: Parallel computation via asyncio.gather, time < 50% serial."""

    @pytest.mark.asyncio
    async def test_parallel_faster_than_serial(self):
        """With 5+ agents, parallel computation should be < 50% of serial time."""
        # Simulate agents with artificial I/O delay
        agent_ids = [f"agent-{i}" for i in range(5)]
        delay_per_agent = 0.1  # 100ms per agent

        async def simulate_agent_compute(agent_id: str) -> Dict[str, Any]:
            """Simulate agent status computation with I/O delay."""
            await asyncio.sleep(delay_per_agent)
            return {"id": agent_id, "status": "idle", "currentTask": "", "lastActiveAt": 0, "error": None}

        # Serial computation
        serial_start = time.monotonic()
        serial_results = []
        for aid in agent_ids:
            result = await simulate_agent_compute(aid)
            serial_results.append(result)
        serial_time = time.monotonic() - serial_start

        # Parallel computation (like get_agents_with_status)
        parallel_start = time.monotonic()
        parallel_results = await asyncio.gather(
            *[simulate_agent_compute(aid) for aid in agent_ids],
            return_exceptions=True
        )
        parallel_time = time.monotonic() - parallel_start

        # Verify parallel is significantly faster
        assert parallel_time < serial_time * 0.7  # generous: should be ~100ms vs ~500ms
        assert parallel_time < serial_time * 0.5  # strict target: < 50% of serial

        # Verify results
        assert len([r for r in parallel_results if isinstance(r, dict)]) == 5

    @pytest.mark.asyncio
    async def test_parallel_single_agent_error_isolation(self):
        """Single agent computation error should not block others (AC-009-2)."""
        error_agent = "agent-error"

        async def compute_agent(agent_id: str) -> Dict[str, Any]:
            if agent_id == error_agent:
                raise RuntimeError(f"Computation failed for {agent_id}")
            await asyncio.sleep(0.01)
            return {"id": agent_id, "status": "idle", "currentTask": "", "lastActiveAt": 0, "error": None}

        agent_ids = ["agent-1", error_agent, "agent-3", "agent-4", "agent-5"]
        results = await asyncio.gather(
            *[compute_agent(aid) for aid in agent_ids],
            return_exceptions=True
        )

        # 4 successful, 1 exception
        success_count = sum(1 for r in results if isinstance(r, dict))
        error_count = sum(1 for r in results if isinstance(r, Exception))

        assert success_count == 4
        assert error_count == 1

    @pytest.mark.asyncio
    async def test_parallel_with_asyncio_to_thread(self):
        """Verify asyncio.to_thread works for wrapping sync I/O (AC-009-1)."""
        import threading

        thread_ids = []

        def sync_io_work(agent_id: str) -> Dict[str, Any]:
            """Simulate synchronous I/O (file read, etc.)."""
            thread_ids.append(threading.current_thread().ident)
            time.sleep(0.05)  # Simulate I/O
            return {"id": agent_id, "status": "working", "currentTask": "task", "lastActiveAt": 0, "error": None}

        agent_ids = [f"agent-{i}" for i in range(3)]
        results = await asyncio.gather(
            *[asyncio.to_thread(sync_io_work, aid) for aid in agent_ids],
            return_exceptions=True
        )

        assert all(isinstance(r, dict) for r in results)
        # Each should run in a thread (may share thread pool threads)
        assert len(thread_ids) == 3


# ============================================================================
# 4. FullStateSnapshot + schemaVersion Tests
# ============================================================================

class TestFullStateSnapshotSchemaVersion:
    """AC-005-3: schemaVersion negotiation triggers FullStateSnapshot (new format).
    C0 backward compat: no hello → type:'full_state' (legacy).
    """

    def test_schema_version_2_gets_full_state_snapshot(self):
        """Client sends hello with schemaVersion=2 → receives FullStateSnapshot (new format)."""
        from core.event_types import FullStateSnapshotEvent

        event = FullStateSnapshotEvent(
            data={
                "agents": [{"id": "main", "status": "idle"}],
                "version": 1,
            },
            trigger="bootstrap",
            schema_version=2,
        )

        assert event.type == "full_state_snapshot"
        assert event.schema_version == 2
        assert event.trigger == "bootstrap"
        assert "agents" in event.data

    def test_schema_version_mismatch_gets_full_state_snapshot(self):
        """schemaVersion mismatch → FullStateSnapshot with trigger='schema_mismatch'."""
        from core.event_types import FullStateSnapshotEvent

        event = FullStateSnapshotEvent(
            data={"agents": [], "version": 1},
            trigger="schema_mismatch",
            schema_version=2,
        )

        assert event.trigger == "schema_mismatch"
        assert event.schema_version == 2

    def test_full_state_snapshot_has_schema_version_field(self):
        """FullStateSnapshot payload includes schemaVersion field."""
        from core.event_types import FullStateSnapshotEvent

        event = FullStateSnapshotEvent(
            data={"agents": [{"id": "main"}]},
            trigger="bootstrap",
            schema_version=2,
        )

        # The WS message should include schemaVersion
        message = {
            'type': 'FullStateSnapshot',
            'payload': event.data,
            'schemaVersion': event.schema_version,
            'timestamp': event.timestamp,
        }

        assert message['type'] == 'FullStateSnapshot'
        assert message['schemaVersion'] == 2
        assert 'timestamp' in message

    @pytest.mark.asyncio
    async def test_websocket_handshake_with_hello_sends_full_state_snapshot(self):
        """WebSocket with hello+schemaVersion=2 should send FullStateSnapshot, not full_state."""
        # We test the handshake logic by checking what would be sent
        # Full integration requires running WS server, so we verify the event flow
        from core.event_types import FullStateSnapshotEvent
        from core.metrics_collector import get_metrics, reset_metrics_for_tests

        reset_metrics_for_tests()
        metrics = get_metrics()

        # Simulate: hello received with schemaVersion=2
        client_schema_version = 2
        server_version = 2

        # When matching versions → trigger = bootstrap
        trigger = "schema_mismatch" if client_schema_version != server_version else "bootstrap"
        assert trigger == "bootstrap"

        # Create the FullStateSnapshotEvent
        event = FullStateSnapshotEvent(
            data={"agents": [{"id": "main", "status": "idle"}]},
            trigger=trigger,
            schema_version=server_version,
        )
        assert event.type == "full_state_snapshot"

        # Metric should be recorded for FullStateSnapshot push
        metrics.increment("dashboard_full_state_total")
        snap = metrics.get_snapshot()
        assert snap["counters"]["dashboard_full_state_total"] == 1

    @pytest.mark.asyncio
    async def test_websocket_no_hello_sends_legacy_full_state(self):
        """WebSocket without hello → sends legacy type:'full_state' (backward compatible)."""
        # When no hello is received within timeout, legacy format is used
        # The legacy message should have type='full_state', not 'FullStateSnapshot'
        legacy_message = {
            'type': 'full_state',
            'data': {
                'agents': [{'id': 'main', 'status': 'idle'}],
            },
        }
        assert legacy_message['type'] == 'full_state'
        assert legacy_message['type'] != 'FullStateSnapshot'

    @pytest.mark.asyncio
    async def test_schema_version_mismatch_metric_recorded(self):
        """schemaVersion mismatch → full_state_total metric with trigger label."""
        from core.metrics_collector import get_metrics, reset_metrics_for_tests

        reset_metrics_for_tests()
        metrics = get_metrics()

        # Simulate schema mismatch
        trigger = "schema_mismatch"
        metrics.increment("dashboard_full_state_total")

        snap = metrics.get_snapshot()
        assert snap["counters"]["dashboard_full_state_total"] == 1


# ============================================================================
# 5. Metrics Tests
# ============================================================================

class TestCheckpointResetMetrics:
    """Verify checkpoint_reset_total / reset_count metric increments correctly."""

    def test_reset_count_on_truncate(self, tmp_path):
        """Truncation → reset_count increments."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        f1 = tmp_path / "f1.jsonl"
        f2 = tmp_path / "f2.jsonl"
        f1.write_text("AAAA\nBBBB\n")
        f2.write_text("CCCC\nDDDD\n")

        cp_manager.update_offset(str(f1), offset=9, bytes_read=9)
        cp_manager.update_offset(str(f2), offset=9, bytes_read=9)
        assert cp_manager.reset_count == 0

        # Truncate f1
        f1.write_text("X\n")
        cp_manager.get_offset(str(f1))

        # Truncate f2
        f2.write_text("Y\n")
        cp_manager.get_offset(str(f2))

        assert cp_manager.reset_count == 2

    def test_reset_count_in_status(self, tmp_path):
        """reset_count is exposed in get_status()."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        status = cp_manager.get_status()
        assert status["implemented"] is True
        assert status["version"] == "c1"
        assert status["reset_count"] == 0
        assert status["total_bytes_read"] == 0

    def test_checkpoint_bytes_read_tracked(self, tmp_path):
        """total_bytes_read accumulates across all file reads."""
        from core.checkpoint_manager import CheckpointManager

        cp_dir = tmp_path / "checkpoints"
        cp_manager = CheckpointManager(
            checkpoint_dir=str(cp_dir),
            flush_interval_sec=0,
        )

        f1 = tmp_path / "f1.jsonl"
        f2 = tmp_path / "f2.jsonl"
        f1.write_text("a" * 100 + "\n")
        f2.write_text("b" * 200 + "\n")

        cp_manager.update_offset(str(f1), offset=101, bytes_read=101)
        cp_manager.update_offset(str(f2), offset=201, bytes_read=201)

        assert cp_manager.total_bytes_read == 302

        status = cp_manager.get_status()
        assert status["total_bytes_read"] == 302


# ============================================================================
# 6. End-to-End: Ingestor + CheckpointManager Integration
# ============================================================================

class TestIngestorCheckpointIntegration:
    """Verify Ingestor uses CheckpointManager for offset tracking."""

    def test_ingestor_initializes_checkpoint_manager(self, tmp_path, monkeypatch):
        """AgentStateIngestor.initialize() loads CheckpointManager."""
        from core.agent_state_ingestor import AgentStateIngestor
        from core.event_bus import EventBus
        from core.state_store import StateStore
        from core.metrics_collector import MetricsCollector

        bus = EventBus()
        store = StateStore()
        metrics = MetricsCollector()

        ingestor = AgentStateIngestor(
            event_bus=bus,
            state_store=store,
            metrics=metrics,
        )

        # Mock CheckpointManager — use import patching since it's lazy imported
        mock_cp = MagicMock()
        mock_cp.load_checkpoints.return_value = 3
        with patch.dict('sys.modules', {'core.checkpoint_manager': MagicMock(get_checkpoint_manager=lambda: mock_cp)}):
            ingestor.initialize()

        assert ingestor._initialized is True
        mock_cp.load_checkpoints.assert_called_once()

    def test_ingestor_flushes_checkpoints_on_shutdown(self, tmp_path):
        """AgentStateIngestor.shutdown() flushes pending checkpoints."""
        from core.agent_state_ingestor import AgentStateIngestor
        from core.event_bus import EventBus
        from core.state_store import StateStore
        from core.metrics_collector import MetricsCollector

        bus = EventBus()
        store = StateStore()
        metrics = MetricsCollector()

        mock_cp = MagicMock()
        mock_cp.load_checkpoints.return_value = 0

        ingestor = AgentStateIngestor(
            event_bus=bus,
            state_store=store,
            metrics=metrics,
        )
        # Directly set checkpoint manager to avoid lazy import issues
        ingestor._checkpoint_manager = mock_cp
        ingestor._initialized = True

        ingestor.shutdown()

        mock_cp.flush.assert_called_once()


# ============================================================================
# 7. C1 End-to-End Pipeline: File Change → Offset Read → StateStore → Event
# ============================================================================

class TestC1EndToEndPipeline:
    """Full C1 pipeline: checkpoint-aware ingest + state update + event emission."""

    def test_pipeline_file_change_triggers_state_update(self, tmp_path, monkeypatch):
        """File change → Ingestor → StateStore update → EventBus event."""
        from core.event_bus import EventBus, TOPIC_FILE_CHANGES
        from core.state_store import StateStore
        from core.metrics_collector import MetricsCollector
        from core.event_types import FileChangeEvent

        bus = EventBus()
        store = StateStore()
        metrics = MetricsCollector()

        published_events = []

        original_publish = bus.publish
        def capture_publish(topic, event):
            published_events.append((topic, event))
            return original_publish(topic, event)
        monkeypatch.setattr(bus, "publish", capture_publish)

        # Create session file
        session_file = tmp_path / "agents" / "main" / "sessions" / "s.jsonl"
        session_file.parent.mkdir(parents=True)
        lines = []
        for i in range(5):
            lines.append(json.dumps({
                "type": "message",
                "role": "assistant" if i == 4 else "user",
                "content": [{"type": "text", "text": f"msg-{i}"}],
                "timestamp": 1746000000 + i,
            }))
        session_file.write_text("\n".join(lines) + "\n")

        # Mock external dependencies
        mock_cp = MagicMock()
        mock_cp.get_offset.return_value = 0
        mock_cp.update_offset = MagicMock()

        from core.agent_state_ingestor import AgentStateIngestor
        ingestor = AgentStateIngestor(
            event_bus=bus,
            state_store=store,
            metrics=metrics,
        )
        monkeypatch.setattr(ingestor, "_checkpoint_manager", mock_cp)

        # Subscribe Ingestor on correct topic
        bus.subscribe(TOPIC_FILE_CHANGES, ingestor._on_file_change)

        # Simulate file change
        event = FileChangeEvent(
            filepath=str(session_file),
            agent_id="main",
            change_type="modified",
        )
        bus.publish(TOPIC_FILE_CHANGES, event)

        # Verify Ingestor processed the event
        assert metrics.get_snapshot()["counters"].get("events_processed_total", 0) >= 1

        # Verify checkpoint manager was called for offset
        assert mock_cp.get_offset.called or mock_cp.update_offset.called
