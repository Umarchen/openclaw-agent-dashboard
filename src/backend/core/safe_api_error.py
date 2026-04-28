"""
面向浏览器/API 客户端的错误文案脱敏（NFR-S-001）。
服务端日志仍由 record_error 记录完整信息（默认不截断）。
"""
from __future__ import annotations

import re
from typing import Any, Dict


def sanitize_client_error_text(raw: str, max_len: int = 1200) -> str:
    """去除常见密钥/路径/邮箱形态，压缩长度；含 Traceback 时整段替换。"""
    if not raw:
        return "internal error"
    s = raw.replace("\r", " ").replace("\n", " ")
    if len(s) > max_len * 2:
        s = s[: max_len * 2]
    if "Traceback (most recent call last)" in raw or '\n  File "' in raw:
        return "Internal error (details redacted; see server logs)"

    s = re.sub(r"\bsk-[a-zA-Z0-9]{12,}\b", "sk-[REDACTED]", s, flags=re.I)
    s = re.sub(r"\bxox[baprs]-[a-zA-Z0-9-]{10,}\b", "[slack-token]", s)
    s = re.sub(r"Bearer\s+[a-zA-Z0-9._=+\/-]{12,}", "Bearer [REDACTED]", s, flags=re.I)
    s = re.sub(
        r"\bAKIA[0-9A-Z]{16}\b",
        "AKIA[REDACTED]",
        s,
    )
    s = re.sub(r"(?i)password\s*[=:]\s*[^\s,}\"]{2,}", "password=[REDACTED]", s)
    s = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[email]",
        s,
    )
    s = re.sub(r"(?:/home/|/Users/)[^\s:]{1,80}/[^\s:]{0,200}", "[path]", s)
    s = re.sub(r"[A-Za-z]:\\(?:[^\\\s]+\\){0,8}[^\s\\]{0,120}", "[path]", s)
    s = re.sub(r"/[^\s:]{0,16}\.openclaw(?:/[^\s:]{0,160})?", "[openclaw-path]", s)

    if len(s) > max_len:
        s = s[:max_len] + "…"
    return s


def safe_client_string(message: str) -> str:
    """JSON 响应体中的 error 等字符串字段脱敏。"""
    from core.config_fortify import get_fortify_config

    raw = message or ""
    if not get_fortify_config().sanitize_api_errors:
        return raw[:4000]
    return sanitize_client_error_text(raw)


def safe_api_error_detail(exc: BaseException) -> str:
    """HTTP 500 等返回给客户端的 detail 字符串。"""
    from core.config_fortify import get_fortify_config

    raw = str(exc).strip() or type(exc).__name__
    if not get_fortify_config().sanitize_api_errors:
        return raw[:4000]
    return sanitize_client_error_text(raw)


def redact_framework_stats_for_client(data: Dict[str, Any]) -> Dict[str, Any]:
    """为 /api/errors/stats 等接口脱敏 last_error.detail。"""
    from core.config_fortify import get_fortify_config

    if not get_fortify_config().sanitize_api_errors:
        return data
    out = dict(data)
    le = out.get("last_error")
    if isinstance(le, dict) and le.get("detail"):
        le = dict(le)
        le["detail"] = sanitize_client_error_text(str(le["detail"]))
        out["last_error"] = le
    return out
