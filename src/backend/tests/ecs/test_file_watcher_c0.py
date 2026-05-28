"""
Unit tests for file_watcher C0 modifications.

Tests DebouncedHandler, agent_id extraction, health checks, and
verifies expectations about C0 changes to file_watcher.py.

NOTE: DebouncedHandler has a deadlock bug in the existing code:
  trigger() acquires self._lock, then calls do_callback() directly
  in the else branch, which also tries to acquire self._lock.
  This deadlocks on the first trigger when _last_trigger == 0.
  BUG reported to tech-lead. Tests are marked xfail until fixed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


# ── BUG NOTE ────────────────────────────────────────────────────────────
# DebouncedHandler has a reentrant lock deadlock in trigger():
#   1. trigger() acquires self._lock
#   2. If _last_trigger == 0 (first call), now - 0 > debounce_sec → else branch
#   3. else calls do_callback() which does: with self._lock: → DEADLOCK
# Fix: use threading.RLock() instead of threading.Lock(), or call do_callback()
#     outside the lock.
# Reported as BUG to tech-lead.
# ──────────────────────────────────────────────────────────────────────


class TestFileWatcherAgentIdExtraction:
    """Agent ID extraction from file paths — C0 prerequisite.

    These tests are skipped until extract_agent_id() is added by C0-5.
    """

    @pytest.fixture(autouse=True)
    def _check_function(self):
        import watchers.file_watcher as fw
        if not callable(getattr(fw, "extract_agent_id", None)):
            pytest.skip("C0-5 not landed: extract_agent_id() not yet implemented")

    def test_extract_agent_id_from_session_jsonl(self):
        """Extract agent ID from agents/<id>/sessions/<sid>/session.jsonl path."""
        import watchers.file_watcher as fw
        path = "/home/user/.openclaw/agents/main/sessions/abc123/session.jsonl"
        result = fw.extract_agent_id(path)
        assert result == "main", f"Expected 'main', got {result}"

    def test_extract_agent_id_from_subagent_runs(self):
        """Extract agent ID from subagent runs path."""
        import watchers.file_watcher as fw
        path = "/home/user/.openclaw/agents/main/runs/subagent_codex/run.jsonl"
        result = fw.extract_agent_id(path)
        assert result == "main", f"Expected 'main', got {result}"

    def test_extract_agent_id_no_match(self):
        """Return None for non-agent paths."""
        import watchers.file_watcher as fw
        path = "/home/user/.openclaw/config.json"
        result = fw.extract_agent_id(path)
        assert result is None

    def test_extract_agent_id_nested(self):
        """Handle nested agent directory structures."""
        import watchers.file_watcher as fw
        path = "/home/user/.openclaw/agents/coder-agent/sessions/xyz/session.jsonl"
        result = fw.extract_agent_id(path)
        assert result == "coder-agent"


class TestFileWatcherHealth:
    """Health check endpoints — C0 adds EventBus health status."""

    @pytest.fixture(autouse=True)
    def _check_function(self):
        import watchers.file_watcher as fw
        if not callable(getattr(fw, "get_health", None)):
            pytest.skip("get_health() not yet implemented in file_watcher.py")

    def test_health_returns_watcher_mode(self):
        """Health endpoint includes watcher_mode field."""
        import watchers.file_watcher as fw
        health = fw.get_health()
        assert "watcher_mode" in health
        assert health["watcher_mode"] in ("watchdog", "polling", "stopped")

    def test_health_returns_started_at(self):
        """Health endpoint includes started_at timestamp."""
        import watchers.file_watcher as fw
        health = fw.get_health()
        assert "started_at" in health


@pytest.mark.skip(
    reason="BUG: DebouncedHandler.trigger() has reentrant lock deadlock on first call. "
           "trigger() holds self._lock then calls do_callback() which re-acquires self._lock. "
           "Fix: use RLock or move do_callback() call outside lock scope. Cannot xfail because deadlock hangs the test."
)
class TestFileWatcherDebounceHandler:
    """DebouncedHandler behavior — unchanged in C0 but critical for correctness.
    These tests xfail due to a deadlock bug in the existing implementation."""

    def test_single_trigger_fires_immediately(self):
        import watchers.file_watcher as fw
        fired = []

        def cb(path):
            fired.append(path)

        handler = fw.DebouncedHandler(cb, debounce_sec=0.1)
        handler.trigger("/tmp/test.jsonl")
        time.sleep(0.15)
        assert len(fired) == 1
        assert fired[0] == "/tmp/test.jsonl"

    def test_rapid_triggers_debounced(self):
        import watchers.file_watcher as fw
        fired = []

        def cb(path):
            fired.append(path)

        handler = fw.DebouncedHandler(cb, debounce_sec=0.3)
        handler.trigger("/tmp/a.jsonl")
        handler.trigger("/tmp/b.jsonl")
        handler.trigger("/tmp/c.jsonl")
        assert len(fired) == 0
        time.sleep(0.4)
        assert len(fired) >= 1

    def test_trigger_with_none_path(self):
        """filepath=None represents polling tick."""
        import watchers.file_watcher as fw
        fired = []

        handler = fw.DebouncedHandler(lambda p: fired.append(p), debounce_sec=0.01)
        handler.trigger(None)
        time.sleep(0.05)
        assert len(fired) == 1
        assert fired[0] is None


class TestFileWatcherC0Expectations:
    """C0 expectations: file_watcher should use EventBus instead of broadcast_full_state."""

    def test_file_watcher_has_broadcast_full_state(self):
        """Pre-C0: file_watcher still imports broadcast_full_state.
        After C0-5, this should be removed and replaced with EventBus.publish."""
        fw_path = BACKEND / "watchers" / "file_watcher.py"
        source = fw_path.read_text(encoding="utf-8")
        assert "broadcast_full_state" in source, (
            "Expected broadcast_full_state reference in pre-C0 file_watcher.py"
        )

    def test_file_watcher_has_on_file_changed(self):
        """_on_file_changed function must exist (C0 modifies, doesn't remove)."""
        import watchers.file_watcher as fw
        assert hasattr(fw, "_on_file_changed")

    def test_extract_agent_id_function_exists(self):
        """extract_agent_id must exist for C0 EventBus integration."""
        import watchers.file_watcher as fw
        if not callable(getattr(fw, "extract_agent_id", None)):
            pytest.skip("C0-5 not landed: extract_agent_id() not yet implemented")
        assert callable(fw.extract_agent_id)
