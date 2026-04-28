"""Shared pytest fixtures for backend tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


@pytest.fixture(autouse=True)
def reset_fortify_state():
    """Reset all fortify singletons between tests."""
    from core.config_fortify import refresh_fortify_config_cache
    from core.error_handler import reset_reliability_metrics_for_tests
    from core.fallback_manager import reset_fallback_handlers_for_tests
    from status.status_cache import reset_cache_for_tests

    reset_cache_for_tests()
    reset_fallback_handlers_for_tests()
    reset_reliability_metrics_for_tests()
    refresh_fortify_config_cache()
    yield
    reset_cache_for_tests()
    reset_fallback_handlers_for_tests()
    reset_reliability_metrics_for_tests()
    refresh_fortify_config_cache()


@pytest.fixture
def fake_openclaw_root(tmp_path: Path):
    """Minimal fake openclaw root with sessions.json index and JSONL fixtures."""
    root = tmp_path / ".openclaw"
    root.mkdir(parents=True, exist_ok=True)

    agents_dir = root / "agents"
    agents_dir.mkdir(exist_ok=True)

    main_agent = agents_dir / "main"
    main_agent.mkdir(exist_ok=True)

    # sessions/ subdirectory (canonical path: agents/<id>/sessions/)
    sessions_dir = main_agent / "sessions"
    sessions_dir.mkdir(exist_ok=True)

    # sessions.json index
    sessions_index = {
        "sessions": [
            {
                "id": "session-001",
                "status": "active",
                "updatedAt": 1746000000,
                "turns": 3,
            },
            {
                "id": "session-002",
                "status": "completed",
                "updatedAt": 1745900000,
                "turns": 7,
            },
        ]
    }
    sessions_file = sessions_dir / "sessions.json"
    sessions_file.write_text(json.dumps(sessions_index))

    # JSONL session file (in sessions/ subdirectory)
    session_jsonl = sessions_dir / "session-001.jsonl"
    messages = [
        {"type": "start", "sessionId": "session-001", "timestamp": 1746000000},
        {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]}},
        {"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}},
    ]
    session_jsonl.write_text("\n".join(json.dumps(m) for m in messages) + "\n")

    # JSONL with repaired line (trailing comma) — CA-003 fixture
    session_with_bad = sessions_dir / "session-002.jsonl"
    bad_messages = [
        json.dumps({"type": "start", "sessionId": "session-002"}),
        '{"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": "test"}]}}',
        '{"type": "end", "sessionId": "session-002", "status": "ok"}',
    ]
    session_with_bad.write_text("\n".join(bad_messages) + "\n")

    return root
