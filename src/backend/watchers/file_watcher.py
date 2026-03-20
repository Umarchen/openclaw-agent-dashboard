"""
文件变更监听 - 关键文件变更时触发 WebSocket 推送
使用 watchdog 监听 runs.json、sessions/*.jsonl、task_history.json、model-failures.log
集成缓存失效机制，确保状态一致性
"""
import threading
import time
from pathlib import Path
from typing import Callable, Optional


def _extract_agent_id_from_path(filepath: str) -> Optional[str]:
    """从文件路径中提取 Agent ID（跨平台兼容）
    
    Args:
        filepath: 文件路径（Unix 或 Windows 风格）
        
    Returns:
        Agent ID，无法解析时返回 None
        
    Examples:
        /path/to/.openclaw/agents/main/sessions/xxx.jsonl -> main
        C:\\path\\to\\.openclaw\\agents\\main\\sessions\\xxx.jsonl -> main
    """
    try:
        path = Path(filepath)
        parts = path.parts
        
        # 查找 'agents' 目录的位置
        try:
            agents_idx = parts.index('agents')
        except ValueError:
            return None
        
        # 检查结构: .../agents/{agent_id}/sessions/...
        # agents_idx + 1 = agent_id
        # agents_idx + 2 = 'sessions'
        if agents_idx + 2 < len(parts) and parts[agents_idx + 2] == 'sessions':
            return parts[agents_idx + 1]
        
        return None
    except Exception:
        return None


def _get_openclaw_dir() -> Path:
    from data.config_reader import get_openclaw_root
    return get_openclaw_root()
DEBOUNCE_SECONDS = 0.3  # 同一文件短时间多次变更只触发一次


def _get_watch_dirs() -> list[tuple[Path, bool]]:
    """获取需要监听的目录列表 (path, recursive)"""
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
    # workspace/*/memory: 从配置读取，或回退到 workspace-main
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
            
            # 保存文件路径
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
                    print(f"[FileWatcher] 回调异常: {e}")

            if now - self._last_trigger < self.debounce_sec:
                self._timer = threading.Timer(self.debounce_sec - (now - self._last_trigger), do_callback)
                self._timer.daemon = True
                self._timer.start()
            else:
                do_callback()


_observer = None
_handler = None


def _on_file_changed(filepath: Optional[str] = None) -> None:
    """文件变更时触发 WebSocket 推送 + 缓存失效
    
    Args:
        filepath: 变更的文件路径（可选）
    """
    try:
        from api.websocket import broadcast_full_state
        from status.status_cache import get_cache
        import asyncio
        
        # 失效缓存
        cache = get_cache()
        if filepath:
            # 解析受影响的 Agent ID（跨平台兼容）
            # 例如：/path/to/.openclaw/agents/main/sessions/xxx.jsonl -> main
            # 或 Windows: C:\path\to\.openclaw\agents\main\sessions\xxx.jsonl -> main
            agent_id = _extract_agent_id_from_path(filepath)
            if agent_id:
                cache.invalidate(agent_id)
                print(f"[FileWatcher] 失效缓存: {agent_id}")
            else:
                # 无法解析，清空所有缓存
                cache.invalidate()
                print(f"[FileWatcher] 失效所有缓存（无法解析Agent）")
        else:
            # 无文件路径，清空所有缓存
            cache.invalidate()
        
        # 触发推送
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
                _handler.trigger(event.src_path)

        def on_created(self, event):
            if event.is_directory:
                return
            if self._should_trigger(event.src_path):
                _handler.trigger(event.src_path)

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
