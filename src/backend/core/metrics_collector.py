"""
MetricsCollector — simple in-memory metrics for C0 observability.

Tracks counters and latency histograms. Thread-safe. No persistence in C0.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Any, Dict, List


class MetricsCollector:
    """In-memory metrics collector (thread-safe).

    Supports:
    - ``increment(name)`` — monotonically increasing counter.
    - ``record_latency(name, ms)`` — append a latency sample; keeps last
      ``_MAX_SAMPLES`` per metric and computes p50/p95/p99 on demand.
    - ``get_snapshot()`` — returns a plain ``dict`` with all counters and
      latency percentiles.
    """

    _MAX_SAMPLES = 1000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {}
        self._latency: Dict[str, deque] = {}

    # ── public API ──────────────────────────────────────────────

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + value

    def record_latency(self, name: str, ms: float) -> None:
        with self._lock:
            bucket = self._latency.setdefault(name, deque(maxlen=self._MAX_SAMPLES))
            bucket.append(ms)

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            snap: Dict[str, Any] = {"counters": dict(self._counters)}
            lat: Dict[str, Any] = {}
            for name, samples in self._latency.items():
                vals: List[float] = list(samples)
                entry: Dict[str, Any] = {"count": len(vals)}
                if vals:
                    vals_sorted = sorted(vals)
                    entry["p50"] = _percentile(vals_sorted, 50)
                    entry["p95"] = _percentile(vals_sorted, 95)
                    entry["p99"] = _percentile(vals_sorted, 99)
                    entry["avg"] = sum(vals) / len(vals)
                    entry["max"] = vals_sorted[-1]
                    entry["min"] = vals_sorted[0]
                lat[name] = entry
            snap["latency"] = lat
            return snap

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._latency.clear()

    # ── well-known metric names ──────────────────────────────────

    @staticmethod
    def EVT_PUBLISHED = "events_published_total"

    @staticmethod
    def EVT_PROCESSED = "events_processed_total"

    @staticmethod
    def INGEST_LATENCY = "ingest_latency_ms"

    @staticmethod
    def STATE_UPDATE = "state_update_count"


# ── helpers ─────────────────────────────────────────────────────

def _percentile(sorted_vals: List[float], p: float) -> float:
    """Return the *p*-th percentile (0-100) using linear interpolation."""
    if not sorted_vals:
        return 0.0
    n = len(sorted_vals)
    k = (p / 100.0) * (n - 1)
    lo = int(math.floor(k))
    hi = min(lo + 1, n - 1)
    frac = k - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


# ── module-level singleton ─────────────────────────────────────

_collector: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def reset_metrics_for_tests() -> None:
    global _collector
    if _collector is not None:
        _collector.reset()
    _collector = None
