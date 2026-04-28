"""
状态缓存 - 缓存 Agent 状态计算结果
通过缓存减少重复的文件读取操作，提升状态计算性能
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore


def _estimate_payload_size(data: Dict[str, Any]) -> int:
    n = 256
    for k, v in data.items():
        if str(k).startswith("_"):
            continue
        n += sys.getsizeof(k) + sys.getsizeof(v)
    return n


def source_mtimes_for_agent_cache(agent_id: str) -> Dict[str, Optional[float]]:
    """
    用于缓存「双验证」：与状态计算强相关的源文件 mtime。
    TTL 通过后若任一 mtime 变化则视为 miss（REQ_002-SPEC-06）。
    """
    from data.config_reader import get_openclaw_root, normalize_openclaw_agent_id

    aid = normalize_openclaw_agent_id(agent_id)
    root = get_openclaw_root()
    out: Dict[str, Optional[float]] = {}
    paths: Dict[str, Path] = {
        "sessions_index": root / "agents" / aid / "sessions" / "sessions.json",
        "subagent_runs": root / "subagents" / "runs.json",
    }
    for key, p in paths.items():
        try:
            out[key] = p.stat().st_mtime if p.is_file() else None
        except OSError:
            out[key] = None
    return out


class StatusCache:
    """Agent 状态缓存（线程安全）"""

    def __init__(self, ttl_ms: int = 1000, max_size: int = 100, max_memory_mb: int = 100):
        self.ttl_ms = ttl_ms
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._fp_invalidations = 0
        self._stale_fallback_reads = 0
        self.preload_enabled = True

    def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._cache.get(agent_id)
            if not entry:
                self._misses += 1
                return None
            now = time.time() * 1000
            if now - entry["_timestamp"] > self.ttl_ms:
                # TTL 逻辑 miss，但保留条目供 IO 降级时 get_stale_fallback（REQ_003-AC-003）
                self._misses += 1
                return None
            from core.config_fortify import get_fortify_config

            if get_fortify_config().cache_double_check:
                fp = entry.get("_fp")
                if fp is not None:
                    current = source_mtimes_for_agent_cache(agent_id)
                    if current != fp:
                        del self._cache[agent_id]
                        self._misses += 1
                        self._fp_invalidations += 1
                        return None
            self._hits += 1
            entry["_last_access"] = now
            return {k: v for k, v in entry.items() if not str(k).startswith("_")}

    def get_stale_fallback(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """忽略 TTL 与 mtime 双验证，返回仍驻留在缓存中的最近一条数据（降级读）。"""
        with self._lock:
            entry = self._cache.get(agent_id)
            if not entry:
                return None
            self._stale_fallback_reads += 1
            now = time.time() * 1000
            entry["_last_access"] = now
            return {k: v for k, v in entry.items() if not str(k).startswith("_")}

    def set(self, agent_id: str, data: Dict[str, Any]) -> None:
        with self._lock:
            if len(self._cache) >= self.max_size and agent_id not in self._cache:
                self._evict_oldest(exclude=agent_id)

            now = time.time() * 1000
            est = _estimate_payload_size(data)
            from core.config_fortify import get_fortify_config

            fp: Optional[Dict[str, Optional[float]]] = None
            if get_fortify_config().cache_double_check:
                fp = source_mtimes_for_agent_cache(agent_id)
            self._cache[agent_id] = {
                **data,
                "_timestamp": now,
                "_last_access": now,
                "_est_bytes": est,
                **({"_fp": fp} if fp is not None else {}),
            }
            self._enforce_memory(agent_id)

    def _evict_oldest(self, exclude: Optional[str] = None) -> None:
        keys = [k for k in self._cache if k != exclude]
        if not keys:
            return
        oldest_key = min(
            keys,
            key=lambda k: self._cache[k].get("_last_access", self._cache[k].get("_timestamp", 0)),
        )
        del self._cache[oldest_key]
        self._evictions += 1

    def _total_estimated_bytes(self) -> int:
        return int(sum(self._cache[k].get("_est_bytes", 0) for k in self._cache))

    def _enforce_memory(self, protect_key: Optional[str] = None) -> None:
        while self._total_estimated_bytes() > self.max_memory_bytes and len(self._cache) > 1:
            self._evict_oldest(exclude=protect_key)
            if protect_key and len(self._cache) == 1:
                break

    def invalidate(self, agent_id: Optional[str] = None) -> None:
        with self._lock:
            if agent_id:
                self._cache.pop(agent_id, None)
            else:
                self._cache.clear()

    def invalidate_stale_fp_entries(self) -> int:
        """
        后台探针：对仍在 TTL 内的条目比对 mtime 指纹，不一致则剔除（RISK-004 / NFR-R-004）。
        与 get() 内双验证逻辑一致，适用于长时间无请求时的最终一致补强。
        """
        from core.config_fortify import get_fortify_config

        if not get_fortify_config().cache_double_check:
            return 0
        invalidated = 0
        with self._lock:
            agent_ids = list(self._cache.keys())
        now_ms = time.time() * 1000
        for agent_id in agent_ids:
            with self._lock:
                entry = self._cache.get(agent_id)
                if not entry:
                    continue
                if now_ms - entry["_timestamp"] > self.ttl_ms:
                    continue
                fp = entry.get("_fp")
                if fp is None:
                    continue
            current = source_mtimes_for_agent_cache(agent_id)
            if current == fp:
                continue
            with self._lock:
                entry2 = self._cache.get(agent_id)
                if entry2 and entry2.get("_fp") == fp:
                    del self._cache[agent_id]
                    self._fp_invalidations += 1
                    invalidated += 1
        return invalidated

    def get_stats(self) -> Dict[str, Any]:
        from core.config_fortify import get_fortify_config

        cfg = get_fortify_config()
        dbl = cfg.cache_double_check
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total) if total else 0.0
            rss_mb = None
            if psutil:
                try:
                    rss_mb = round(psutil.Process().memory_info().rss / (1024 * 1024), 2)
                except Exception:
                    pass
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "memory_usage_mb": round(self._total_estimated_bytes() / (1024 * 1024), 3),
                "memory_estimate_mb": round(self._total_estimated_bytes() / (1024 * 1024), 3),
                "max_memory_mb": round(self.max_memory_bytes / (1024 * 1024), 2),
                "process_rss_mb": rss_mb,
                "hit_rate": round(hit_rate, 4),
                "ttl_seconds": self.ttl_ms / 1000.0,
                "preload_enabled": self.preload_enabled,
                "cache_double_check": dbl,
                "fp_probe_interval_sec": cfg.cache_fp_probe_interval_sec,
                "stats": {
                    "hits": self._hits,
                    "misses": self._misses,
                    "evictions": self._evictions,
                    "fp_invalidations": self._fp_invalidations,
                    "stale_fallback_reads": self._stale_fallback_reads,
                },
            }


_cache_instance: Optional[StatusCache] = None


def get_cache() -> StatusCache:
    global _cache_instance
    if _cache_instance is None:
        from core.config_fortify import get_fortify_config

        c = get_fortify_config()
        _cache_instance = StatusCache(
            ttl_ms=c.cache_ttl_seconds * 1000,
            max_size=c.cache_max_entries,
            max_memory_mb=c.cache_max_memory_mb,
        )
        _cache_instance.preload_enabled = c.cache_preload
    return _cache_instance


def reset_cache_for_tests() -> None:
    global _cache_instance
    _cache_instance = None
