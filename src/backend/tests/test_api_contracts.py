"""CA-001 / CA-002 / CA-003：核心 API 与数据校验响应结构契约（轻量回归）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _stub_watcher(monkeypatch):
    import watchers.file_watcher as fw
    monkeypatch.setattr(fw, "start_file_watcher", lambda loop: None)
    monkeypatch.setattr(fw, "stop_file_watcher", lambda: None)


@pytest.mark.asyncio
async def test_contract_health_root(monkeypatch):
    import httpx
    _stub_watcher(monkeypatch)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/health")
        assert r.status_code == 200
        assert r.json().get("status") == "healthy"


@pytest.mark.asyncio
async def test_contract_api_version_shape(monkeypatch):
    import httpx
    _stub_watcher(monkeypatch)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/version")
        assert r.status_code == 200
        body = r.json()
        assert "version" in body and "name" in body and "description" in body


@pytest.mark.asyncio
async def test_contract_cache_stats_fortify_keys(monkeypatch):
    import httpx
    _stub_watcher(monkeypatch)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/cache/stats")
        assert r.status_code == 200
        j = r.json()
        for k in ("hit_rate", "ttl_seconds", "stats", "cache_double_check", "fp_probe_interval_sec"):
            assert k in j, f"missing {k}"
        assert "hits" in j["stats"]


@pytest.mark.asyncio
async def test_contract_errors_stats_has_framework(monkeypatch):
    import httpx
    _stub_watcher(monkeypatch)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/errors/stats")
        assert r.status_code == 200
        j = r.json()
        assert "framework" in j
        fw = j["framework"]
        assert "total_count" in fw
        assert "retry_budget_blocks" in fw


@pytest.mark.asyncio
async def test_contract_agents_list_is_array(monkeypatch):
    import httpx
    _stub_watcher(monkeypatch)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/agents")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            row = data[0]
            for k in ("id", "status", "name"):
                assert k in row


@pytest.mark.asyncio
async def test_contract_health_watcher_shape(monkeypatch):
    import httpx
    _stub_watcher(monkeypatch)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/health/watcher")
        assert r.status_code == 200
        j = r.json()
        for k in (
            "status",
            "mode",
            "error_count",
            "switch_count",
            "resume_watchdog_success_count",
            "resume_watchdog_failure_count",
            "uptime_seconds",
            "poll_interval_sec",
            "persisted_snapshot",
        ):
            assert k in j, f"missing {k}"


@pytest.mark.asyncio
async def test_contract_api_config_has_main_agent_id(monkeypatch):
    import httpx
    _stub_watcher(monkeypatch)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/config")
        assert r.status_code == 200
        j = r.json()
        assert "mainAgentId" in j
        assert isinstance(j["mainAgentId"], str)
        assert j["mainAgentId"]


@pytest.mark.asyncio
async def test_contract_data_validate_report_shape(monkeypatch, tmp_path):
    """CA-003：GET /api/data/validate 稳定字段（与 session_reader 报告结构对齐）。"""
    import httpx
    import data.session_reader as session_reader
    monkeypatch.setattr(session_reader, "get_openclaw_root", lambda: tmp_path)
    _stub_watcher(monkeypatch)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/data/validate", params={"agent_id": "main"})
        assert r.status_code == 200
        j = r.json()
        for k in (
            "agent_id",
            "validation_passed",
            "sessions_index_path",
            "session_file",
            "session_file_query",
            "file_integrity",
            "read_path_policy",
            "total_lines",
            "valid_messages",
            "repaired_messages",
            "errors",
            "repair_report",
        ):
            assert k in j, f"missing {k}"
        rp = j["repair_report"]
        assert "repaired_count" in rp and "repair_success_rate" in rp and "failed_repairs" in rp
        assert isinstance(j["errors"], list)
        assert isinstance(rp["failed_repairs"], list)
        pol = j["read_path_policy"]
        assert "memory_auto_repair_default" in pol and "disk_write_back_enabled" in pol


# ---------------------------------------------------------------------------
# CA-001 / CA-002：timeline / chains 响应结构契约
# ---------------------------------------------------------------------------

def _stub_root(monkeypatch, tmp_path):
    """隔离 openclaw_root，避免依赖真实数据目录。"""
    _stub_watcher(monkeypatch)
    import data.session_reader as sr
    import api.timeline as tl
    monkeypatch.setattr(sr, "get_openclaw_root", lambda: tmp_path)
    monkeypatch.setattr(tl, "get_agent_config", lambda agent_id: {"id": agent_id, "name": agent_id, "model": "test-model"})


@pytest.mark.asyncio
async def test_contract_timeline_shape(monkeypatch, tmp_path):
    """CA-002：GET /timeline/{agent_id} 稳定字段（agentId / steps / stats / model / agentName）。"""
    import httpx
    _stub_root(monkeypatch, tmp_path)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/timeline/main")
        assert r.status_code == 200
        j = r.json()
        for k in ("agentId", "status", "steps", "stats"):
            assert k in j, f"missing {k}"
        stats = j["stats"]
        for k in ("totalDuration", "totalInputTokens", "totalOutputTokens", "toolCallCount", "stepCount"):
            assert k in stats, f"missing stats.{k}"
        assert isinstance(j["steps"], list)
        assert isinstance(j["agentId"], str)


@pytest.mark.asyncio
async def test_contract_timeline_steps_shape(monkeypatch, tmp_path):
    """CA-002：GET /timeline/{agent_id}/steps 返回 {steps, count}。"""
    import httpx
    _stub_root(monkeypatch, tmp_path)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/timeline/main/steps")
        assert r.status_code == 200
        j = r.json()
        assert "steps" in j
        assert "count" in j
        assert j["count"] == len(j["steps"])
        assert isinstance(j["steps"], list)


@pytest.mark.asyncio
async def test_contract_chains_list_shape(monkeypatch, tmp_path):
    """CA-002：GET /chains 返回 {chains, activeChain}。"""
    import httpx
    _stub_root(monkeypatch, tmp_path)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/chains")
        assert r.status_code == 200
        j = r.json()
        assert "chains" in j
        assert "activeChain" in j
        assert isinstance(j["chains"], list)
        assert j["activeChain"] is None or isinstance(j["activeChain"], dict)


@pytest.mark.asyncio
async def test_contract_chains_summary_shape(monkeypatch, tmp_path):
    """CA-002：GET /chains/summary 返回 {total, running, completed, error, chains}。"""
    import httpx
    _stub_root(monkeypatch, tmp_path)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/chains/summary")
        assert r.status_code == 200
        j = r.json()
        for k in ("total", "running", "completed", "error", "chains"):
            assert k in j, f"missing {k}"
        assert isinstance(j["total"], int)
        assert isinstance(j["chains"], list)


@pytest.mark.asyncio
async def test_contract_chains_active_shape(monkeypatch, tmp_path):
    """CA-002：GET /chains/active 返回 {activeChain} 或含 message。"""
    import httpx
    _stub_root(monkeypatch, tmp_path)
    from main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/chains/active")
        assert r.status_code == 200
        j = r.json()
        assert "activeChain" in j
        if j["activeChain"] is None:
            assert "message" in j


# ---------------------------------------------------------------------------
# CA-003：数据校验 fixture 驱动测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contract_data_validate_with_fixture(monkeypatch, fake_openclaw_root):
    """CA-003：GET /api/data/validate 用真实 fixture 验证 sessions.json + JSONL 解析。"""
    import httpx
    import data.session_reader as sr
    import api.timeline as tl

    monkeypatch.setattr(sr, "get_openclaw_root", lambda: fake_openclaw_root)
    monkeypatch.setattr(tl, "get_agent_config", lambda agent_id: {"id": agent_id, "name": agent_id, "model": "test-model"})
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/data/validate", params={"agent_id": "main"})
        assert r.status_code == 200, r.text
        j = r.json()
        # sessions_index 被找到
        assert j["sessions_index_path"] is not None
        # JSONL 行被解析（valid_messages = lines with type=message）
        assert j["total_lines"] >= 3
        assert j["valid_messages"] >= 1
        assert "file_integrity" in j


@pytest.mark.asyncio
async def test_contract_data_validate_session_file_param(monkeypatch, fake_openclaw_root):
    """CA-003：GET /api/data/validate 支持 session_file query 参数（无 agent_id 时走默认）。"""
    import httpx
    import data.session_reader as sr
    import api.timeline as tl

    monkeypatch.setattr(sr, "get_openclaw_root", lambda: fake_openclaw_root)
    monkeypatch.setattr(tl, "get_agent_config", lambda agent_id: {"id": agent_id, "name": agent_id, "model": "test-model"})
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/data/validate", params={"agent_id": "main", "max_lines": 5})
        assert r.status_code == 200
        j = r.json()
        assert "validation_passed" in j
        assert "repair_report" in j


# ---------------------------------------------------------------------------
# CA-002 扩展：agents / cache / errors 更多字段断言
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contract_agents_list_item_extended_fields(monkeypatch):
    """CA-002：GET /api/agents 列表项含 status / name / role。"""
    import httpx
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/agents")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        if data:
            row = data[0]
            for k in ("id", "status", "name", "role"):
                assert k in row, f"missing field: {k}"


@pytest.mark.asyncio
async def test_contract_cache_stats_stats_fields(monkeypatch):
    """CA-002：GET /api/cache/stats.stats 含 hits / misses / fp_invalidations / stale_fallback_reads。"""
    import httpx
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/cache/stats")
        assert r.status_code == 200
        stats = r.json()["stats"]
        for k in ("hits", "misses", "fp_invalidations", "stale_fallback_reads"):
            assert k in stats, f"missing stats.{k}"
            assert isinstance(stats[k], int)


@pytest.mark.asyncio
async def test_contract_errors_stats_by_type_fields(monkeypatch):
    """CA-002：GET /api/errors/stats.framework 含 by_type / by_scope_top / retry_budget_blocks。"""
    import httpx
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/errors/stats")
        assert r.status_code == 200
        fw = r.json()["framework"]
        assert "by_type" in fw
        assert "by_scope_top" in fw
        assert "retry_budget_blocks" in fw
        assert isinstance(fw["by_type"], dict)
        assert isinstance(fw["by_scope_top"], list)


@pytest.mark.asyncio
async def test_contract_watcher_poll_ticks_counter(monkeypatch):
    """CA-002：GET /api/health/watcher 含 persisted_snapshot（内含 poll_ticks_counter）。"""
    import httpx
    _stub_watcher(monkeypatch)
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as c:
        r = await c.get("/api/health/watcher")
        assert r.status_code == 200
        snap = r.json().get("persisted_snapshot")
        if snap:
            assert "poll_ticks_counter" in snap, "persisted_snapshot should contain poll_ticks_counter"
