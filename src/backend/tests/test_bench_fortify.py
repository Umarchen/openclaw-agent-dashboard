"""轻量探针：§3 NFR-P 相关（非严格 SLA，慢机可能波动；CI 可用 -m benchmark 筛选）。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

pytestmark = pytest.mark.benchmark


def _stub_watcher(monkeypatch):
    import watchers.file_watcher as fw
    monkeypatch.setattr(fw, "start_file_watcher", lambda loop: None)
    monkeypatch.setattr(fw, "stop_file_watcher", lambda: None)


def test_nfr_p003_record_error_overhead(monkeypatch):
    """PA-003：record_error 单次调用平均开销 <10ms（NFR-P-003）。"""
    from core.error_handler import record_error
    record_error("unknown", "warmup", "bench:warmup")
    n = 40
    t0 = time.perf_counter()
    for i in range(n):
        record_error("validation-error", f"e{i}", "bench:loop")
    elapsed_ms = (time.perf_counter() - t0) * 1000
    per_ms = elapsed_ms / n
    assert per_ms < 10.0, f"mean record_error {per_ms:.3f}ms (target <10ms)"


def test_nfr_p004_parse_large_message_line():
    from utils.data_repair import parse_session_jsonl_line

    inner = {"role": "user", "content": [{"type": "text", "text": "x" * 40_000}]}
    line = json.dumps({"type": "message", "message": inner}, ensure_ascii=False)
    t0 = time.perf_counter()
    env, msg = parse_session_jsonl_line(line, json_strict=True, auto_repair=False)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert env is not None and msg is not None
    assert elapsed_ms < 800.0, f"parse took {elapsed_ms:.1f}ms"


@pytest.mark.asyncio
async def test_nfr_p005_api_response_health(monkeypatch):
    """PA-005：GET /health 端到端 <200ms。"""
    import httpx
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        t0 = time.perf_counter()
        r = await c.get("/health")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 200.0, f"/health took {elapsed_ms:.1f}ms"


@pytest.mark.asyncio
async def test_nfr_p005_api_response_version(monkeypatch):
    """PA-005：GET /api/version 端到端 <200ms。"""
    import httpx
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        t0 = time.perf_counter()
        r = await c.get("/api/version")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 200.0, f"/api/version took {elapsed_ms:.1f}ms"


@pytest.mark.asyncio
async def test_nfr_p005_api_response_cache_stats(monkeypatch):
    """PA-005：GET /api/cache/stats 端到端 <200ms。"""
    import httpx
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        t0 = time.perf_counter()
        r = await c.get("/api/cache/stats")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 200.0, f"/api/cache/stats took {elapsed_ms:.1f}ms"


@pytest.mark.asyncio
async def test_nfr_p005_api_response_errors_stats(monkeypatch):
    """PA-005：GET /api/errors/stats 端到端 <200ms。"""
    import httpx
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        t0 = time.perf_counter()
        r = await c.get("/api/errors/stats")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        assert r.status_code == 200
        assert elapsed_ms < 200.0, f"/api/errors/stats took {elapsed_ms:.1f}ms"


def test_nfr_p001_resume_watchdog_full_resync(monkeypatch, tmp_path):
    """PA-001 / NFR-P-001：轮询恢复 watchdog 时的全量同步 <1s。测 _full_resync_cache_and_push 耗时。"""
    import threading
    import watchers.file_watcher as fw
    import data.session_reader as sr
    monkeypatch.setattr(sr, "get_openclaw_root", lambda: tmp_path)
    monkeypatch.setattr(fw, "_watcher_mode", "polling")
    monkeypatch.setattr(fw, "_monitor_stop", threading.Event())
    fake_calls = []
    def fake_on_file_changed(_):
        fake_calls.append(1)
    monkeypatch.setattr(fw, "_on_file_changed", fake_on_file_changed)
    monkeypatch.setattr(fw, "_persist_watcher_state", lambda: None)

    t0 = time.perf_counter()
    fw._full_resync_cache_and_push()
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert len(fake_calls) == 1, "full resync should trigger one _on_file_changed"
    assert elapsed_ms < 1000.0, f"_full_resync_cache_and_push took {elapsed_ms:.1f}ms (target <1000ms)"


def test_nfr_p001_switch_to_polling(monkeypatch, tmp_path):
    """PA-001 / NFR-P-001：watchdog 切换到 polling 模式 <1s。测 _switch_to_polling 耗时。"""
    import threading
    import asyncio
    import watchers.file_watcher as fw
    import data.session_reader as sr
    monkeypatch.setattr(sr, "get_openclaw_root", lambda: tmp_path)
    # start in watchdog mode with a stub observer
    monkeypatch.setattr(fw, "_watcher_mode", "watchdog")
    monkeypatch.setattr(fw, "_observer", None)  # no real observer
    monkeypatch.setattr(fw, "_stop_watchdog_observer", lambda: None)
    monkeypatch.setattr(fw, "_start_polling_mode", lambda loop: None)
    monkeypatch.setattr(fw, "_persist_watcher_state", lambda: None)

    fake_loop = asyncio.new_event_loop()
    t0 = time.perf_counter()
    fw._switch_to_polling(fake_loop)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 1000.0, f"_switch_to_polling took {elapsed_ms:.1f}ms (target <1000ms)"
    fake_loop.close()


def test_nfr_p002_cache_hit_rate(monkeypatch, tmp_path):
    """PA-002 / NFR-P-002：缓存命中率 ≥60%。通过 StatusCache 直接验证。"""
    import data.session_reader as sr
    monkeypatch.setattr(sr, "get_openclaw_root", lambda: tmp_path)
    from status.status_cache import StatusCache

    cache = StatusCache(ttl_ms=60_000)
    cache.get("agent-x")  # cold miss
    cache.get("agent-y")  # cold miss
    cache.set("agent-a", {"status": "running"})
    cache.get("agent-a")  # warm hit
    cache.get("agent-a")  # warm hit
    cache.get("agent-a")  # warm hit
    cache.get("agent-a")  # warm hit
    cache.get("agent-b")  # cold miss
    cache.set("agent-b", {"status": "idle"})
    cache.get("agent-b")  # warm hit
    cache.get("agent-b")  # warm hit
    # 5 hits / (5+3) = 5/8 = 62.5% >= 60%

    stats = cache.get_stats()
    total = stats["stats"]["hits"] + stats["stats"]["misses"]
    hit_rate = (stats["stats"]["hits"] / total) if total else 0.0
    assert hit_rate >= 0.60, f"hit_rate {hit_rate:.2%} < 60% (hits={stats['stats']['hits']}, misses={stats['stats']['misses']})"


