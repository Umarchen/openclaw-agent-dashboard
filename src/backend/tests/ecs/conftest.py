"""
Shared fixtures for ECS C0 tests.
Provides mock objects and helper functions for testing EventBus, StateStore,
FileChangeClassifier, AgentStateIngestor, and MetricsCollector.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock, AsyncMock
from dataclasses import dataclass, field

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


# ── C0 Event Types (specification-first definitions) ──────────────────

@dataclass
class FileChangeEvent:
    """File system change event emitted by file_watcher."""
    filepath: str
    change_type: str  # "created" | "modified" | "deleted"
    agent_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class HeartbeatTickEvent:
    """Periodic heartbeat tick (from polling mode, filepath=None)."""
    tick_count: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentStateChangedEvent:
    """Emitted when AgentStateIngestor updates StateStore."""
    agent_id: str
    old_status: Optional[str]
    new_status: str
    current_task: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class FileClassifiedEvent:
    """Emitted by FileChangeClassifier after classification."""
    filepath: str
    agent_id: str
    file_category: str  # "session_jsonl" | "sessions_index" | "subagent_runs" | "config" | "other"
    change_type: str
    timestamp: float = field(default_factory=time.time)


# ── Mock Helpers ─────────────────────────────────────────────────────────

@pytest.fixture
def event_loop():
    """Create a new event loop for each test."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def fake_openclaw_root(tmp_path: Path):
    """Minimal fake openclaw root for ECS tests."""
    root = tmp_path / ".openclaw"
    root.mkdir(parents=True, exist_ok=True)

    # agents/main/sessions structure
    agents_dir = root / "agents"
    agents_dir.mkdir(exist_ok=True)

    main_agent = agents_dir / "main"
    main_agent.mkdir(exist_ok=True)
    sessions_dir = main_agent / "sessions"
    sessions_dir.mkdir(exist_ok=True)

    # sessions.json index
    sessions_index = {
        "sessions": [
            {"id": "session-001", "status": "active", "updatedAt": 1746000000, "turns": 3},
            {"id": "session-002", "status": "completed", "updatedAt": 1745900000, "turns": 7},
        ]
    }
    sessions_dir.joinpath("sessions.json").write_text(json.dumps(sessions_index))

    # JSONL session file
    messages = [
        {"type": "start", "sessionId": "session-001", "timestamp": 1746000000},
        {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "hello"}], "timestamp": 1746000001}},
        {"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}], "stopReason": "end_turn", "timestamp": 1746000002}},
    ]
    sessions_dir.joinpath("session-001.jsonl").write_text(
        "\n".join(json.dumps(m) for m in messages) + "\n"
    )

    # subagents/runs.json
    subagents_dir = root / "subagents"
    subagents_dir.mkdir(exist_ok=True)
    subagents_dir.joinpath("runs.json").write_text(json.dumps({
        "version": 2,
        "runs": {}
    }))

    # openclaw.json config
    root.joinpath("openclaw.json").write_text(json.dumps({
        "agents": {
            "list": [
                {"id": "main", "name": "Main Agent", "default": True},
                {"id": "coder", "name": "Coder Agent"},
            ],
            "defaults": {}
        }
    }))

    return root


@pytest.fixture
def sample_agent_state():
    """Sample agent state data for testing StateStore."""
    return {
        "id": "main",
        "name": "Main Agent",
        "status": "idle",
        "currentTask": "",
        "lastActiveAt": 1746000000,
        "error": None,
    }


@pytest.fixture
def sample_jsonl_messages():
    """Sample JSONL messages for testing Ingestor tail-read."""
    return [
        {"type": "start", "sessionId": "s1", "timestamp": 1746000000},
        {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "do task A"}], "timestamp": 1746000001}},
        {"type": "message", "message": {"role": "assistant", "content": [{"type": "thinking", "thinking": "thinking..."}], "timestamp": 1746000002}},
        {"type": "message", "message": {"role": "assistant", "content": [{"type": "toolCall", "name": "Bash", "id": "tc1", "arguments": "{}"}], "timestamp": 1746000003}},
        {"type": "message", "message": {"role": "toolResult", "toolCallId": "tc1", "content": [{"type": "text", "text": "done"}], "timestamp": 1746000004}},
        {"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Task A completed."}], "stopReason": "end_turn", "timestamp": 1746000005}},
    ]
