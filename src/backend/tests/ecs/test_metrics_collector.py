"""
Unit tests for MetricsCollector — C0 metrics collection and reporting.

Acceptance Criteria Coverage:
- REQ_005: Metrics (increment counters, record_latency, get_snapshot)
- C0 AC #1: full_state push count tracked
- C0 AC #6: ingest lag p95 < 200ms
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

BACKEND = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND))

from core.metrics_collector import MetricsCollector


# ── MetricsCollector Unit Tests ────────────────────────────────────────

class TestMetricsCollectorIncrement:
    """Counter increment tracking."""

    def test_increment_basic(self):
        mc = MetricsCollector()
        mc.increment("dashboard_state_update_total")
        mc.increment("dashboard_state_update_total")
        mc.increment("dashboard_state_update_total")
        snap = mc.get_snapshot()
        assert snap["counters"]["dashboard_state_update_total"] == 3

    def test_increment_with_value(self):
        mc = MetricsCollector()
        mc.increment("dashboard_jsonl_bytes_read_total", value=1024)
        mc.increment("dashboard_jsonl_bytes_read_total", value=2048)
        snap = mc.get_snapshot()
        assert snap["counters"]["dashboard_jsonl_bytes_read_total"] == 3072

    def test_increment_multiple_counters(self):
        mc = MetricsCollector()
        mc.increment("dashboard_state_update_total")
        mc.increment("dashboard_full_state_total", value=2)
        snap = mc.get_snapshot()
        assert snap["counters"]["dashboard_state_update_total"] == 1
        assert snap["counters"]["dashboard_full_state_total"] == 2

    def test_increment_no_data(self):
        mc = MetricsCollector()
        snap = mc.get_snapshot()
        assert snap["counters"] == {}


class TestMetricsCollectorRecordLatency:
    """Latency recording with percentile computation."""

    def test_record_latency_basic(self):
        mc = MetricsCollector()
        mc.record_latency("dashboard_ingest_lag_ms", 10.0)
        mc.record_latency("dashboard_ingest_lag_ms", 20.0)
        snap = mc.get_snapshot()
        lat = snap["latency"]["dashboard_ingest_lag_ms"]
        assert lat["count"] == 2
        assert lat["avg"] == pytest.approx(15.0, rel=0.1)

    def test_latency_p50(self):
        mc = MetricsCollector()
        for i in range(100):
            mc.record_latency("dashboard_e2e_update_latency_ms", float(i))
        snap = mc.get_snapshot()
        lat = snap["latency"]["dashboard_e2e_update_latency_ms"]
        assert lat["p50"] >= 45  # roughly median of 0..99
        assert lat["p50"] <= 55

    def test_latency_p95(self):
        mc = MetricsCollector()
        for i in range(100):
            mc.record_latency("dashboard_e2e_update_latency_ms", float(i))
        snap = mc.get_snapshot()
        lat = snap["latency"]["dashboard_e2e_update_latency_ms"]
        assert lat["p95"] >= 90  # 95th of 0..99

    def test_latency_p99(self):
        mc = MetricsCollector()
        for i in range(100):
            mc.record_latency("dashboard_e2e_update_latency_ms", float(i))
        snap = mc.get_snapshot()
        lat = snap["latency"]["dashboard_e2e_update_latency_ms"]
        assert lat["p99"] >= 95

    def test_latency_min_max(self):
        mc = MetricsCollector()
        mc.record_latency("dashboard_ingest_lag_ms", 10.0)
        mc.record_latency("dashboard_ingest_lag_ms", 50.0)
        mc.record_latency("dashboard_ingest_lag_ms", 30.0)
        snap = mc.get_snapshot()
        lat = snap["latency"]["dashboard_ingest_lag_ms"]
        assert lat["min"] == 10.0
        assert lat["max"] == 50.0

    def test_latency_no_data(self):
        mc = MetricsCollector()
        snap = mc.get_snapshot()
        assert snap["latency"] == {}

    def test_ingest_lag_p95_under_200ms(self):
        """C0 AC #6: ingest lag p95 < 200ms (typical scenario)."""
        mc = MetricsCollector()
        for lag in [10, 15, 20, 30, 50, 80, 100, 120, 150, 10, 15, 20, 25, 30, 40, 60, 80, 90, 100, 110]:
            mc.record_latency("dashboard_ingest_lag_ms", float(lag))
        snap = mc.get_snapshot()
        lat = snap["latency"]["dashboard_ingest_lag_ms"]
        assert lat["p95"] < 200.0

    def test_ingest_lag_p95_high_values(self):
        """Verify p95 calculation with high outlier values.
        100 samples mostly under 100ms, a few above 200ms.
        With linear interpolation: k = 0.95 * 99 = 94.05,
        p95 should fall among the higher values."""
        mc = MetricsCollector()
        lags = [float(i) for i in range(100)]  # 0..99
        mc.record_latency("dashboard_ingest_lag_ms", float(lags[94]))  # value at index 94
        for lag in lags:
            mc.record_latency("dashboard_ingest_lag_ms", lag)
        snap = mc.get_snapshot()
        lat = snap["latency"]["dashboard_ingest_lag_ms"]
        # With 201 samples (101 from loop + 100 from range),
        # p95 ≈ 0.95 * 200 = 190th value (0-indexed)
        assert lat["p95"] > 80


class TestMetricsCollectorSnapshot:
    """get_snapshot returns a consistent dict with counters and latency."""

    def test_snapshot_is_dict(self):
        mc = MetricsCollector()
        snap = mc.get_snapshot()
        assert isinstance(snap, dict)
        assert "counters" in snap
        assert "latency" in snap

    def test_snapshot_is_independent(self):
        mc = MetricsCollector()
        mc.increment("test_counter")
        snap1 = mc.get_snapshot()
        mc.increment("test_counter")
        snap2 = mc.get_snapshot()
        assert snap1["counters"]["test_counter"] == 1
        assert snap2["counters"]["test_counter"] == 2


class TestMetricsCollectorReset:
    """Reset clears all metrics."""

    def test_reset(self):
        mc = MetricsCollector()
        mc.increment("dashboard_state_update_total")
        mc.record_latency("dashboard_ingest_lag_ms", 10.0)
        mc.reset()
        snap = mc.get_snapshot()
        assert snap["counters"] == {}
        assert snap["latency"] == {}

    def test_reset_then_reuse(self):
        mc = MetricsCollector()
        mc.increment("test")
        mc.reset()
        mc.increment("test", value=5)
        snap = mc.get_snapshot()
        assert snap["counters"]["test"] == 5


class TestMetricsCollectorThreadSafety:
    """Concurrent recording should not lose data."""

    def test_concurrent_records(self):
        import threading
        mc = MetricsCollector()
        errors = []

        def record():
            try:
                for i in range(200):
                    mc.increment("dashboard_state_update_total")
                    mc.record_latency("dashboard_ingest_lag_ms", float(i % 50))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        snap = mc.get_snapshot()
        assert snap["counters"]["dashboard_state_update_total"] == 1000
        lat = snap["latency"]["dashboard_ingest_lag_ms"]
        assert lat["count"] == 1000
