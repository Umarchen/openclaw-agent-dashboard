"""
Unified error handling: classification, exponential backoff retry, in-process stats, structured logging.

降级策略集中注册见 core.fallback_manager（REQ_003-SPEC-04）；IO 失败读缓存见 status_cache.get_stale_fallback（REQ_003-AC-003）。
"""
from __future__ import annotations

import logging
import threading
import time
import functools
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from core.config_fortify import get_fortify_config

_LOG = logging.getLogger("openclaw.fortify")


def _ensure_fortify_logging() -> None:
    if getattr(_ensure_fortify_logging, "_done", False):
        return
    cfg = get_fortify_config()
    level = getattr(logging, cfg.error_log_level, logging.INFO)
    _LOG.setLevel(level)
    if not _LOG.handlers:
        # Try to use secure file-based logging if configured
        try:
            from core.logging_config import setup_secure_logging, get_log_file_path
            log_path = get_log_file_path()
            if log_path is not None:
                # Secure logging is configured, skip console-only handler
                # setup_secure_logging() already added file handlers
                _ensure_fortify_logging._done = True  # type: ignore[attr-defined]
                return
        except ImportError:
            pass  # Fall back to console handler

        h = logging.StreamHandler()
        h.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)s | fortify | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        _LOG.addHandler(h)
    _ensure_fortify_logging._done = True  # type: ignore[attr-defined]


@dataclass
class ErrorHandlerStats:
    total_count: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_scope: Dict[str, int] = field(default_factory=dict)
    hourly_trend: List[Dict[str, Any]] = field(default_factory=list)
    last_error: Optional[Dict[str, Any]] = None
    last_update_iso: Optional[str] = None


_stats_lock = threading.Lock()
_stats = ErrorHandlerStats()
_retry_totals = defaultdict(int)

_retry_budget_lock = threading.Lock()
_retry_budget_deques: Dict[str, deque] = {}
_retry_budget_blocks = 0

# NFR-R: Reliability metrics
_reliability_lock = threading.Lock()
# Error recovery tracking
_error_recovery_times: deque = deque(maxlen=100)  # last 100 recovery times in seconds
_last_error_timestamp: Optional[float] = None
_last_recovery_timestamp: Optional[float] = None

# Graceful degradation tracking
_fallback_total_attempts = 0
_fallback_success_count = 0

# Watcher availability tracking
_watcher_uptime_start: Optional[float] = None
_watcher_total_uptime_seconds = 0.0
_watcher_total_downtime_seconds = 0.0
_watchdog_last_failure_time: Optional[float] = None


def record_fallback_attempt(success: bool) -> None:
    """Record graceful degradation attempt (NFR-R-005)."""
    global _fallback_total_attempts, _fallback_success_count
    with _reliability_lock:
        _fallback_total_attempts += 1
        if success:
            _fallback_success_count += 1


def record_error_recovery(duration_seconds: float) -> None:
    """Record error recovery time (NFR-R-003)."""
    with _reliability_lock:
        _error_recovery_times.append(duration_seconds)


def record_watcher_failure() -> None:
    """Mark watchdog failure start time."""
    global _watchdog_last_failure_time, _watcher_uptime_start, _watcher_total_uptime_seconds
    now = time.time()
    with _reliability_lock:
        if _watchdog_last_failure_time is None:
            _watchdog_last_failure_time = now
            if _watcher_uptime_start is not None:
                _watcher_total_uptime_seconds += now - _watcher_uptime_start
                _watcher_uptime_start = None


def record_watcher_recovery() -> None:
    """Mark watchdog recovery and record recovery time (NFR-R-003)."""
    global _watchdog_last_failure_time, _watcher_uptime_start, _watcher_total_downtime_seconds
    now = time.time()
    recovery_time = 0.0
    with _reliability_lock:
        if _watchdog_last_failure_time is not None:
            recovery_time = now - _watchdog_last_failure_time
            _watcher_total_downtime_seconds += recovery_time
            _watchdog_last_failure_time = None
        _watcher_uptime_start = now
    # Record outside lock to avoid deadlock (record_error_recovery also uses _reliability_lock)
    if recovery_time > 0:
        _error_recovery_times.append(recovery_time)


