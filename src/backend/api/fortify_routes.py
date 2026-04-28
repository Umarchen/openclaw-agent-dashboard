"""TECHDEBT_FORTIFY: health, cache stats, data validation, logging endpoints."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

sys.path.append(str(Path(__file__).parent.parent))

from api.input_safety import require_safe_agent_id, require_safe_session_file_segment
from core.error_handler import record_error
from core.safe_api_error import safe_api_error_detail

router = APIRouter()


@router.get("/health/watcher")
async def watcher_health() -> Any:
    from watchers.file_watcher import get_watcher_health

    return get_watcher_health()


@router.get("/cache/stats")
async def cache_stats() -> Any:
    from status.status_cache import get_cache

    c = get_cache()
    s = c.get_stats()
    from datetime import datetime, timezone

    s["last_update"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "cache_size": s["size"],
        "max_size": s["max_size"],
        "memory_usage_mb": s.get("memory_usage_mb"),
        "max_memory_mb": s["max_memory_mb"],
        "hit_rate": s["hit_rate"],
        "ttl_seconds": s["ttl_seconds"],
        "preload_enabled": s["preload_enabled"],
        "cache_double_check": s.get("cache_double_check"),
        "fp_probe_interval_sec": s.get("fp_probe_interval_sec"),
        "last_update": s["last_update"],
        "stats": s["stats"],
        "process_rss_mb": s.get("process_rss_mb"),
    }


@router.get("/data/validate")
async def validate_session_data(
    agent_id: str = Query(..., description="Agent ID"),
    session_file: Optional[str] = Query(
        None,
        description="可选：相对于 agents/{agent_id}/sessions 的 .jsonl 路径（如 foo.jsonl）",
    ),
    auto_repair: bool = Query(True),
    include_details: bool = Query(False),
    max_lines: int = Query(1000, ge=1, le=50_000),
) -> Any:
    from data.session_reader import get_session_validation_report

    if not agent_id.strip():
        raise HTTPException(status_code=400, detail="agent_id required")
    aid = require_safe_agent_id(agent_id.strip())
    rel = session_file.strip() if session_file and session_file.strip() else None
    if rel:
        rel = require_safe_session_file_segment(rel)
    try:
        return get_session_validation_report(
            aid,
            relative_session_file=rel,
            auto_repair=auto_repair,
            include_details=include_details,
            max_lines=max_lines,
        )
    except Exception as e:
        record_error("unknown", str(e), "api:fortify:validate", exc=e)
        raise HTTPException(status_code=500, detail=safe_api_error_detail(e)) from e


@router.get("/logging/config")
async def logging_config() -> Any:
    """
    NFR-S-003: Get logging configuration and status.

    Returns current logging configuration for diagnostics and monitoring.
    """
    try:
        from core.logging_config import get_logging_config_summary
        return {
            "status": "ok",
            "config": get_logging_config_summary(),
        }
    except ImportError:
        # Fallback if logging_config is not available
        return {
            "status": "ok",
            "config": {
                "log_retention_days": 30,
                "log_max_size_mb": 100,
                "log_backup_count": 5,
                "log_file_path": None,
                "log_compression": True,
            },
            "note": "Enhanced logging not configured",
        }
