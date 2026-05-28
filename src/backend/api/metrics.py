"""
ECS Metrics API — Prometheus-style metrics endpoint for C0 observability.

Exposes /api/metrics returning MetricsCollector snapshot.
"""
from __future__ import annotations

from fastapi import APIRouter
from typing import Dict, Any

router = APIRouter()


@router.get("/metrics")
async def get_metrics():
    """Return C0 runtime metrics (JSON format).

    Prometheus text format is deferred to C1. C0 uses JSON for simplicity.
    """
    try:
        from core.metrics_collector import get_metrics
        return get_metrics().get_snapshot()
    except Exception as e:
        return {"error": str(e)}