def get_reliability_metrics() -> Dict[str, Any]:
    """Get all reliability metrics for NFR-R-002/003/005."""
    import statistics as _statistics

    with _reliability_lock:
        current_time = time.time()
        current_uptime = 0.0
        if _watcher_uptime_start is not None:
            current_uptime = current_time - _watcher_uptime_start

        total_uptime = _watcher_total_uptime_seconds + current_uptime
        total_downtime = _watcher_total_downtime_seconds
        total_time = total_uptime + total_downtime

        # NFR-R-002: Watcher availability/success rate
        availability_rate = 1.0
        if total_time > 0:
            availability_rate = total_uptime / total_time

        # NFR-R-003: Error recovery time
        recovery_times_list = list(_error_recovery_times)
        avg_recovery_time = 0.0
        p95_recovery_time = 0.0
        if recovery_times_list:
            avg_recovery_time = _statistics.mean(recovery_times_list)
            sorted_times = sorted(recovery_times_list)
            p95_idx = int(len(sorted_times) * 0.95)
            p95_recovery_time = sorted_times[min(p95_idx, len(sorted_times) - 1)]

        # NFR-R-005: Graceful degradation rate
        graceful_degradation_rate = 1.0
        if _fallback_total_attempts > 0:
            graceful_degradation_rate = _fallback_success_count / _fallback_total_attempts

        return {
            # NFR-R-002: Watcher availability
            "watcher_uptime_seconds": total_uptime,
            "watcher_downtime_seconds": total_downtime,
            "watcher_availability_rate": round(availability_rate, 4),
            "watcher_uptime_percentage": round(availability_rate * 100, 2),
            # NFR-R-003: Error recovery time
            "avg_error_recovery_seconds": round(avg_recovery_time, 3),
            "p95_error_recovery_seconds": round(p95_recovery_time, 3),
            "error_recovery_count": len(recovery_times_list),
            "last_error_recovery_time": recovery_times_list[-1] if recovery_times_list else None,
            # NFR-R-005: Graceful degradation
            "graceful_degradation_attempts": _fallback_total_attempts,
            "graceful_degradation_successes": _fallback_success_count,
            "graceful_degradation_rate": round(graceful_degradation_rate, 4),
            "graceful_degradation_percentage": round(graceful_degradation_rate * 100, 2),
        }


def reset_reliability_metrics_for_tests() -> None:
    """Reset reliability metrics for testing."""
    global _error_recovery_times, _last_error_timestamp, _last_recovery_timestamp
    global _fallback_total_attempts, _fallback_success_count
    global _watcher_uptime_start, _watcher_total_uptime_seconds, _watcher_total_downtime_seconds
    global _watchdog_last_failure_time
    with _reliability_lock:
        _error_recovery_times.clear()
        _last_error_timestamp = None
        _last_recovery_timestamp = None
        _fallback_total_attempts = 0
        _fallback_success_count = 0
        _watcher_uptime_start = None
        _watcher_total_uptime_seconds = 0.0
        _watcher_total_downtime_seconds = 0.0
        _watchdog_last_failure_time = None


def _consume_retry_budget(operation: str) -> bool:
    """
    滑动窗口（60s）内同一 operation 的退避重试次数上限，缓解重试风暴（RISK-005）。
    OPENCLAW_RETRY_BUDGET_PER_MINUTE=0 表示不限制。
    """
    global _retry_budget_blocks
    cfg = get_fortify_config()
    limit = cfg.retry_budget_per_minute
    if limit <= 0:
        return True
    op = (operation or "default").strip() or "default"
    now = time.monotonic()
    with _retry_budget_lock:
        dq = _retry_budget_deques.setdefault(op, deque())
        while dq and now - dq[0] > 60.0:
            dq.popleft()
        if len(dq) >= limit:
            _retry_budget_blocks += 1
            return False
        dq.append(now)
        return True


