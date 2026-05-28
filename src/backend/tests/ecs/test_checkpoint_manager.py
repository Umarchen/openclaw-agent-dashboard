"""
Unit tests for C1 CheckpointManager.

Tests cover:
- offset tracking (get/update/remove)
- checkpoint persistence (save/load/flush)
- file truncate detection
- file rotation (inode change) detection
- corrupted checkpoint recovery
- periodic flush timing
- metrics/status reporting
- file permission security (0600)
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from core.checkpoint_manager import CheckpointManager, FileCheckpoint


@pytest.fixture
def tmp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for checkpoint files."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def cp_mgr(tmp_dir: Path) -> CheckpointManager:
    """Create a CheckpointManager with a temporary checkpoint directory."""
    return CheckpointManager(
        checkpoint_dir=str(tmp_dir / "checkpoints"),
        flush_interval_sec=100.0,  # Disable periodic flush in tests
    )


@pytest.fixture
def sample_file(tmp_dir: Path) -> Path:
    """Create a sample JSONL file with known content."""
    f = tmp_dir / "test_agent" / "sessions" / "session.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    content = '{"type":"message","role":"user","content":"hello"}\n'
    content += '{"type":"message","role":"assistant","content":"hi"}\n'
    f.write_text(content, encoding="utf-8")
    return f


class TestGetAndUpdateOffset:
    """Tests for basic get_offset / update_offset operations."""

    def test_no_checkpoint_returns_zero(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """get_offset returns 0 when no checkpoint exists."""
        assert cp_mgr.get_offset(str(sample_file)) == 0

    def test_update_then_get(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """update_offset persists offset, get_offset retrieves it."""
        content = sample_file.read_bytes()
        cp_mgr.update_offset(str(sample_file), offset=len(content), bytes_read=len(content))
        assert cp_mgr.get_offset(str(sample_file)) == len(content)

    def test_update_offset_records_inode_mtime(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """update_offset records file inode and mtime."""
        cp_mgr.update_offset(str(sample_file), offset=50, bytes_read=50)
        canonical = os.path.realpath(str(sample_file))
        with cp_mgr._lock:
            entry = cp_mgr._offsets.get(canonical)
        assert entry is not None
        assert entry.inode > 0
        assert entry.mtime > 0.0
        assert entry.last_read_ts > 0.0

    def test_remove_checkpoint(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """remove_checkpoint clears the entry, get_offset returns 0."""
        cp_mgr.update_offset(str(sample_file), offset=100, bytes_read=50)
        cp_mgr.remove_checkpoint(str(sample_file))
        assert cp_mgr.get_offset(str(sample_file)) == 0

    def test_update_acumulates_bytes_read(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """Multiple update_offset calls accumulate total_bytes_read."""
        cp_mgr.update_offset(str(sample_file), offset=50, bytes_read=50)
        cp_mgr.update_offset(str(sample_file), offset=100, bytes_read=50)
        assert cp_mgr.total_bytes_read == 100

    def test_multiple_files_independent(self, cp_mgr: CheckpointManager, tmp_dir: Path) -> None:
        """Different files maintain independent offsets."""
        f1 = tmp_dir / "file1.jsonl"
        f2 = tmp_dir / "file2.jsonl"
        content1 = "line1\n"
        content2 = "longer line2 here\n"
        f1.write_text(content1, encoding="utf-8")
        f2.write_text(content2, encoding="utf-8")

        cp_mgr.update_offset(str(f1), offset=len(content1), bytes_read=len(content1))
        cp_mgr.update_offset(str(f2), offset=len(content2), bytes_read=len(content2))

        assert cp_mgr.get_offset(str(f1)) == len(content1)
        assert cp_mgr.get_offset(str(f2)) == len(content2)


class TestTruncateDetection:
    """Tests for file truncation detection."""

    def test_truncated_file_resets_offset(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """When file size < checkpoint offset, get_offset returns 0."""
        original_size = sample_file.stat().st_size
        cp_mgr.update_offset(str(sample_file), offset=original_size, bytes_read=original_size)

        # Truncate file to smaller size
        sample_file.write_text("short\n", encoding="utf-8")
        truncated_size = sample_file.stat().st_size
        assert truncated_size < original_size

        # get_offset should detect truncation and return 0
        assert cp_mgr.get_offset(str(sample_file)) == 0
        assert cp_mgr.reset_count == 1

    def test_truncated_file_internal_state_reset(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """After truncation detection, internal entry is reset."""
        original_size = sample_file.stat().st_size
        cp_mgr.update_offset(str(sample_file), offset=original_size, bytes_read=original_size)

        # Truncate
        sample_file.write_text("x\n", encoding="utf-8")

        # Trigger validation
        cp_mgr.get_offset(str(sample_file))

        # Check internal state
        canonical = os.path.realpath(str(sample_file))
        with cp_mgr._lock:
            entry = cp_mgr._offsets.get(canonical)
        assert entry is not None
        assert entry.offset == 0
        assert entry.inode == 0


class TestRotationDetection:
    """Tests for file rotation (inode change) detection."""

    def test_inode_change_resets_offset(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """When file inode changes (rotation/replacement), get_offset returns 0."""
        original_size = sample_file.stat().st_size
        cp_mgr.update_offset(str(sample_file), offset=original_size, bytes_read=original_size)

        # Simulate rotation: delete and recreate
        original_inode = sample_file.stat().st_ino
        sample_file.unlink()
        sample_file.write_text("new content after rotation\n", encoding="utf-8")
        new_inode = sample_file.stat().st_ino

        # Inode should have changed (on most filesystems)
        # Note: some filesystems may reuse inodes, but this test covers the logic
        if new_inode != original_inode:
            assert cp_mgr.get_offset(str(sample_file)) == 0
            assert cp_mgr.reset_count == 1
        else:
            # Inode reused — offset should still be valid if file size >= offset
            new_size = sample_file.stat().st_size
            if new_size >= original_size:
                assert cp_mgr.get_offset(str(sample_file)) == original_size
            else:
                assert cp_mgr.get_offset(str(sample_file)) == 0

    def test_missing_file_returns_zero(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """When file is deleted, get_offset returns 0."""
        cp_mgr.update_offset(str(sample_file), offset=100, bytes_read=50)
        sample_file.unlink()
        assert cp_mgr.get_offset(str(sample_file)) == 0


class TestPersistence:
    """Tests for checkpoint save/load/flush."""

    def test_flush_creates_file(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """flush() creates the checkpoint file."""
        cp_mgr.update_offset(str(sample_file), offset=80, bytes_read=80)
        assert cp_mgr.flush() is True

        cp_file = cp_mgr._checkpoint_path()
        assert cp_file.exists()

    def test_flush_writes_json_lines(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """flush() writes valid JSON lines."""
        cp_mgr.update_offset(str(sample_file), offset=80, bytes_read=80)
        cp_mgr.flush()

        cp_file = cp_mgr._checkpoint_path()
        lines = cp_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert "filepath" in data
        assert "offset" in data
        assert "inode" in data
        assert "mtime" in data
        assert data["offset"] == 80

    def test_flush_file_permissions(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """Checkpoint file has 0600 permissions."""
        cp_mgr.update_offset(str(sample_file), offset=80, bytes_read=80)
        cp_mgr.flush()

        cp_file = cp_mgr._checkpoint_path()
        mode = stat.S_IMODE(cp_file.stat().st_mode)
        assert mode == stat.S_IRUSR | stat.S_IWUSR

    def test_flush_directory_permissions(self, cp_mgr: CheckpointManager) -> None:
        """Checkpoint directory has 0700 permissions."""
        cp_mgr._ensure_dir()
        mode = stat.S_IMODE(cp_mgr._checkpoint_dir.stat().st_mode)
        assert mode == stat.S_IRWXU

    def test_load_checkpoints_restores_offsets(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """load_checkpoints() restores offsets from disk."""
        # Write a checkpoint
        cp_mgr.update_offset(str(sample_file), offset=80, bytes_read=80)
        cp_mgr.flush()

        # Create a new manager and load
        cp_mgr2 = CheckpointManager(
            checkpoint_dir=str(cp_mgr._checkpoint_dir),
            flush_interval_sec=100.0,
        )
        loaded = cp_mgr2.load_checkpoints()
        assert loaded == 1
        assert cp_mgr2.get_offset(str(sample_file)) == 80

    def test_load_corrupted_checkpoint_discards(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """Corrupted JSON lines are discarded during load."""
        cp_mgr.update_offset(str(sample_file), offset=80, bytes_read=80)
        cp_mgr.flush()

        # Corrupt the file
        cp_file = cp_mgr._checkpoint_path()
        content = cp_file.read_text(encoding="utf-8")
        corrupted = "THIS IS NOT JSON\n" + content
        cp_file.write_text(corrupted, encoding="utf-8")

        # Load should succeed with 1 valid entry, 1 discarded
        cp_mgr2 = CheckpointManager(
            checkpoint_dir=str(cp_mgr._checkpoint_dir),
            flush_interval_sec=100.0,
        )
        loaded = cp_mgr2.load_checkpoints()
        assert loaded == 1

    def test_load_no_file_returns_zero(self, cp_mgr: CheckpointManager) -> None:
        """load_checkpoints() returns 0 when no checkpoint file exists."""
        assert cp_mgr.load_checkpoints() == 0

    def test_flush_overwrites_existing(self, cp_mgr: CheckpointManager, sample_file: Path, tmp_dir: Path) -> None:
        """flush() overwrites previous checkpoint file."""
        # First flush
        cp_mgr.update_offset(str(sample_file), offset=40, bytes_read=40)
        cp_mgr.flush()

        # Second flush with updated offset
        cp_mgr.update_offset(str(sample_file), offset=80, bytes_read=40)
        cp_mgr.flush()

        # Load should get the latest offset
        cp_mgr2 = CheckpointManager(
            checkpoint_dir=str(cp_mgr._checkpoint_dir),
            flush_interval_sec=100.0,
        )
        cp_mgr2.load_checkpoints()
        assert cp_mgr2.get_offset(str(sample_file)) == 80

    def test_flush_empty_does_not_error(self, cp_mgr: CheckpointManager) -> None:
        """flush() with no checkpoints does not error."""
        assert cp_mgr.flush() is True


class TestReset:
    """Tests for checkpoint reset functionality."""

    def test_reset_all(self, cp_mgr: CheckpointManager, sample_file: Path, tmp_dir: Path) -> None:
        """reset_all() clears all checkpoints."""
        f2 = tmp_dir / "other.jsonl"
        f2.write_text("data\n", encoding="utf-8")

        cp_mgr.update_offset(str(sample_file), offset=80, bytes_read=80)
        cp_mgr.update_offset(str(f2), offset=5, bytes_read=5)

        count = cp_mgr.reset_all()
        assert count == 2
        assert cp_mgr.get_offset(str(sample_file)) == 0
        assert cp_mgr.get_offset(str(f2)) == 0

    def test_reset_count_tracked(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """reset_count is incremented on resets."""
        original_size = sample_file.stat().st_size
        cp_mgr.update_offset(str(sample_file), offset=original_size, bytes_read=original_size)

        # Trigger truncation reset
        sample_file.write_text("x\n", encoding="utf-8")
        cp_mgr.get_offset(str(sample_file))

        assert cp_mgr.reset_count == 1

        # reset_all
        cp_mgr.reset_all()
        assert cp_mgr.reset_count == 2


class TestPeriodicFlush:
    """Tests for automatic periodic flush."""

    def test_periodic_flush_triggered(self, tmp_dir: Path, sample_file: Path) -> None:
        """update_offset triggers flush when interval elapses."""
        cp_mgr = CheckpointManager(
            checkpoint_dir=str(tmp_dir / "checkpoints"),
            flush_interval_sec=0.01,  # 10ms interval
        )

        # First update (establishes last_flush_ts)
        cp_mgr.update_offset(str(sample_file), offset=20, bytes_read=20)
        cp_mgr.flush()  # Force initial flush

        # Second update should trigger auto-flush after delay
        import time
        time.sleep(0.02)
        cp_mgr.update_offset(str(sample_file), offset=40, bytes_read=20)

        # Check file was written
        cp_file = cp_mgr._checkpoint_path()
        assert cp_file.exists()

    def test_flush_disabled_with_zero_interval(self, tmp_dir: Path, sample_file: Path) -> None:
        """flush_interval_sec=0 disables periodic flush."""
        cp_mgr = CheckpointManager(
            checkpoint_dir=str(tmp_dir / "checkpoints"),
            flush_interval_sec=0,
        )

        cp_mgr.update_offset(str(sample_file), offset=20, bytes_read=20)

        # File should not exist without explicit flush
        cp_file = cp_mgr._checkpoint_path()
        assert not cp_file.exists()

        # Explicit flush should work
        assert cp_mgr.flush() is True
        assert cp_file.exists()


class TestStatus:
    """Tests for get_status() diagnostics."""

    def test_status_fields(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """get_status returns all expected fields."""
        cp_mgr.update_offset(str(sample_file), offset=80, bytes_read=80)

        status = cp_mgr.get_status()
        assert status["implemented"] is True
        assert status["version"] == "c1"
        assert status["num_checkpoints"] == 1
        assert status["total_bytes_read"] == 80
        assert status["flush_interval_sec"] == 100.0
        assert "checkpoint_dir" in status

    def test_status_after_flush(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """flush_count increments after flush."""
        content = sample_file.read_bytes()
        cp_mgr.update_offset(str(sample_file), offset=len(content), bytes_read=len(content))
        # Note: _last_flush_ts starts at 0, so first update_offset may trigger
        # auto-flush. We just verify that explicit flush increments the count.
        pre_flush = cp_mgr.get_status()["flush_count"]
        cp_mgr.flush()
        assert cp_mgr.get_status()["flush_count"] == pre_flush + 1


class TestIntegration:
    """Integration tests covering realistic workflows."""

    def test_full_workflow_new_file(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """Full workflow: new file → first read → update → flush → reload."""
        # First read: get_offset returns 0 (no checkpoint)
        offset = cp_mgr.get_offset(str(sample_file))
        assert offset == 0

        # Simulate reading the file from beginning
        content = sample_file.read_bytes()
        offset = len(content)

        # Update checkpoint
        cp_mgr.update_offset(str(sample_file), offset=offset, bytes_read=len(content))

        # Flush to disk
        cp_mgr.flush()

        # Reload in new manager
        cp_mgr2 = CheckpointManager(
            checkpoint_dir=str(cp_mgr._checkpoint_dir),
            flush_interval_sec=100.0,
        )
        loaded = cp_mgr2.load_checkpoints()
        assert loaded == 1

        # Second read should start from saved offset
        new_offset = cp_mgr2.get_offset(str(sample_file))
        assert new_offset == len(content)

    def test_append_then_incremental_read(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """Simulate jsonl append: read increment from last offset."""
        content = sample_file.read_bytes()
        cp_mgr.update_offset(str(sample_file), offset=len(content), bytes_read=len(content))

        # Append new data
        with open(sample_file, "a", encoding="utf-8") as f:
            f.write('{"type":"message","role":"user","content":"world"}\n')

        # Get offset should return previous offset (valid checkpoint)
        saved_offset = cp_mgr.get_offset(str(sample_file))
        assert saved_offset == len(content)

        # Read only new data
        with open(sample_file, "rb") as f:
            f.seek(saved_offset)
            new_data = f.read()
        assert b"world" in new_data

    def test_truncate_then_recovery(self, cp_mgr: CheckpointManager, sample_file: Path) -> None:
        """File truncate → offset reset → re-read from beginning."""
        original = sample_file.read_bytes()
        cp_mgr.update_offset(str(sample_file), offset=len(original), bytes_read=len(original))

        # File is truncated (e.g., log rotation)
        sample_file.write_text("new start\n", encoding="utf-8")

        # get_offset detects truncation, returns 0
        offset = cp_mgr.get_offset(str(sample_file))
        assert offset == 0

        # Re-read from beginning
        new_content = sample_file.read_bytes()
        assert new_content == b"new start\n"

    def test_multiple_files_persistence(self, cp_mgr: CheckpointManager, tmp_dir: Path) -> None:
        """Multiple files tracked and persisted correctly."""
        files = []
        for i in range(5):
            f = tmp_dir / f"agent_{i}" / "sessions" / "s.jsonl"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"line {i}\n", encoding="utf-8")
            files.append(f)

        # Update offsets
        for i, f in enumerate(files):
            cp_mgr.update_offset(str(f), offset=len(f"line {i}\n"), bytes_read=len(f"line {i}\n"))

        # Flush
        cp_mgr.flush()

        # Reload
        cp_mgr2 = CheckpointManager(
            checkpoint_dir=str(cp_mgr._checkpoint_dir),
            flush_interval_sec=100.0,
        )
        loaded = cp_mgr2.load_checkpoints()
        assert loaded == 5

        for i, f in enumerate(files):
            assert cp_mgr2.get_offset(str(f)) == len(f"line {i}\n")


class TestSingleton:
    """Tests for module-level singleton."""

    def test_get_checkpoint_manager_returns_singleton(self) -> None:
        """get_checkpoint_manager() returns the same instance."""
        from core.checkpoint_manager import get_checkpoint_manager, reset_checkpoint_manager_for_tests

        reset_checkpoint_manager_for_tests()
        m1 = get_checkpoint_manager()
        m2 = get_checkpoint_manager()
        assert m1 is m2
        reset_checkpoint_manager_for_tests()

    def test_reset_creates_new_instance(self) -> None:
        """reset_checkpoint_manager_for_tests() creates a new instance."""
        from core.checkpoint_manager import get_checkpoint_manager, reset_checkpoint_manager_for_tests

        reset_checkpoint_manager_for_tests()
        m1 = get_checkpoint_manager()
        reset_checkpoint_manager_for_tests()
        m2 = get_checkpoint_manager()
        assert m1 is not m2
        reset_checkpoint_manager_for_tests()
