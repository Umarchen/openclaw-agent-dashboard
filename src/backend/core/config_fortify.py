"""
TECHDEBT_FORTIFY: centralized environment configuration.

OPENCLAW_CACHE_MAX_SIZE = max cache memory in MB (PRD).
OPENCLAW_CACHE_MAX_ENTRIES = max number of cache entries (distinct from memory cap).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _env_int(key: str, default: int, min_v: int | None = None, max_v: int | None = None) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        v = default
    else:
        try:
            v = int(raw)
        except ValueError:
            v = default
    if min_v is not None:
        v = max(min_v, v)
    if max_v is not None:
        v = min(max_v, v)
    return v


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _env_str(key: str, default: str) -> str:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return raw


@dataclass(frozen=True)
class FortifyConfig:
    cache_ttl_seconds: int
    cache_max_entries: int
    cache_max_memory_mb: int
    cache_preload: bool
    cache_double_check: bool
    cache_fp_probe_interval_sec: float

    max_retry: int
    retry_base_delay: float
    retry_budget_per_minute: int
    enable_fallback: bool
    fallback_cache_on_io: bool
    error_log_level: str
    sanitize_api_errors: bool

    json_strict: bool
    auto_repair_json: bool
    auto_repair_write_back: bool
    repair_backup_path: str | None
    max_repair_attempts: int

    watcher_max_retries: int
    watcher_poll_interval_sec: float
    watcher_failure_window_sec: float

    # NFR-S-003: Logging storage security
    log_retention_days: int
    log_max_size_mb: int
    log_backup_count: int
    log_file_path: str | None
    log_compression: bool

    # C0 ECS event-driven architecture
    ecs_debounce_ms: int          # file change debounce (milliseconds)
    ecs_ingest_batch_size: int    # max agents per ingest cycle
    ecs_max_state_store_size: int # max agents in StateStore
    ecs_watchdog_resume_ticks: int # polling ticks before watchdog resume attempt
    ecs_metrics_enabled: bool      # enable metrics collection
    ecs_heartbeat_topic: str       # EventBus topic for heartbeat ticks
    ecs_state_topic: str          # EventBus topic for agent state changes

    # C1 JSONL offset + checkpoint (REQ_ECS_008)
    ecs_checkpoint_dir: str                # checkpoint storage directory
    ecs_checkpoint_flush_interval_sec: float  # checkpoint flush interval (seconds)
    ecs_max_agent_parallel: int             # bounded parallelism limit for status computation
    ecs_full_state_schema_version: int      # WS protocol schema version number


@lru_cache(maxsize=1)
def get_fortify_config() -> FortifyConfig:
    ttl = _env_int("OPENCLAW_CACHE_TTL", 1, min_v=1, max_v=60)
    return FortifyConfig(
        cache_ttl_seconds=ttl,
        cache_max_entries=_env_int("OPENCLAW_CACHE_MAX_ENTRIES", 100, min_v=1, max_v=10_000),
        cache_max_memory_mb=_env_int("OPENCLAW_CACHE_MAX_SIZE", 100, min_v=1, max_v=4096),
        cache_preload=_env_bool("OPENCLAW_CACHE_PRELOAD", True),
        cache_double_check=_env_bool("OPENCLAW_CACHE_DOUBLE_CHECK", True),
        cache_fp_probe_interval_sec=_env_float("OPENCLAW_CACHE_FP_PROBE_INTERVAL", 0.0),
        max_retry=_env_int("OPENCLAW_MAX_RETRY", 3, min_v=0, max_v=20),
        retry_base_delay=_env_float("OPENCLAW_RETRY_BASE_DELAY", 1.0),
        retry_budget_per_minute=_env_int("OPENCLAW_RETRY_BUDGET_PER_MINUTE", 300, min_v=0, max_v=100_000),
        enable_fallback=_env_bool("OPENCLAW_ENABLE_FALLBACK", True),
        fallback_cache_on_io=_env_bool("OPENCLAW_FALLBACK_CACHE_ON_IO", True),
        error_log_level=_env_str("OPENCLAW_ERROR_LOG_LEVEL", "INFO").upper(),
        sanitize_api_errors=_env_bool("OPENCLAW_API_ERROR_SANITIZE", True),
        json_strict=_env_bool("OPENCLAW_JSON_STRICT", True),
        auto_repair_json=_env_bool("OPENCLAW_AUTO_REPAIR_JSON", True),
        auto_repair_write_back=_env_bool("OPENCLAW_AUTO_REPAIR_WB", False),
        repair_backup_path=os.environ.get("OPENCLAW_REPAIR_BACKUP") or None,
        max_repair_attempts=_env_int("OPENCLAW_MAX_REPAIR_ATTEMPTS", 3, min_v=1, max_v=10),
        watcher_max_retries=_env_int("OPENCLAW_WATCHER_MAX_RETRIES", 3, min_v=1, max_v=10),
        watcher_poll_interval_sec=_env_float("OPENCLAW_WATCHER_POLL_INTERVAL", 5.0),
        watcher_failure_window_sec=_env_float("OPENCLAW_WATCHER_FAILURE_WINDOW", 30.0),
        # NFR-S-003: Logging storage security
        log_retention_days=_env_int("OPENCLAW_LOG_RETENTION_DAYS", 30, min_v=1, max_v=365),
        log_max_size_mb=_env_int("OPENCLAW_LOG_MAX_SIZE_MB", 100, min_v=1, max_v=1024),
        log_backup_count=_env_int("OPENCLAW_LOG_BACKUP_COUNT", 5, min_v=1, max_v=50),
        log_file_path=os.environ.get("OPENCLAW_LOG_FILE_PATH") or None,
        log_compression=_env_bool("OPENCLAW_LOG_COMPRESSION", True),
        # C0 ECS event-driven architecture
        ecs_debounce_ms=_env_int("OPENCLAW_ECS_DEBOUNCE_MS", 1500, min_v=100, max_v=10000),
        ecs_ingest_batch_size=_env_int("OPENCLAW_ECS_INGEST_BATCH_SIZE", 50, min_v=1, max_v=1000),
        ecs_max_state_store_size=_env_int("OPENCLAW_ECS_MAX_STATE_STORE_SIZE", 200, min_v=1, max_v=10000),
        ecs_watchdog_resume_ticks=_env_int("OPENCLAW_ECS_WATCHDOG_RESUME_TICKS", 12, min_v=1, max_v=100),
        ecs_metrics_enabled=_env_bool("OPENCLAW_ECS_METRICS_ENABLED", True),
        ecs_heartbeat_topic=_env_str("OPENCLAW_ECS_HEARTBEAT_TOPIC", "heartbeat"),
        ecs_state_topic=_env_str("OPENCLAW_ECS_STATE_TOPIC", "agent_state_changed"),
        # C1 JSONL offset + checkpoint (REQ_ECS_008, REQ_ECS_009, REQ_ECS_012)
        ecs_checkpoint_dir=_env_str("OPENCLAW_ECS_CHECKPOINT_DIR", "~/.openclaw-agent-dashboard/checkpoints/"),
        ecs_checkpoint_flush_interval_sec=_env_float("OPENCLAW_ECS_CHECKPOINT_FLUSH_INTERVAL", 10.0),
        ecs_max_agent_parallel=_env_int("OPENCLAW_ECS_MAX_AGENT_PARALLEL", 8, min_v=1, max_v=32),
        ecs_full_state_schema_version=_env_int("OPENCLAW_ECS_SCHEMA_VERSION", 2, min_v=1, max_v=99),
    )


def refresh_fortify_config_cache() -> FortifyConfig:
    get_fortify_config.cache_clear()
    return get_fortify_config()