def classify_exception(exc: BaseException) -> str:
    """Map exception to PRD-style category."""
    import json as _json

    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, PermissionError):
        return "permission-error"
    if isinstance(exc, FileNotFoundError):
        return "io-error"
    if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return "network"
    if isinstance(exc, (ConnectionError, OSError)):
        msg = str(exc).lower()
        if "network" in msg or "connection" in msg or "broken pipe" in msg:
            return "network"
        return "io-error"
    if isinstance(exc, _json.JSONDecodeError):
        return "parsing-error"
    if isinstance(exc, UnicodeDecodeError):
        return "parsing-error"
    if isinstance(exc, MemoryError):
        return "compute-error"
    if isinstance(exc, RecursionError):
        return "compute-error"
    if isinstance(exc, (KeyError, TypeError, AttributeError)):
        return "validation-error"
    if isinstance(exc, ValueError):
        return "validation-error"
    try:
        import ssl
    except ImportError:
        pass
    else:
        if isinstance(exc, ssl.SSLError):
            return "network"
    return "unknown"


class ErrorHandler:
    """Per-use-case handler; global stats still aggregate via record_error."""

    def __init__(
        self,
        max_retry: Optional[int] = None,
        base_delay: Optional[float] = None,
        enable_fallback: Optional[bool] = None,
    ):
        _ensure_fortify_logging()
        cfg = get_fortify_config()
        self.max_retry = cfg.max_retry if max_retry is None else max_retry
        self.base_delay = cfg.retry_base_delay if base_delay is None else base_delay
        self.enable_fallback = cfg.enable_fallback if enable_fallback is None else enable_fallback

    def log_error(
        self,
        error_type: str,
        error_detail: str,
        affected_scope: str = "",
        exc: Optional[BaseException] = None,
    ) -> None:
        record_error(error_type, error_detail, affected_scope, exc)

    def get_stats(self) -> Dict[str, Any]:
        return get_framework_error_stats()

    def run_with_retry(
        self,
        fn: Callable[[], Any],
        *,
        operation: str = "operation",
        error_type: str = "unknown",
        fallback: Optional[Callable[[], Any]] = None,
        retryable: Optional[Tuple[Type[BaseException], ...]] = None,
    ) -> Any:
        if retryable is None:
            retryable = (OSError, IOError, TimeoutError, ConnectionError)
        attempts = max(1, self.max_retry + 1)
        last_exc: Optional[BaseException] = None
        for attempt in range(attempts):
            try:
                return fn()
            except retryable as e:
                last_exc = e
                if attempt + 1 >= attempts:
                    break
                if not _consume_retry_budget(operation):
                    record_error(
                        "compute-error",
                        f"retry budget exceeded (60s window) op={operation}",
                        f"retry_budget:{operation}",
                    )
                    if self.enable_fallback and fallback is not None:
                        return fallback()
                    if last_exc:
                        raise last_exc
                    raise RuntimeError(operation)
                delay = self.base_delay * (2**attempt)
                _LOG.warning(
                    "retry operation=%s attempt=%s/%s delay=%.2fs err=%s",
                    operation,
                    attempt + 1,
                    attempts,
                    delay,
                    e,
                )
                time.sleep(delay)
        record_error(error_type, str(last_exc) if last_exc else "failed", operation, last_exc)
        if self.enable_fallback and fallback is not None:
            return fallback()
        if last_exc:
            raise last_exc
        raise RuntimeError(operation)


def record_error(
    error_type: str,
    error_detail: str,
    affected_scope: str = "",
    exc: Optional[BaseException] = None,
) -> None:
    _ensure_fortify_logging()
    if exc is not None:
        error_type = classify_exception(exc) if error_type in ("", "unknown") else error_type
    detail = (error_detail or "")[:2000]
    scope = affected_scope or ""
    exc_type_name = type(exc).__name__ if exc is not None else ""
    exc_module = type(exc).__module__ if exc is not None else ""
    _LOG.error(
        "fortify_event error_type=%s scope=%s exc_type=%s exc_module=%s detail=%s",
        error_type,
        scope,
        exc_type_name,
        exc_module,
        detail,
        exc_info=exc is not None,
    )
    now = datetime.now(timezone.utc)
    hour_key = now.strftime("%Y-%m-%d %H:00")
    with _stats_lock:
        _stats.total_count += 1
        _stats.by_type[error_type] = _stats.by_type.get(error_type, 0) + 1
        if scope:
            _stats.by_scope[scope] = _stats.by_scope.get(scope, 0) + 1
        _stats.last_error = {
            "type": error_type,
            "detail": detail,
            "scope": scope,
            "time": now.isoformat(),
            "exc_type": exc_type_name or None,
            "exc_module": exc_module or None,
        }
        _stats.last_update_iso = now.isoformat()
        # rolling hourly bucket (merge into hourly_trend max 24 entries)
        found = False
        for row in _stats.hourly_trend:
            if row.get("hour") == hour_key:
                row["count"] = row.get("count", 0) + 1
                found = True
                break
        if not found:
            _stats.hourly_trend.append({"hour": hour_key, "count": 1})
            if len(_stats.hourly_trend) > 24:
                _stats.hourly_trend = _stats.hourly_trend[-24:]


