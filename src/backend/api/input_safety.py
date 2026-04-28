"""
外部路径与 Query 边界校验（NFR-S-002）。
拒绝路径逃逸与过长输入，避免异常 agent_id / session 片段误触文件逻辑。
"""
from __future__ import annotations

from fastapi import HTTPException

_MAX_AGENT_ID_LEN = 128
_MAX_SESSION_KEY_LEN = 512
_MAX_RUN_CHAIN_ID_LEN = 128
_MAX_SESSION_FILE_SEGMENT = 256


def require_safe_agent_id(agent_id: str) -> str:
    s = (agent_id or "").strip()
    if not s or len(s) > _MAX_AGENT_ID_LEN:
        raise HTTPException(status_code=400, detail="invalid agent_id")
    if "\x00" in s:
        raise HTTPException(status_code=400, detail="invalid agent_id")
    if ".." in s:
        raise HTTPException(status_code=400, detail="invalid agent_id")
    for ch in ("/", "\\"):
        if ch in s:
            raise HTTPException(status_code=400, detail="invalid agent_id")
    low = s.lower()
    if "%2f" in low or "%5c" in low or "%2e%2e" in low:
        raise HTTPException(status_code=400, detail="invalid agent_id")
    return s


def require_safe_session_key(session_key: str | None) -> str | None:
    if session_key is None:
        return None
    s = session_key.strip()
    if not s:
        return None
    if len(s) > _MAX_SESSION_KEY_LEN or "\x00" in s:
        raise HTTPException(status_code=400, detail="invalid session_key")
    if ".." in s or "/" in s or "\\" in s:
        raise HTTPException(status_code=400, detail="invalid session_key")
    return s


def require_safe_session_file_segment(session_file: str) -> str:
    s = (session_file or "").strip()
    if not s or len(s) > _MAX_SESSION_FILE_SEGMENT:
        raise HTTPException(status_code=400, detail="invalid session_file")
    if "\x00" in s or ".." in s or "/" in s or "\\" in s:
        raise HTTPException(status_code=400, detail="invalid session_file")
    return s


def require_safe_run_or_chain_id(value: str, *, name: str = "id") -> str:
    s = (value or "").strip()
    if not s or len(s) > _MAX_RUN_CHAIN_ID_LEN:
        raise HTTPException(status_code=400, detail=f"invalid {name}")
    if "\x00" in s or ".." in s or "/" in s or "\\" in s:
        raise HTTPException(status_code=400, detail=f"invalid {name}")
    return s
