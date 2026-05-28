"""
PerformanceIngestor — C2: periodic slow channel that publishes
PerformanceSnapshotEvent every N seconds (default 30s).

Independent of file changes — runs on a fixed interval timer.
Does NOT subscribe to file change events.

REQ_ECS_010 AC-010-4: pushes every 30s, not following file change frequency.
Config: ecs_perf_snapshot_interval_sec (ECS_PERF_SNAPSHOT_INTERVAL), default 30.0.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from core.error_handler import record_error
from core.event_bus import get_event_bus, TOPIC_PERFORMANCE_SNAPSHOT
from core.event_types import PerformanceSnapshotEvent

_LOG = logging.getLogger(__name__)


class PerformanceIngestor:
    """C2: Periodic performance snapshot publisher.

    Runs as an asyncio background task with a configurable interval.
    """

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the periodic snapshot loop."""
        if self._running:
            return

        from core.config_fortify import get_fortify_config
        cfg = get_fortify_config()

        self._running = True
        self._task = asyncio.create_task(self._snapshot_loop(cfg.ecs_perf_snapshot_interval_sec))
        _LOG.info(
            "PerformanceIngestor started with interval=%.1fs",
            cfg.ecs_perf_snapshot_interval_sec,
        )

    async def stop(self) -> None:
        """Stop the periodic snapshot loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        _LOG.info("PerformanceIngestor stopped")

    async def _snapshot_loop(self, interval_sec: float) -> None:
        """Main loop: sleep then publish snapshot."""
        while self._running:
            try:
                await asyncio.sleep(interval_sec)
                if not self._running:
                    break
                await self._publish_snapshot()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOG.error("PerformanceIngestor snapshot error: %s", e, exc_info=True)
                record_error("unknown", str(e), "performance_ingestor:snapshot", exc=e)

    async def _publish_snapshot(self) -> None:
        """Fetch performance data and publish PerformanceSnapshotEvent."""
        try:
            from api.performance import get_real_stats

            # Use 20-minute window by default for the snapshot
            stats = await get_real_stats(range_minutes=20, range_hours=1, granularity="minute")

            # Structure the payload
            agents: Dict[str, Any] = {}
            global_stats: Dict[str, Any] = {}

            current = stats.get("current", {})
            history = stats.get("history", {})
            statistics = stats.get("statistics", {})

            global_stats = {
                "currentTpm": current.get("tpm", 0),
                "currentRpm": current.get("rpm", 0),
                "windowTotal": current.get("windowTotal", {}),
                "avgTpm": statistics.get("avgTpm", 0),
                "peakTpm": statistics.get("peakTpm", 0),
                "peakTime": statistics.get("peakTime", ""),
                "history": {
                    "tpm": history.get("tpm", []),
                    "rpm": history.get("rpm", []),
                    "timestamps": history.get("timestamps", []),
                },
            }

            event = PerformanceSnapshotEvent(
                agents=agents,
                global_stats=global_stats,
            )

            bus = get_event_bus()
            bus.publish(TOPIC_PERFORMANCE_SNAPSHOT, event)

            _LOG.debug("PerformanceSnapshotEvent published (tpm=%d, rpm=%d)",
                       current.get("tpm", 0), current.get("rpm", 0))

        except Exception as e:
            _LOG.error("PerformanceIngestor publish error: %s", e, exc_info=True)
            record_error("unknown", str(e), "performance_ingestor:publish", exc=e)


# Module-level singleton
_instance: Optional[PerformanceIngestor] = None


def get_performance_ingestor() -> PerformanceIngestor:
    global _instance
    if _instance is None:
        _instance = PerformanceIngestor()
    return _instance