def record_retry(operation: str) -> None:
    _retry_totals[operation] += 1


def get_framework_error_stats_for_client() -> Dict[str, Any]:
    """供 HTTP 返回：在开启脱敏时处理 last_error。"""
    from core.safe_api_error import redact_framework_stats_for_client

    return redact_framework_stats_for_client(get_framework_error_stats())


def get_framework_error_stats() -> Dict[str, Any]:
    with _stats_lock:
        by_type_out: Dict[str, Any] = {}
        type_labels = {
            "network": ("网络错误", "#f59e0b"),
            "timeout": ("超时错误", "#ef4444"),
            "parsing": ("解析错误", "#8b5cf6"),
            "parsing-error": ("解析错误", "#8b5cf6"),
            "io-error": ("IO 错误", "#64748b"),
            "permission-error": ("权限错误", "#b45309"),
            "compute-error": ("计算错误", "#dc2626"),
            "validation-error": ("校验错误", "#ca8a04"),
            "unknown": ("未知错误", "#6b7280"),
        }
        for t, c in _stats.by_type.items():
            label, color = type_labels.get(t, (t, "#6b7280"))
            by_type_out[t] = {"count": c, "label": label, "color": color}
        by_agent: Dict[str, Any] = {}
        for scope, c in _stats.by_scope.items():
            if scope.startswith("agent_id:"):
                aid = scope.split(":", 1)[-1]
                by_agent[aid] = {"count": c, "agentId": aid}
            else:
                by_agent[scope] = {"count": c, "agentId": scope}
        sum_by_type = sum(t.get("count", 0) if isinstance(t, dict) else 0 for t in by_type_out.values())
        top_scopes = [
            {"scope": k, "count": v}
            for k, v in sorted(_stats.by_scope.items(), key=lambda kv: -kv[1])[:50]
        ]

    # NFR-R reliability metrics
    reliability = get_reliability_metrics()

    return {
        "total_count": _stats.total_count,
        "by_type": by_type_out,
        "by_agent": by_agent,
        "by_scope_top": top_scopes,
        "sum_by_type": sum_by_type,
        "totals_consistent": sum_by_type == _stats.total_count,
        "hourly_trend": list(_stats.hourly_trend),
        "last_update": _stats.last_update_iso,
        "last_error": _stats.last_error,
        "retry_by_operation": dict(_retry_totals),
        "retry_budget_blocks": _retry_budget_blocks,
        # NFR-R Reliability
        "reliability": reliability,
    }


def execute_with_retry(
    max_attempts: int = 3,
    delay_base: float = 1.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            cfg = get_fortify_config()
            attempts = max_attempts if max_attempts is not None else cfg.max_retry + 1
            base = delay_base if delay_base is not None else cfg.retry_base_delay
            last: Optional[BaseException] = None
            for attempt in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last = e
                    record_retry(fn.__name__)
                    if attempt + 1 >= attempts:
                        break
                    if not _consume_retry_budget(fn.__name__):
                        record_error(
                            "compute-error",
                            f"retry budget exceeded (60s window) op={fn.__name__}",
                            f"retry_budget:{fn.__name__}",
                        )
                        if last:
                            raise last
                        raise RuntimeError(fn.__name__)
                    time.sleep(base * (2**attempt))
            if last:
                raise last
            raise RuntimeError(fn.__name__)

        return wrapped

    return deco
