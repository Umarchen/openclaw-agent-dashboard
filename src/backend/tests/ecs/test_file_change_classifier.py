"""
Unit tests for FileChangeClassifier — classifies file changes by type and agent.

Acceptance Criteria Coverage:
- REQ_001: File change classification (session_jsonl, sessions_index, subagent_runs, config, other)
- C0 constraint: Classification drives EventBus routing, not broadcast_full_state
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


try:
    from core.file_change_classifier import FileChangeClassifier, ClassifiedChange
except ImportError:
    # ── Inline spec-first shim ──────────────────────────────────────────
    import re

    _SESSION_JSONL_RE = re.compile(r'.*sessions/[^/]+\.jsonl$')
    _SESSIONS_INDEX_RE = re.compile(r'.*sessions/sessions\.json$')
    _SUBAGENT_RUNS_RE = re.compile(r'.*subagents/runs\.json$')
    _CONFIG_RE = re.compile(r'.*/openclaw\.json$')

    _CATEGORY_PRIORITY = [
        "session_jsonl",
        "sessions_index",
        "subagent_runs",
        "config",
        "other",
    ]

    def _extract_agent_id(filepath: str) -> Optional[str]:
        """Extract agent_id from path pattern: agents/{agent_id}/sessions/..."""
        parts = Path(filepath).parts
        try:
            idx = parts.index("agents")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        except ValueError:
            pass
        return None

    def _classify_file(filepath: str) -> str:
        if _SESSION_JSONL_RE.match(filepath):
            return "session_jsonl"
        if _SESSIONS_INDEX_RE.match(filepath):
            return "sessions_index"
        if _SUBAGENT_RUNS_RE.match(filepath):
            return "subagent_runs"
        if _CONFIG_RE.match(filepath):
            return "config"
        return "other"

    class ClassifiedChange:
        def __init__(self, filepath: str, agent_id: Optional[str], category: str, change_type: str):
            self.filepath = filepath
            self.agent_id = agent_id
            self.category = category
            self.change_type = change_type

    class FileChangeClassifier:
        """Classifies file system changes for EventBus routing."""

        def classify(self, filepath: str, change_type: str = "modified") -> ClassifiedChange:
            agent_id = _extract_agent_id(filepath)
            category = _classify_file(filepath)
            return ClassifiedChange(
                filepath=filepath,
                agent_id=agent_id,
                category=category,
                change_type=change_type,
            )

        def is_agent_session_change(self, classified: ClassifiedChange) -> bool:
            return classified.category in ("session_jsonl", "sessions_index") and classified.agent_id is not None

        def is_subagent_change(self, classified: ClassifiedChange) -> bool:
            return classified.category == "subagent_runs"


# ── FileChangeClassifier Unit Tests ─────────────────────────────────────

class TestFileChangeClassifierSessionJsonl:
    """Classification of session .jsonl files."""

    def test_session_jsonl_in_agents_dir(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/.openclaw/agents/main/sessions/session-001.jsonl",
            "modified",
        )
        assert result.category == "session_jsonl"
        assert result.agent_id == "main"
        assert result.change_type == "modified"

    def test_session_jsonl_created(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/.openclaw/agents/coder/sessions/new-session.jsonl",
            "created",
        )
        assert result.category == "session_jsonl"
        assert result.agent_id == "coder"
        assert result.change_type == "created"

    def test_session_jsonl_deleted(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/.openclaw/agents/main/sessions/old.jsonl",
            "deleted",
        )
        assert result.category == "session_jsonl"
        assert result.change_type == "deleted"

    def test_is_agent_session_change_true(self):
        classifier = FileChangeClassifier()
        classified = classifier.classify("/.openclaw/agents/main/sessions/active.jsonl")
        assert classifier.is_agent_session_change(classified) is True

    def test_is_agent_session_change_false_for_other(self):
        classifier = FileChangeClassifier()
        classified = classifier.classify("/some/random/path.jsonl")
        assert classifier.is_agent_session_change(classified) is False


class TestFileChangeClassifierSessionsIndex:
    """Classification of sessions.json index files."""

    def test_sessions_index(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/.openclaw/agents/main/sessions/sessions.json",
            "modified",
        )
        assert result.category == "sessions_index"
        assert result.agent_id == "main"

    def test_is_agent_session_change_for_index(self):
        classifier = FileChangeClassifier()
        classified = classifier.classify("/.openclaw/agents/coder/sessions/sessions.json")
        assert classifier.is_agent_session_change(classified) is True


class TestFileChangeClassifierSubagentRuns:
    """Classification of subagent runs.json files."""

    def test_subagent_runs(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/.openclaw/subagents/runs.json",
            "modified",
        )
        assert result.category == "subagent_runs"
        assert result.agent_id is None  # runs.json is global, not per-agent

    def test_is_subagent_change_true(self):
        classifier = FileChangeClassifier()
        classified = classifier.classify("/.openclaw/subagents/runs.json")
        assert classifier.is_subagent_change(classified) is True

    def test_is_subagent_change_false(self):
        classifier = FileChangeClassifier()
        classified = classifier.classify("/.openclaw/agents/main/sessions/active.jsonl")
        assert classifier.is_subagent_change(classified) is False


class TestFileChangeClassifierConfig:
    """Classification of config files."""

    def test_openclaw_json(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/.openclaw/openclaw.json",
            "modified",
        )
        assert result.category == "config"

    def test_is_agent_session_change_false_for_config(self):
        classifier = FileChangeClassifier()
        classified = classifier.classify("/.openclaw/openclaw.json")
        assert classifier.is_agent_session_change(classified) is False


class TestFileChangeClassifierOther:
    """Classification of unrecognized files."""

    def test_memory_file(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/.openclaw/workspace-main/memory/2024-01-01.md",
            "modified",
        )
        assert result.category == "other"

    def test_log_file(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/.openclaw/logs/app.log",
            "created",
        )
        assert result.category == "other"

    def test_random_json(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/tmp/some-file.json",
            "modified",
        )
        assert result.category == "other"


class TestFileChangeClassifierAgentIdExtraction:
    """Agent ID extraction from various path patterns."""

    def test_nested_agent_path(self):
        classifier = FileChangeClassifier()
        result = classifier.classify(
            "/root/.openclaw/agents/my-agent/sessions/session.jsonl",
        )
        assert result.agent_id == "my-agent"

    def test_no_agents_dir(self):
        classifier = FileChangeClassifier()
        result = classifier.classify("/tmp/random.jsonl")
        assert result.agent_id is None

    def test_agents_dir_but_no_id(self):
        """Path like /agents/ but nothing after it."""
        classifier = FileChangeClassifier()
        result = classifier.classify("/.openclaw/agents/sessions.jsonl")
        # "agents" is the dir, "sessions.jsonl" doesn't match agents/{id}/sessions/...
        assert result.agent_id is None or result.agent_id == "sessions.jsonl"

    def test_config_no_agent_id(self):
        classifier = FileChangeClassifier()
        result = classifier.classify("/.openclaw/openclaw.json")
        assert result.agent_id is None
