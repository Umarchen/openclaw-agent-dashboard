"""Tests for TECHDEBT_FORTIFY modules."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _stub_file_watcher_for_testclient(monkeypatch) -> None:
    """避免 TestClient 触发 lifespan 时真实启动监听线程导致用例挂起。"""
    import watchers.file_watcher as fw

    monkeypatch.setattr(fw, "start_file_watcher", lambda loop: None)
    monkeypatch.setattr(fw, "stop_file_watcher", lambda: None)


@pytest.fixture(autouse=True)
def reset_cache_and_fortify_config():
    from core.config_fortify import refresh_fortify_config_cache
    from core.fallback_manager import reset_fallback_handlers_for_tests
    from status.status_cache import reset_cache_for_tests

    reset_cache_for_tests()
    reset_fallback_handlers_for_tests()
    refresh_fortify_config_cache()
    yield
    reset_cache_for_tests()
    reset_fallback_handlers_for_tests()
    refresh_fortify_config_cache()


def test_status_cache_hits_misses():
    from status.status_cache import StatusCache

    c = StatusCache(ttl_ms=60_000, max_size=10, max_memory_mb=50)
    assert c.get("x") is None
    c.set("x", {"status": "idle"})
    assert c.get("x") is not None
    assert c.get("x") is not None
    st = c.get_stats()
    assert st["stats"]["misses"] >= 1
    assert st["stats"]["hits"] >= 1


def test_attempt_line_json_repair_trailing_comma():
    from utils.data_repair import attempt_line_json_repair

    fixed, log = attempt_line_json_repair('{"a":1,}')
    assert fixed is not None
    assert json.loads(fixed)["a"] == 1
    assert log


def test_parse_session_jsonl_line_message():
    from utils.data_repair import parse_session_jsonl_line

    line = json.dumps({"type": "message", "message": {"role": "user", "content": []}})
    env, msg = parse_session_jsonl_line(line, json_strict=True, auto_repair=False)
    assert env is not None and msg is not None
    assert msg["role"] == "user"


def test_framework_error_stats():
    from core.error_handler import get_framework_error_stats, record_error

    record_error("network", "test err", "scope:test")
    s = get_framework_error_stats()
    assert s["total_count"] >= 1
    assert "network" in s["by_type"] or any("network" in k for k in s["by_type"])


def test_calculate_agent_status_io_fallback_uses_stale_cache(monkeypatch):
    """REQ_003-AC-003：重算路径 OSError 时读缓存中的最近状态。"""
    from status import status_calculator as sc
    from status.status_cache import get_cache

    get_cache().set("aid", {"status": "working"})

    def boom(*a, **k):
        raise OSError("simulated fs")

    monkeypatch.setattr(sc, "has_recent_errors", boom)
    assert sc.calculate_agent_status("aid", use_cache=False) == "working"
    assert get_cache().get_stats()["stats"]["stale_fallback_reads"] >= 1


def test_calculate_agent_status_io_fallback_disabled(monkeypatch):
    from core.config_fortify import refresh_fortify_config_cache
    from status import status_calculator as sc
    from status.status_cache import get_cache

    monkeypatch.setenv("OPENCLAW_FALLBACK_CACHE_ON_IO", "false")
    refresh_fortify_config_cache()
    get_cache().set("aid", {"status": "working"})

    def boom(*a, **k):
        raise OSError("simulated fs")

    monkeypatch.setattr(sc, "has_recent_errors", boom)
    assert sc.calculate_agent_status("aid", use_cache=False) == "idle"


def test_fallback_manager_register_overrides_default():
    from core import fallback_manager as fm

    def always_idle(agent_id=None, **kw):
        return "idle"

    fm.register_fallback("network", always_idle)
    assert fm.run_fallback("network", agent_id="x") == "idle"


def test_fortify_api_routes(monkeypatch):
    import asyncio
    import httpx
    _stub_file_watcher_for_testclient(monkeypatch)
    from main import app

    async def _run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
            r = await c.get("/api/health/watcher")
            assert r.status_code == 200
            body = r.json()
            assert "mode" in body
            assert "status" in body
            assert "switch_count" in body
            assert "error_count" in body
            assert "persisted_snapshot" in body

            r2 = await c.get("/api/cache/stats")
            assert r2.status_code == 200
            assert "hit_rate" in r2.json()

            r3 = await c.get("/api/errors/stats")
            assert r3.status_code == 200
            j = r3.json()
            assert "framework" in j
            assert "totalCount" in j or "total_count" in j.get("framework", {})

    asyncio.run(_run())


def test_data_validate_requires_agent(monkeypatch):
    import asyncio
    import httpx
    _stub_file_watcher_for_testclient(monkeypatch)
    from main import app

    async def _run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
            r = await c.get("/api/data/validate")
            assert r.status_code == 422

    asyncio.run(_run())


def test_get_session_validation_report_integrity_and_policy(monkeypatch, tmp_path):
    import data.session_reader as session_reader

    aid = "demo"
    sess = tmp_path / "agents" / aid / "sessions"
    sess.mkdir(parents=True)
    line = {
        "type": "message",
        "message": {"role": "user", "content": []},
    }
    (sess / "a.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    (sess / "sessions.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(session_reader, "get_openclaw_root", lambda: tmp_path)

    rep = session_reader.get_session_validation_report(aid)
    assert rep["validation_passed"] is True
    assert rep["file_integrity"] and rep["file_integrity"].get("sha256")
    assert rep["file_integrity"].get("hash_scope") == "full"
    assert "read_path_policy" in rep
    assert "disk_write_back_enabled" in rep["read_path_policy"]
    assert rep["sessions_index_path"]


def test_get_session_validation_report_specific_jsonl(monkeypatch, tmp_path):
    import data.session_reader as session_reader

    aid = "x"
    sess = tmp_path / "agents" / aid / "sessions"
    sess.mkdir(parents=True)
    good = {"type": "message", "message": {"role": "user", "content": []}}
    bad_line = "{not json"
    (sess / "old.jsonl").write_text(bad_line + "\n", encoding="utf-8")
    (sess / "new.jsonl").write_text(json.dumps(good, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setattr(session_reader, "get_openclaw_root", lambda: tmp_path)

    r_old = session_reader.get_session_validation_report(
        aid, relative_session_file="old.jsonl", include_details=True
    )
    assert r_old["validation_passed"] is False
    assert r_old["repair_report"]["failed_repairs"]

    r_escape = session_reader.get_session_validation_report(
        aid, relative_session_file="../escape.jsonl"
    )
    assert r_escape["validation_passed"] is False
    assert any(e.get("type") == "invalid_session_file" for e in r_escape["errors"])


def test_data_validate_session_file_query_param(monkeypatch, tmp_path):
    import asyncio
    import httpx
    import data.session_reader as session_reader
    _stub_file_watcher_for_testclient(monkeypatch)
    monkeypatch.setattr(session_reader, "get_openclaw_root", lambda: tmp_path)
    from main import app

    aid = "apiagent"
    sess = tmp_path / "agents" / aid / "sessions"
    sess.mkdir(parents=True)
    line = {"type": "message", "message": {"role": "user", "content": []}}
    (sess / "pick.jsonl").write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")

    async def _run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
            r = await c.get(
                "/api/data/validate",
                params={"agent_id": aid, "session_file": "pick.jsonl"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["validation_passed"] is True
            assert "pick.jsonl" in (body.get("session_file") or "")

    asyncio.run(_run())


def test_audit_repair_emits_audit_log(caplog):
    import logging

    from utils.data_repair import audit_repair

    with caplog.at_level(logging.INFO, logger="openclaw.fortify.audit"):
        audit_repair("unit_test", "orig", "fixed")
    assert any("audit_repair" in r.getMessage() for r in caplog.records)


def test_chain_reader_load_runs_via_subagent_reader(monkeypatch, tmp_path):
    import data.chain_reader as chain_reader
    import data.subagent_reader as subagent_reader

    (tmp_path / "subagents").mkdir(parents=True)
    (tmp_path / "subagents" / "runs.json").write_text(
        json.dumps(
            {
                "version": 2,
                "runs": {
                    "run-z": {
                        "childSessionKey": "agent:demo:sk",
                        "requesterSessionKey": "agent:parent:sk0",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(chain_reader, "get_openclaw_root", lambda: tmp_path)
    monkeypatch.setattr(subagent_reader, "get_openclaw_root", lambda: tmp_path)
    data = chain_reader._load_runs()
    assert data.get("version") == 2
    assert "run-z" in data.get("runs", {})


def test_performance_parse_session_file_uses_fortify_parser(tmp_path):
    """parse_session_file / parse_session_file_with_details 经 parse_session_jsonl_line。"""
    import json
    from pathlib import Path

    from api.performance import parse_session_file, parse_session_file_with_details

    line_obj = {
        "type": "message",
        "id": "m1",
        "timestamp": "2026-01-01T12:00:00.000Z",
        "message": {
            "role": "assistant",
            "model": "test-model",
            "usage": {"totalTokens": 42, "input": 20, "output": 22},
            "content": [],
        },
    }
    p = tmp_path / "sess.jsonl"
    p.write_text(json.dumps(line_obj, ensure_ascii=False) + "\n", encoding="utf-8")

    details = parse_session_file_with_details(Path(p), "agent-x")
    assert len(details) == 1
    assert details[0]["tokens"] == 42
    assert details[0]["model"] == "test-model"

    msgs = parse_session_file(Path(p), range_hours=0)
    assert len(msgs) == 1
    assert msgs[0]["tokens"] == 42
    assert msgs[0]["is_request"] is True


def test_sessions_index_strict_invalid_returns_zero(monkeypatch, tmp_path):
    """sessions.json 根非 object 时，严格模式下 get_session_updated_at 返回 0。"""
    import data.session_reader as session_reader
    from core.config_fortify import refresh_fortify_config_cache

    monkeypatch.setenv("OPENCLAW_JSON_STRICT", "true")
    refresh_fortify_config_cache()

    sess = tmp_path / "agents" / "main" / "sessions"
    sess.mkdir(parents=True)
    (sess / "sessions.json").write_text("[]", encoding="utf-8")

    monkeypatch.setattr(session_reader, "get_openclaw_root", lambda: tmp_path)

    assert session_reader.get_session_updated_at("main") == 0


def test_load_subagent_runs_injects_run_id_from_dict_key(monkeypatch, tmp_path):
    """OpenClaw runs.json 常以 runId 为键，值内可无 runId 字段。"""
    import data.subagent_reader as subagent_reader

    (tmp_path / "subagents").mkdir(parents=True)
    (tmp_path / "subagents" / "runs.json").write_text(
        json.dumps(
            {
                "version": 2,
                "runs": {
                    "run-abc": {
                        "childSessionKey": "agent:demo:sk1",
                        "requesterSessionKey": "agent:parent:sk0",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(subagent_reader, "get_openclaw_root", lambda: tmp_path)
    runs = subagent_reader.load_subagent_runs()
    assert len(runs) == 1
    assert runs[0].get("runId") == "run-abc"


def test_error_analyzer_parse_session_uses_fortify_parser(tmp_path):
    """parse_session_for_errors 经 parse_session_jsonl_line。"""
    from data.error_analyzer import parse_session_for_errors

    line = {
        "type": "message",
        "timestamp": "2026-01-01T00:00:00.000Z",
        "message": {
            "role": "assistant",
            "stopReason": "error",
            "errorMessage": "boom",
            "content": [],
        },
    }
    p = tmp_path / "s.jsonl"
    p.write_text(json.dumps(line, ensure_ascii=False) + "\n", encoding="utf-8")
    errs = parse_session_for_errors(p)
    assert any(e.get("stopReason") == "error" for e in errs if "error" not in e)


def test_timeline_parse_session_lines_uses_fortify_parser():
    """_parse_session_lines 经 parse_session_jsonl_line（session + message 分支）。"""
    from data import timeline_reader

    lines = [
        json.dumps({"type": "session", "timestamp": 1000}),
        json.dumps(
            {
                "type": "message",
                "timestamp": 1001,
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "hi"}],
                },
            }
        ),
    ]
    steps, started_at, _status = timeline_reader._parse_session_lines(lines, None, None)
    assert started_at == 1000
    assert len(steps) >= 1
    assert any(s.type == timeline_reader.StepType.USER.value for s in steps)


def test_status_cache_double_check_mtime_invalidation(monkeypatch, tmp_path):
    """REQ_002-SPEC-06：mtime 变化导致缓存 miss。"""
    import time

    import data.config_reader as config_reader
    from core.config_fortify import refresh_fortify_config_cache
    from status.status_cache import StatusCache

    monkeypatch.setenv("OPENCLAW_CACHE_DOUBLE_CHECK", "true")
    refresh_fortify_config_cache()
    monkeypatch.setattr(config_reader, "get_openclaw_root", lambda: tmp_path)

    aid = "agent1"
    sess = tmp_path / "agents" / aid / "sessions"
    sess.mkdir(parents=True)
    (sess / "sessions.json").write_text("{}", encoding="utf-8")
    (tmp_path / "subagents").mkdir(parents=True)
    (tmp_path / "subagents" / "runs.json").write_text("{}", encoding="utf-8")

    c = StatusCache(ttl_ms=600_000, max_size=10, max_memory_mb=50)
    c.set(aid, {"status": "idle"})
    assert c.get(aid) is not None
    time.sleep(0.02)
    (sess / "sessions.json").write_text('{"k": 1}', encoding="utf-8")
    assert c.get(aid) is None
    assert c.get_stats()["stats"]["fp_invalidations"] >= 1


def test_status_cache_double_check_disabled_skips_mtime(monkeypatch, tmp_path):
    import data.config_reader as config_reader
    from core.config_fortify import refresh_fortify_config_cache
    from status.status_cache import StatusCache

    monkeypatch.setenv("OPENCLAW_CACHE_DOUBLE_CHECK", "false")
    refresh_fortify_config_cache()
    monkeypatch.setattr(config_reader, "get_openclaw_root", lambda: tmp_path)

    aid = "a2"
    sess = tmp_path / "agents" / aid / "sessions"
    sess.mkdir(parents=True)
    (sess / "sessions.json").write_text("{}", encoding="utf-8")
    (tmp_path / "subagents").mkdir(parents=True)
    (tmp_path / "subagents" / "runs.json").write_text("{}", encoding="utf-8")

    c = StatusCache(ttl_ms=600_000, max_size=10, max_memory_mb=50)
    c.set(aid, {"status": "idle"})
    (sess / "sessions.json").write_text('{"k": 2}', encoding="utf-8")
    got = c.get(aid)
    assert got is not None and got.get("status") == "idle"
    assert c.get_stats()["stats"]["fp_invalidations"] == 0


def test_status_cache_memory_eviction_boundary():
    """REQ_002-AC-004：估算内存超上限时 LRU 逐出。"""
    from status.status_cache import StatusCache

    c = StatusCache(ttl_ms=600_000, max_size=200, max_memory_mb=1)
    pad = "x" * 80_000
    for i in range(30):
        c.set(f"agent_{i}", {"status": "idle", "pad": pad})
    st = c.get_stats()
    assert st["stats"]["evictions"] >= 1
    assert st["memory_usage_mb"] <= 1.15


def test_watcher_try_resume_watchdog_success(monkeypatch, tmp_path):
    """REQ_001-AC-004：轮询模式下恢复 watchdog 成功路径（自动化）。"""
    from core.config_fortify import refresh_fortify_config_cache

    monkeypatch.setenv("OPENCLAW_AGENT_DASHBOARD_DATA", str(tmp_path))
    refresh_fortify_config_cache()

    import watchers.file_watcher as fw

    class FakeObs:
        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def join(self, timeout: float = 0) -> None:
            pass

        def is_alive(self) -> bool:
            return True

    monkeypatch.setattr(fw, "_build_observer", lambda: FakeObs())
    monkeypatch.setattr(fw, "_start_monitor_thread", lambda loop: None)
    monkeypatch.setattr(fw, "_on_file_changed", lambda p=None: None)

    fw._monitor_stop.clear()
    fw._resume_success_count = 0
    fw._resume_failure_count = 0
    fw._watcher_mode = "polling"
    fw._observer = None
    fw._poll_timer = None

    try:
        fw._try_resume_watchdog(None)
        assert fw._watcher_mode == "watchdog"
        assert fw._resume_success_count == 1
        assert fw._resume_failure_count == 0
    finally:
        fw.stop_file_watcher()


def test_watcher_try_resume_watchdog_failure_increments_counter(monkeypatch, tmp_path):
    from core.config_fortify import refresh_fortify_config_cache

    monkeypatch.setenv("OPENCLAW_AGENT_DASHBOARD_DATA", str(tmp_path))
    refresh_fortify_config_cache()

    import watchers.file_watcher as fw

    def boom():
        raise RuntimeError("no observer")

    monkeypatch.setattr(fw, "_build_observer", boom)

    fw._monitor_stop.clear()
    fw._resume_failure_count = 0
    fw._resume_success_count = 0
    fw._watcher_mode = "polling"
    fw._observer = None

    fw._try_resume_watchdog(None)
    assert fw._watcher_mode == "polling"
    assert fw._resume_failure_count == 1
    assert fw._resume_success_count == 0


def test_watcher_health_error_count_tracks_record_error():
    """REQ_001-AC-005：health.error_count 与 fortify record_error（watcher 相关 scope）对齐。"""
    from core.error_handler import record_error

    import watchers.file_watcher as fw

    base = fw.get_watcher_health()["error_count"]
    record_error("io-error", "watcher test", "file_watcher")
    assert fw.get_watcher_health()["error_count"] == base + 1


def test_watcher_persists_state_json(monkeypatch, tmp_path):
    """REQ_001-SPEC-05：磁盘轻量快照。"""
    from core.config_fortify import refresh_fortify_config_cache

    monkeypatch.setenv("OPENCLAW_AGENT_DASHBOARD_DATA", str(tmp_path))
    refresh_fortify_config_cache()

    import watchers.file_watcher as fw

    fw._set_mode("polling")
    p = tmp_path / "watcher_state.json"
    assert p.is_file()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data.get("mode") == "polling"


def test_classify_exception_permission_and_decode():
    from core.error_handler import classify_exception

    assert classify_exception(PermissionError("denied")) == "permission-error"
    assert classify_exception(FileNotFoundError("x")) == "io-error"
    assert classify_exception(UnicodeDecodeError("utf-8", b"", 0, 1, "x")) == "parsing-error"


def test_error_handler_exponential_backoff(monkeypatch):
    from core.error_handler import ErrorHandler

    delays = []
    monkeypatch.setattr("core.error_handler.time.sleep", lambda d: delays.append(d))
    h = ErrorHandler(max_retry=2, base_delay=1.0, enable_fallback=False)
    n = {"v": 0}

    def fn():
        n["v"] += 1
        if n["v"] < 3:
            raise OSError("fail")
        return "ok"

    assert h.run_with_retry(fn, operation="t", error_type="io-error") == "ok"
    assert delays == [1.0, 2.0]


def test_framework_error_stats_totals_consistent():
    from core.error_handler import get_framework_error_stats, record_error

    record_error("network", "a", "scope:stats_a")
    record_error("timeout", "b", "scope:stats_b")
    s = get_framework_error_stats()
    assert s["totals_consistent"] is True
    assert s["sum_by_type"] == s["total_count"]
    assert isinstance(s["by_scope_top"], list)


def test_record_error_includes_exc_metadata():
    from core.error_handler import get_framework_error_stats, record_error

    record_error("unknown", "x", "meta:test", exc=ValueError("bad"))
    le = get_framework_error_stats()["last_error"]
    assert le.get("exc_type") == "ValueError"
    assert le.get("exc_module") == "builtins"


def test_CA004_app_bootstrap(monkeypatch):
    """CA-004：默认配置下 FastAPI 应用可挂载、文档与版本接口可访问。"""
    import asyncio
    import httpx
    _stub_file_watcher_for_testclient(monkeypatch)
    from main import app

    async def _run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
            assert (await c.get("/docs")).status_code == 200
            assert (await c.get("/api/version")).status_code == 200

    asyncio.run(_run())


def test_input_safety_rejects_traversal():
    """NFR-S-002：路径型参数拒绝 .. / 斜杠等。"""
    from fastapi import HTTPException

    from api.input_safety import (
        require_safe_agent_id,
        require_safe_run_or_chain_id,
        require_safe_session_file_segment,
        require_safe_session_key,
    )

    with pytest.raises(HTTPException):
        require_safe_agent_id("a/../b")
    with pytest.raises(HTTPException):
        require_safe_agent_id("x/y")
    with pytest.raises(HTTPException):
        require_safe_session_key("k/../z")
    with pytest.raises(HTTPException):
        require_safe_session_file_segment("..\\x.jsonl")
    with pytest.raises(HTTPException):
        require_safe_run_or_chain_id("../run", name="run_id")


def test_error_analysis_classify_accepts_json_body(monkeypatch):
    """error-analysis/classify 使用 JSON body，并限制 message 长度。"""
    import asyncio
    import httpx
    _stub_file_watcher_for_testclient(monkeypatch)
    from main import app

    async def _run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
            r = await c.post("/api/error-analysis/classify", json={"message": "rate limit 429"})
            assert r.status_code == 200
            body = r.json()
            assert "errorType" in body
            r2 = await c.post("/api/error-analysis/classify", json={"message": "x" * 20_000})
            assert r2.status_code == 422

    asyncio.run(_run())


def test_retry_budget_limits_run_with_retry(monkeypatch):
    """RISK-005：60s 窗口内同一 operation 重试次数受 OPENCLAW_RETRY_BUDGET_PER_MINUTE 约束。"""
    from core.config_fortify import refresh_fortify_config_cache
    from core.error_handler import ErrorHandler, get_framework_error_stats

    monkeypatch.setenv("OPENCLAW_RETRY_BUDGET_PER_MINUTE", "2")
    refresh_fortify_config_cache()
    before = get_framework_error_stats().get("retry_budget_blocks", 0)
    h = ErrorHandler(max_retry=5, base_delay=0.01, enable_fallback=False)
    n = {"i": 0}

    def fn():
        n["i"] += 1
        raise OSError("fail")

    with pytest.raises(OSError):
        h.run_with_retry(fn, operation="budget_test_op", error_type="io-error")
    assert n["i"] == 3
    assert get_framework_error_stats().get("retry_budget_blocks", 0) >= before


def test_invalidate_stale_fp_entries_on_mtime_change(monkeypatch, tmp_path):
    """RISK-004：后台双验证剔除与 mtime 变化一致。"""
    import time

    import data.config_reader as cr
    from core.config_fortify import refresh_fortify_config_cache
    from status.status_cache import StatusCache

    monkeypatch.setenv("OPENCLAW_CACHE_DOUBLE_CHECK", "true")
    refresh_fortify_config_cache()
    monkeypatch.setattr(cr, "get_openclaw_root", lambda: tmp_path)
    sess = tmp_path / "agents" / "ag" / "sessions"
    sess.mkdir(parents=True)
    (sess / "sessions.json").write_text("{}", encoding="utf-8")
    (tmp_path / "subagents").mkdir(parents=True)
    (tmp_path / "subagents" / "runs.json").write_text("{}", encoding="utf-8")

    c = StatusCache(ttl_ms=600_000, max_size=10, max_memory_mb=50)
    c.set("ag", {"status": "idle"})
    assert c.get("ag") is not None
    time.sleep(0.03)
    (sess / "sessions.json").write_text('{"k": 1}', encoding="utf-8")
    assert c.invalidate_stale_fp_entries() >= 1
    assert c.get("ag") is None


def test_sanitize_client_error_text_redacts_secrets():
    """NFR-S-001：API 文案脱敏 sk- / Bearer / 路径等。"""
    from core.safe_api_error import sanitize_client_error_text

    s = sanitize_client_error_text("fail sk-abcdefghijklmnopqrstuvwx trailing")
    assert "sk-abcdefghij" not in s
    assert "REDACTED" in s
    s2 = sanitize_client_error_text("Authorization Bearer abcdefghijklmnop")
    assert "REDACTED" in s2


def test_get_framework_error_stats_for_client_redacts_last_error(monkeypatch):
    from core.config_fortify import refresh_fortify_config_cache
    from core.error_handler import get_framework_error_stats_for_client, record_error

    monkeypatch.setenv("OPENCLAW_API_ERROR_SANITIZE", "true")
    refresh_fortify_config_cache()
    record_error("unknown", "x sk-abcdefghijklmnopqrstuvwx", "scope:test_redact_client")
    out = get_framework_error_stats_for_client()
    le = out.get("last_error") or {}
    detail = str(le.get("detail", ""))
    assert "sk-abc" not in detail


def test_risk003_malformed_jsonl_lines_handled():
    """RISK-003：畸形行不抛未捕获异常。"""
    from utils.data_repair import parse_session_jsonl_line

    samples = [
        "",
        "{",
        "{not json",
        '{"type":"message"}',
        '{"type":"message","message":null}',
        '{"type":"message","message":{"role":"user","content":[]}}',
    ]
    for raw in samples:
        env, msg = parse_session_jsonl_line(raw, auto_repair=False, json_strict=True)
        assert env is None or isinstance(env, dict)
        assert msg is None or isinstance(msg, dict)
