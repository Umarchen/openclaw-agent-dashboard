"""Unit tests for FileChangeClassifier."""
from __future__ import annotations

from core.file_change_classifier import (
    classify,
    classify_memory_change,
    classify_session_change,
    classify_subagent_change,
    extract_agent_id_from_path,
)
from core.event_types import FileChangeEvent


class TestExtractAgentIdFromPath:
    def test_session_jsonl(self):
        result = extract_agent_id_from_path(
            "/openclaw/agents/agent:main/sessions/session-abc.jsonl"
        )
        assert result == "agent:main"

    def test_nested_session(self):
        result = extract_agent_id_from_path(
            "/openclaw/agents/agent:coder/sessions/deep/dir/file.jsonl"
        )
        assert result == "agent:coder"

    def test_subagents_dir(self):
        result = extract_agent_id_from_path("/openclaw/subagents/runs.json")
        assert result is None

    def test_memory_dir(self):
        result = extract_agent_id_from_path(
            "/openclaw/workspace-main/memory/2024-01-01.md"
        )
        assert result is None

    def test_no_agents_dir(self):
        result = extract_agent_id_from_path("/tmp/random.jsonl")
        assert result is None

    def test_agents_but_no_sessions(self):
        result = extract_agent_id_from_path("/openclaw/agents/agent:x/config.json")
        assert result is None

    def test_windows_style_path(self):
        result = extract_agent_id_from_path(
            "C:\\openclaw\\agents\\agent:main\\sessions\\session.jsonl"
        )
        assert result == "agent:main"


class TestClassify:
    def test_returns_file_change_event(self):
        evt = classify("/openclaw/agents/agent:main/sessions/abc.jsonl")
        assert isinstance(evt, FileChangeEvent)
        assert evt.type == "file_change"
        assert evt.agent_id == "agent:main"
        assert evt.change_type == "modified"

    def test_custom_change_type(self):
        evt = classify("/openclaw/agents/agent:x/sessions/new.jsonl", "created")
        assert evt.change_type == "created"

    def test_no_agent_id(self):
        evt = classify("/openclaw/subagents/runs.json")
        assert evt.agent_id is None

    def test_has_timestamp(self):
        evt = classify("/openclaw/agents/agent:a/sessions/b.jsonl")
        assert evt.timestamp


class TestClassifySessionChange:
    def test_session_path(self):
        result = classify_session_change(
            "/openclaw/agents/agent:pm/sessions/pm-123.jsonl"
        )
        assert result == "agent:pm"

    def test_non_session_path(self):
        result = classify_session_change("/tmp/other.jsonl")
        assert result is None


class TestClassifyMemoryChange:
    def test_memory_change(self):
        result = classify_memory_change("/openclaw/workspace-main/memory/daily.md")
        assert result is None


class TestClassifySubagentChange:
    def test_subagent_change(self):
        result = classify_subagent_change("/openclaw/subagents/runs.json")
        assert result is None
