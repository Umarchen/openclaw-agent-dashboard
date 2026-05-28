"""
Regression: main.py lifespan must start when cache_preload is enabled.

The production bug was a function-scoped `import asyncio` shadowing the module
import and causing UnboundLocalError on asyncio.get_running_loop().
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))


def _stub_file_watcher(monkeypatch) -> None:
    import watchers.file_watcher as fw

    monkeypatch.setattr(fw, "start_file_watcher", lambda loop: None)
    monkeypatch.setattr(fw, "stop_file_watcher", lambda: None)


@pytest.mark.asyncio
async def test_lifespan_bootstraps_with_cache_preload(monkeypatch):
    """App starts and serves /health with default cache_preload=True."""
    _stub_file_watcher(monkeypatch)

    from core.config_fortify import get_fortify_config

    cfg = get_fortify_config()
    assert cfg.cache_preload is True

    from main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"

        metrics = await client.get("/api/metrics")
        assert metrics.status_code == 200
        assert "counters" in metrics.json()
