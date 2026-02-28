"""
文件变更监听 - 关键文件变更时触发 WebSocket 推送
使用 watchdog 监听 runs.json、sessions/*.jsonl、task_history.json、model-failures.log
"""
import threading
import time
from pathlib import Path
from typing import Callable, Optional

OPENCLAW_DIR = Path.home() / ".openclaw"
DEBOUNCE_SECONDS = 0.3  # 同一文件短时间多次变更只触发一次


def _get_watch_dirs() -> list[tuple[Path, bool]]:
    """获取需要监听的目录列表 (path, recursive)"""
    dirs: list[tuple[Path, bool]] = []
    subagents = OPENCLAW_DIR / "subagents"
    if subagents.exists():
        dirs.append((subagents, False))
    dashboard = OPENCLAW_DIR / "dashboard"
    if dashboard.exists():
        dirs.append((dashboard, False))
    # workspace/*/memory: 从配置读取，或回退到 workspace-main
    try:
        from data.config_reader import get_workspace_paths
        for ws in get_workspace_paths():
            memory = ws / "memory"
            if memory.exists():
                dirs.append((memory, False))
    except Exception:
        memory = OPENCLAW_DIR / "workspace-main" / "memory"
        if memory.exists():
            dirs.append((memory, False))
    agents_dir = OPENCLAW_DIR / "agents"
    if agents_dir.exists():
        for agent_dir in agents_dir.iterdir():
            if agent_dir.is_dir():
                sessions_dir = agent_dir / "sessions"
                if sessions_dir.exists():
                    dirs.append((sessions_dir, True))
    return dirs


class DebouncedHandler:
    """防抖：短时间多次变更只触发一次回调"""

    def __init__(self, callback: Callable[[], None], debounce_sec: float = DEBOUNCE_SECONDS):
        self.callback = callback
        self.debounce_sec = debounce_sec
        self._last_trigger: float = 0
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    def trigger(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self._timer:
                self._timer.cancel()
                self._timer = None

            def do_callback() -> None:
                with self._lock:
                    self._last_trigger = time.monotonic()
                    self._timer = None
                try:
                    self.callback()
                except Exception as e:
                    print(f"[FileWatcher] 回调异常: {e}")

            if now - self._last_trigger < self.debounce_sec:
                self._timer = threading.Timer(self.debounce_sec - (now - self._last_trigger), do_callback)
                self._timer.daemon = True
                self._timer.start()
            else:
                do_callback()


_observer = None
_handler = None


def _on_file_changed() -> None:
    """文件变更时触发 WebSocket 推送"""
    try:
        from api.websocket import broadcast_full_state
        import asyncio

        loop = _event_loop
        if loop and broadcast_full_state:
            future = asyncio.run_coroutine_threadsafe(broadcast_full_state(), loop)
            future.result(timeout=10)
    except Exception as e:
        print(f"[FileWatcher] 推送失败: {e}")


_event_loop = None


def start_file_watcher(loop) -> None:
    """启动文件监听（在 FastAPI 启动时调用）"""
    global _observer, _handler, _event_loop
    _event_loop = loop

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
    except ImportError:
        print("[FileWatcher] watchdog 未安装，跳过文件监听。请执行: pip install watchdog")
        return

    RELEVANT_SUFFIXES = (".json", ".jsonl", ".log")

    class Handler(FileSystemEventHandler):
        def _should_trigger(self, src_path: str) -> bool:
            return any(src_path.endswith(s) for s in RELEVANT_SUFFIXES)

        def on_modified(self, event):
            if event.is_directory:
                return
            if self._should_trigger(event.src_path):
                _handler.trigger()

        def on_created(self, event):
            if event.is_directory:
                return
            if self._should_trigger(event.src_path):
                _handler.trigger()

    watch_dirs = _get_watch_dirs()
    if not watch_dirs:
        print("[FileWatcher] 无有效监听路径，跳过")
        return

    _handler = DebouncedHandler(_on_file_changed)
    _observer = Observer()

    for watch_dir, recursive in watch_dirs:
        _observer.schedule(Handler(), str(watch_dir), recursive=recursive)

    _observer.start()
    print(f"[FileWatcher] 已启动，监听 {len(watch_dirs)} 个目录")


def stop_file_watcher() -> None:
    """停止文件监听"""
    global _observer
    if _observer:
        _observer.stop()
        _observer.join(timeout=2)
        _observer = None
        print("[FileWatcher] 已停止")
