"""
文件变更监听 - 关键文件变更时触发 WebSocket 推送
使用 watchdog 监听；失败时重试并降级为轮询；集成缓存失效
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

_LOG = logging.getLogger("openclaw.fortify.watcher")

from core.config_fortify import get_fortify_config
from core.error_handler import record_error

DEBOUNCE_SECONDS = 0.3


def _extract_agent_id_from_path(filepath: str) -> Optional[str]:
    try:
        path = Path(filepath)
        parts = path.parts
        try:
            agents_idx = parts.index("agents")
        except ValueError:
            return None
        if agents_idx + 2 < len(parts) and parts[agents_idx + 2] == "sessions":
            return parts[agents_idx + 1]
        return None
    except Exception:
        return None


def _get_openclaw_dir() -> Path:
    from data.config_reader import get_openclaw_root

    return get_openclaw_root()


def _get_watch_dirs() -> list[tuple[Path, bool]]:
    dirs: list[tuple[Path, bool]] = []
    openclaw_dir = _get_openclaw_dir()
    subagents = openclaw_dir / "subagents"
    if subagents.exists():
        dirs.append((subagents, False))
    try:
        from data.task_history import get_dashboard_data_dir

        dashboard_data = get_dashboard_data_dir()
        if dashboard_data.exists():
            dirs.append((dashboard_data, False))
    except Exception:
        pass
    try:
        from data.config_reader import get_workspace_paths

        for ws in get_workspace_paths():
            memory = ws / "memory"
            if memory.exists():
                dirs.append((memory, False))
    except Exception:
        memory = openclaw_dir / "workspace-main" / "memory"
        if memory.exists():
            dirs.append((memory, False))
    agents_dir = openclaw_dir / "agents"
    if agents_dir.exists():
        for agent_dir in agents_dir.iterdir():
            if agent_dir.is_dir():
                sessions_dir = agent_dir / "sessions"
                if sessions_dir.exists():
                    dirs.append((sessions_dir, True))
    return dirs


class DebouncedHandler:
    """防抖：短时间多次变更只触发一次回调"""

    def __init__(self, callback: Callable[[Optional[str]], None], debounce_sec: float = DEBOUNCE_SECONDS):
        self.callback = callback
        self.debounce_sec = debounce_sec
        self._last_trigger: float = 0
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._pending_path: Optional[str] = None

    def trigger(self, filepath: Optional[str] = None) -> None:
        with self._lock:
            now = time.monotonic()
            if self._timer:
                self._timer.cancel()
                self._timer = None
            if filepath:
                self._pending_path = filepath

            def do_callback() -> None:
                with self._lock:
                    self._last_trigger = time.monotonic()
                    self._timer = None
                    path = self._pending_path
                    self._pending_path = None
                try:
                    self.callback(path)
                except Exception as e:
                    record_error("unknown", str(e), "file_watcher_debounce")

            if now - self._last_trigger < self.debounce_sec:
                self._timer = threading.Timer(self.debounce_sec - (now - self._last_trigger), do_callback)
                self._timer.daemon = True
                self._timer.start()
            else:
                do_callback()


_observer = None
_handler: Optional[DebouncedHandler] = None
_event_loop = None
_watcher_mode = "stopped"
_poll_timer: Optional[threading.Timer] = None
_monitor_stop = threading.Event()
_monitor_thread: Optional[threading.Thread] = None
_started_at = 0.0
_switch_count = 0
_resume_success_count = 0
_resume_failure_count = 0
_events_processed = 0
_last_error: Optional[str] = None
_last_heartbeat = 0.0
_watchdog_failure_since: Optional[float] = None
_poll_ticks = 0
_health_lock = threading.Lock()
_last_full_sync_iso: Optional[str] = None


def _watcher_state_path() -> Optional[Path]:
    try:
        from data.task_history import get_dashboard_data_dir

        d = get_dashboard_data_dir()
        d.mkdir(parents=True, exist_ok=True)
        return d / "watcher_state.json"
    except Exception:
        return None


def _persist_watcher_state() -> None:
    """持久化轻量快照（跨进程重启可读；不恢复内存计数，仅供健康检查与排障）。"""
    path = _watcher_state_path()
    if path is None:
        return
    watch_dirs: list[str] = []
    try:
        for p, _ in _get_watch_dirs()[:48]:
            try:
                watch_dirs.append(str(p.resolve()))
            except OSError:
                watch_dirs.append(str(p))
    except Exception:
        pass
    with _health_lock:
        payload = {
            "mode": _watcher_mode,
            "switch_count": _switch_count,
            "resume_success_count": _resume_success_count,
            "resume_failure_count": _resume_failure_count,
            "events_processed": _events_processed,
            "poll_ticks_counter": _poll_ticks,
            "last_error": _last_error,
            "last_full_sync": _last_full_sync_iso,
            "watch_dirs": watch_dirs,
            "started_at": datetime.fromtimestamp(_started_at, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
            if _started_at
            else None,
            "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _read_persisted_watcher_state() -> Optional[Dict[str, Any]]:
    path = _watcher_state_path()
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _is_watcher_record_error_scope(scope: str) -> bool:
    if not scope:
        return False
    if scope.startswith("file_watcher"):
        return True
    return scope in ("watchdog_resume", "polling_tick")


def _watcher_framework_error_count() -> int:
    from core.error_handler import get_framework_error_stats

    total = 0
    by_scope = get_framework_error_stats().get("by_agent", {})
    for scope, info in by_scope.items():
        if not isinstance(info, dict):
            continue
        if _is_watcher_record_error_scope(str(scope)):
            total += int(info.get("count", 0))
    return total


def _full_resync_cache_and_push() -> None:
    """轮询恢复 watchdog 或显式需要时：全量缓存失效 + 推送（REQ_001-SPEC-05）。"""
    global _last_full_sync_iso
    try:
        _on_file_changed(None)
        _last_full_sync_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception as e:
        record_error("unknown", str(e), "file_watcher_full_resync", exc=e)
    _persist_watcher_state()


def _set_mode(mode: str) -> None:
    global _watcher_mode
    with _health_lock:
        _watcher_mode = mode
    _persist_watcher_state()


def _touch_activity() -> None:
    global _events_processed, _last_heartbeat
    _events_processed += 1
    _last_heartbeat = time.time()


def _on_file_changed(filepath: Optional[str] = None) -> None:
    global _last_error
    try:
        _touch_activity()
        from api.websocket import broadcast_full_state
        from status.status_cache import get_cache
        import asyncio

        cache = get_cache()
        if filepath:
            agent_id = _extract_agent_id_from_path(filepath)
            if agent_id:
                cache.invalidate(agent_id)
            else:
                cache.invalidate()
        else:
            cache.invalidate()

        loop = _event_loop
        if loop and broadcast_full_state:
            future = asyncio.run_coroutine_threadsafe(broadcast_full_state(), loop)
            future.result(timeout=10)
    except Exception as e:
        _last_error = str(e)
        record_error("unknown", str(e), "file_watcher_push")


def _build_observer() -> Any:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    RELEVANT_SUFFIXES = (".json", ".jsonl", ".log")

    class Handler(FileSystemEventHandler):
        def _should_trigger(self, src_path: str) -> bool:
            return any(src_path.endswith(s) for s in RELEVANT_SUFFIXES)

        def on_modified(self, event):
            if event.is_directory:
                return
            if self._should_trigger(event.src_path) and _handler:
                _handler.trigger(event.src_path)

        def on_created(self, event):
            if event.is_directory:
                return
            if self._should_trigger(event.src_path) and _handler:
                _handler.trigger(event.src_path)

    watch_dirs = _get_watch_dirs()
    if not watch_dirs:
        raise RuntimeError("no watch dirs")

    global _handler, _observer
    _handler = DebouncedHandler(_on_file_changed)
    obs = Observer()
    for watch_dir, recursive in watch_dirs:
        obs.schedule(Handler(), str(watch_dir), recursive=recursive)
    return obs


def _stop_watchdog_observer() -> None:
    global _observer
    if _observer:
        try:
            _observer.stop()
            _observer.join(timeout=2)
        except Exception:
            pass
        _observer = None


def _start_monitor_thread(loop) -> None:
    global _monitor_thread
    if _monitor_thread and _monitor_thread.is_alive():
        return

    def monitor() -> None:
        cfg = get_fortify_config()
        global _watchdog_failure_since
        while not _monitor_stop.is_set():
            time.sleep(5)
            if _monitor_stop.is_set():
                break
            if _watcher_mode != "watchdog":
                continue
            obs = _observer
            if obs is None:
                continue
            if obs.is_alive():
                _watchdog_failure_since = None
                continue
            now = time.time()
            if _watchdog_failure_since is None:
                _watchdog_failure_since = now
            elif now - _watchdog_failure_since >= cfg.watcher_failure_window_sec:
                record_error("io-error", "observer not alive, fallback to polling", "file_watcher")
                _switch_to_polling(loop)

    _monitor_stop.clear()
    t = threading.Thread(target=monitor, daemon=True)
    t.start()
    _monitor_thread = t


def _switch_to_polling(loop) -> None:
    global _switch_count
    with _health_lock:
        _stop_watchdog_observer()
        _switch_count += 1
    _persist_watcher_state()
    _start_polling_mode(loop)


def _cancel_poll_timer() -> None:
    global _poll_timer
    if _poll_timer:
        try:
            _poll_timer.cancel()
        except Exception:
            pass
        _poll_timer = None


def _start_polling_mode(loop) -> None:
    global _watcher_mode, _poll_timer, _poll_ticks
    _set_mode("polling")
    cfg = get_fortify_config()
    _cancel_poll_timer()

    def tick() -> None:
        global _poll_timer, _poll_ticks
        if _monitor_stop.is_set():
            return
        if _watcher_mode != "polling":
            return
        try:
            _on_file_changed(None)
        except Exception as e:
            record_error("unknown", str(e), "polling_tick")
        _poll_ticks += 1
        if _poll_ticks >= 12:
            _poll_ticks = 0
            _try_resume_watchdog(loop)
        _poll_timer = threading.Timer(cfg.watcher_poll_interval_sec, tick)
        _poll_timer.daemon = True
        _poll_timer.start()

    _poll_ticks = 0
    tick()


def _try_resume_watchdog(loop) -> None:
    global _watcher_mode, _resume_success_count, _resume_failure_count
    if _watcher_mode != "polling" or _monitor_stop.is_set():
        return
    cfg = get_fortify_config()
    try:
        obs = _build_observer()
        obs.start()
        global _observer
        _observer = obs
        _cancel_poll_timer()
        with _health_lock:
            _resume_success_count += 1
        _set_mode("watchdog")
        _start_monitor_thread(loop)
        _LOG.info("file watcher resumed from polling to watchdog mode")
        _full_resync_cache_and_push()
    except Exception as e:
        with _health_lock:
            _resume_failure_count += 1
        _persist_watcher_state()
        record_error("io-error", str(e), "watchdog_resume")


def start_file_watcher(loop) -> None:
    global _event_loop, _started_at, _observer
    _monitor_stop.clear()
    _event_loop = loop
    _started_at = time.time()
    cfg = get_fortify_config()

    try:
        __import__("watchdog.observers", fromlist=["Observer"])
    except ImportError:
        record_error("io-error", "watchdog not installed", "file_watcher")
        _set_mode("import_failed")
        _start_polling_mode(loop)
        _LOG.warning("watchdog package not installed; using polling mode")
        return

    delay = cfg.retry_base_delay
    last_exc: Optional[Exception] = None
    for attempt in range(cfg.watcher_max_retries):
        try:
            obs = _build_observer()
            obs.start()
            _observer = obs
            _set_mode("watchdog")
            _start_monitor_thread(loop)
            _LOG.info("watchdog started (attempt %s)", attempt + 1)
            _persist_watcher_state()
            return
        except Exception as e:
            last_exc = e
            _stop_watchdog_observer()
            record_error("io-error", str(e), f"file_watcher_start_{attempt}")
            time.sleep(delay * (2**attempt))

    if last_exc:
        _last_error = str(last_exc)
    _switch_to_polling(loop)
    _LOG.warning("watchdog start failed after retries; switched to polling mode")


def stop_file_watcher() -> None:
    global _monitor_thread, _watcher_mode
    _monitor_stop.set()
    _cancel_poll_timer()
    _stop_watchdog_observer()
    _set_mode("stopped")
    _persist_watcher_state()
    _LOG.info("file watcher stopped")


def get_watcher_health() -> Dict[str, Any]:
    cfg = get_fortify_config()
    obs_alive = bool(_observer and _observer.is_alive())
    mode = _watcher_mode
    if mode == "import_failed":
        display_mode = "polling"
    else:
        display_mode = mode

    status = "healthy"
    if mode in ("polling", "import_failed"):
        status = "degraded"
    elif mode == "stopped":
        status = "down"
    elif mode == "watchdog" and _observer and not obs_alive:
        status = "degraded"

    hb = None
    if _last_heartbeat:
        hb = datetime.fromtimestamp(_last_heartbeat, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    with _health_lock:
        rc_ok = _resume_success_count
        rc_fail = _resume_failure_count
        sw = _switch_count
        last_sync = _last_full_sync_iso

    fw_err = _watcher_framework_error_count()
    snapshot = _read_persisted_watcher_state()

    return {
        "status": status,
        "mode": display_mode,
        "last_heartbeat": hb,
        # error_count：与 /api/errors/stats 同源（record_error 中 file_watcher* / watchdog_resume / polling_tick）
        "error_count": fw_err,
        "switch_count": sw,
        "resume_watchdog_success_count": rc_ok,
        "resume_watchdog_failure_count": rc_fail,
        "last_full_sync": last_sync,
        "uptime_seconds": int(time.time() - _started_at) if _started_at else 0,
        "events_processed": _events_processed,
        "last_error": _last_error,
        "observer_alive": obs_alive,
        "poll_interval_sec": cfg.watcher_poll_interval_sec,
        "persisted_snapshot": snapshot,
    }
