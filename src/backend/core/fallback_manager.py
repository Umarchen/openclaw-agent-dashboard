"""
REQ_003-SPEC-04：按错误类型注册集中降级策略；供状态计算、列表聚合等路径调用。

REQ_003-AC-003：网络/IO 等错误在重试仍失败或未覆盖时，可读 StatusCache 中的最近状态（见 status_cache.get_stale_fallback）。
"""
from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional

_Handler = Callable[..., Any]

_lock = threading.Lock()
_handlers: Dict[str, _Handler] = {}
_defaults_registered = False


def register_fallback(error_category: str, handler: _Handler) -> None:
    """注册某 classify_exception 类别对应的降级函数；handler 签名为 (agent_id=None, **kwargs) -> Any。"""
    with _lock:
        _handlers[error_category] = handler


def run_fallback(error_category: str, *, agent_id: Optional[str] = None, **kwargs: Any) -> Any:
    """按类别执行已注册降级；无匹配则返回 None。"""
    _ensure_default_fallbacks()
    with _lock:
        h = _handlers.get(error_category)
    if h is None:
        return None
    return h(agent_id=agent_id, **kwargs)


def _stale_agent_status_handler(agent_id: Optional[str] = None, **_: Any) -> Optional[str]:
    if not agent_id:
        return None
    from core.config_fortify import get_fortify_config

    if not get_fortify_config().fallback_cache_on_io:
        return None
    from status.status_cache import get_cache

    row = get_cache().get_stale_fallback(agent_id)
    if not row:
        return None
    s = row.get("status")
    if s in ("idle", "working", "down"):
        return str(s)
    return None


def _ensure_default_fallbacks() -> None:
    global _defaults_registered
    if _defaults_registered:
        return
    with _lock:
        if _defaults_registered:
            return
        for cat in ("network", "io-error", "timeout", "permission-error"):
            if cat not in _handlers:
                _handlers[cat] = _stale_agent_status_handler
        _defaults_registered = True


def reset_fallback_handlers_for_tests() -> None:
    """单测隔离：清空注册表并允许重新挂载默认处理器。"""
    global _handlers, _defaults_registered
    with _lock:
        _handlers.clear()
        _defaults_registered = False
