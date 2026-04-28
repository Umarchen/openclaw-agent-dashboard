"""可选后台线程：周期性对 StatusCache 做 mtime 双验证剔除（RISK-004）。"""
from __future__ import annotations

import logging
import threading
from typing import Optional

_LOG = logging.getLogger("openclaw.fortify.cache_probe")


def start_cache_fp_probe_background() -> Optional[threading.Event]:
    """
    若 OPENCLAW_CACHE_FP_PROBE_INTERVAL > 0，启动守护线程并返回用于停止的 Event；
    否则返回 None。
    """
    from core.config_fortify import get_fortify_config

    interval = get_fortify_config().cache_fp_probe_interval_sec
    if interval <= 0:
        return None

    stop = threading.Event()

    def loop() -> None:
        from status.status_cache import get_cache

        while not stop.is_set():
            if stop.wait(timeout=interval):
                break
            try:
                n = get_cache().invalidate_stale_fp_entries()
                if n:
                    _LOG.info("cache_fp_probe removed %s stale cache entries", n)
            except Exception as e:
                from core.error_handler import record_error

                record_error("unknown", str(e), "cache_fp_probe", exc=e)

    threading.Thread(target=loop, daemon=True, name="openclaw_cache_fp_probe").start()
    return stop
