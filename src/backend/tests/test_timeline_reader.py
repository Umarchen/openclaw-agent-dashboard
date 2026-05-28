"""Regression tests for timeline_reader I/O helpers."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


def test_read_text_lines_tail_mode_reads_small_file(tmp_path: Path) -> None:
    """max_lines > 0 must not return empty after seek-to-EOF on small jsonl files."""
    from data.timeline_reader import _read_text_lines

    session = tmp_path / "session.jsonl"
    session.write_text(
        '{"type":"session","id":"s1"}\n'
        '{"type":"message","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n',
        encoding="utf-8",
    )

    lines = _read_text_lines(session, max_lines=10)
    assert len(lines) == 2


def test_get_timeline_steps_subagent_small_session(tmp_path: Path, monkeypatch) -> None:
    """Sub-agent sessions under 64KB should produce timeline steps."""
    from data import timeline_reader as tl

    agent_id = "analyst-agent"
    session_id = "740a6a44-test"
    agent_dir = tmp_path / "agents" / agent_id / "sessions"
    agent_dir.mkdir(parents=True)
    session_file = agent_dir / f"{session_id}.jsonl"
    session_file.write_text(
        '{"type":"session","version":3,"id":"740a6a44-test","timestamp":"2026-05-28T13:03:10.984Z"}\n'
        '{"type":"message","id":"u1","timestamp":"2026-05-28T13:03:11.000Z","message":{"role":"user","content":[{"type":"text","text":"task"}]}}\n'
        '{"type":"message","id":"a1","timestamp":"2026-05-28T13:03:12.000Z","message":{"role":"assistant","content":[{"type":"text","text":"done"}],"stopReason":"stop"}}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(tl, "get_openclaw_root", lambda: tmp_path)

    def fake_resolve(agent_id: str, session_key=None):
        return session_file, session_id, f"agent:{agent_id}:subagent:test"

    monkeypatch.setattr(tl, "resolve_agent_session_jsonl", fake_resolve)
    monkeypatch.setattr(tl, "_get_main_agent_id", lambda: "project-manager")
    monkeypatch.setattr(tl, "_get_requester_info_for_session", lambda *_: {})
    monkeypatch.setattr(tl, "_subagent_run_anchor_ms", lambda *_: 1779973391013)

    result = tl.get_timeline_steps(agent_id)
    assert len(result["steps"]) >= 2
