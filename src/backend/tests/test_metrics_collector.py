"""Unit tests for MetricsCollector."""
from __future__ import annotations

import threading
import time

from core.metrics_collector import MetricsCollector, _percentile, get_metrics, reset_metrics_for_tests


def _make() -> MetricsCollector:
    reset_metrics_for_tests()
    return get_metrics()


class TestMetricsCollectorBasic:
    def test_increment(self):
        m = _make()
        m.increment("a")
        m.increment("a")
        m.increment("b")
        snap = m.get_snapshot()
        assert snap["counters"]["a"] == 2
        assert snap["counters"]["b"] == 1

    def test_record_latency_single(self):
        m = _make()
        m.record_latency("x", 10.0)
        snap = m.get_snapshot()
        lat = snap["latency"]["x"]
        assert lat["count"] == 1
        assert lat["p50"] == 10.0
        assert lat["p95"] == 10.0
        assert lat["avg"] == 10.0

    def test_record_latency_percentiles(self):
        m = _make()
        for i in range(1, 101):
            m.record_latency("y", float(i))
        snap = m.get_snapshot()
        lat = snap["latency"]["y"]
        assert lat["count"] == 100
        assert lat["min"] == 1.0
        assert lat["max"] == 100.0
        assert lat["p50"] == 50.5
        assert lat["p95"] == 95.55
        assert lat["p99"] == 99.55
        assert abs(lat["avg"] - 50.5) < 0.01

    def test_latency_max_samples(self):
        m = _make()
        max_samples = m._MAX_SAMPLES
        for i in range(max_samples + 500):
            m.record_latency("z", float(i))
        snap = m.get_snapshot()
        lat = snap["latency"]["z"]
        assert lat["count"] == max_samples
        # oldest samples should be evicted
        assert lat["min"] == 500.0

    def test_reset(self):
        m = _make()
        m.increment("a")
        m.record_latency("x", 5.0)
        m.reset()
        snap = m.get_snapshot()
        assert snap["counters"] == {}
        assert snap["latency"] == {}

    def test_empty_snapshot(self):
        m = _make()
        snap = m.get_snapshot()
        assert snap["counters"] == {}
        assert snap["latency"] == {}


class TestPercentileHelper:
    def test_single_value(self):
        assert _percentile([42.0], 50) == 42.0

    def test_two_values(self):
        assert _percentile([10.0, 20.0], 50) == 15.0

    def test_p0_and_p100(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(vals, 0) == 1.0
        assert _percentile(vals, 100) == 5.0

    def test_empty(self):
        assert _percentile([], 50) == 0.0


class TestThreadSafety:
    def test_concurrent_increments(self):
        m = _make()
        threads = []
        for _ in range(10):
            t = threading.Thread(target=lambda: [m.increment("race") for _ in range(1000)])
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert m.get_snapshot()["counters"]["race"] == 10000

    def test_concurrent_latency(self):
        m = _make()
        barrier = threading.Barrier(4)

        def writer():
            barrier.wait()
            for i in range(250):
                m.record_latency("concurrent", float(i))

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        lat = m.get_snapshot()["latency"]["concurrent"]
        assert lat["count"] == 1000
        assert lat["min"] == 0.0
        assert lat["max"] == 249.0


class TestWellKnownNames:
    def test_constants(self):
        assert isinstance(MetricsCollector.EVT_PUBLISHED, str)
        assert isinstance(MetricsCollector.EVT_PROCESSED, str)
        assert isinstance(MetricsCollector.INGEST_LATENCY, str)
        assert isinstance(MetricsCollector.STATE_UPDATE, str)
