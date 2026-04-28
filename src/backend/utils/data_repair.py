"""
JSON line repair (memory-first), optional write-back with backup, audit logging.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config_fortify import get_fortify_config
from core.schemas.base import SchemaValidator
from core.schemas.session_schema import session_envelope_schema, session_message_schema

_audit_log = logging.getLogger("openclaw.fortify.audit")


def _ensure_audit_logging() -> None:
    if _audit_log.handlers:
        return
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s | AUDIT | %(message)s"))
    _audit_log.addHandler(h)
    _audit_log.setLevel(logging.INFO)


def _truncate(s: str, max_len: int = 500) -> str:
    s = s or ""
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"...({len(s)} chars)"


def audit_repair(
    operation: str,
    original_summary: str,
    repaired_summary: str,
    operator: str = "backend",
) -> None:
    _ensure_audit_logging()
    _audit_log.info(
        "audit_repair op=%s operator=%s original_sha256=%s repaired_sha256=%s original=%s repaired=%s",
        operation,
        operator,
        hashlib.sha256(original_summary.encode("utf-8", errors="replace")).hexdigest()[:16],
        hashlib.sha256(repaired_summary.encode("utf-8", errors="replace")).hexdigest()[:16],
        _truncate(original_summary),
        _truncate(repaired_summary),
    )


def attempt_line_json_repair(raw: str, max_attempts: Optional[int] = None) -> Tuple[Optional[str], List[str]]:
    """Heuristic repairs for a single JSONL line. Returns (fixed_line_or_none, attempts_log)."""
    cfg = get_fortify_config()
    attempts = cfg.max_repair_attempts if max_attempts is None else max_attempts
    log: List[str] = []
    s = raw
    if not s or not s.strip():
        return None, ["empty"]
    for i in range(attempts):
        try:
            json.loads(s)
            if i > 0:
                log.append(f"ok_after_attempt_{i}")
            return s, log
        except json.JSONDecodeError as e:
            log.append(f"attempt_{i}:{e.msg}")
        # progressive fixes
        if s.startswith("\ufeff"):
            s = s[1:]
            continue
        s2 = re.sub(r",\s*}", "}", s)
        s2 = re.sub(r",\s*]", "]", s2)
        if s2 != s:
            s = s2
            continue
        s2 = s.replace("'", '"')
        if s2 != s:
            s = s2
            continue
        break
    return None, log


def parse_session_jsonl_line(
    line: str,
    *,
    auto_repair: Optional[bool] = None,
    json_strict: Optional[bool] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Parse one JSONL line for session files.
    Returns (envelope_dict, message_dict_or_none) for type=message; on total failure (None, None).
    """
    cfg = get_fortify_config()
    use_repair = cfg.auto_repair_json if auto_repair is None else auto_repair
    strict = cfg.json_strict if json_strict is None else json_strict
    stripped = line.strip()
    if not stripped:
        return None, None

    def _loads(s: str) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(s)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None

    data = _loads(stripped)
    if data is None and use_repair:
        repaired, _ = attempt_line_json_repair(stripped)
        if repaired:
            data = _loads(repaired)
            if data is not None:
                audit_repair("json_line_memory", stripped, repaired)

    if not data:
        from core.error_handler import record_error

        record_error("parsing-error", "json_decode session line", "session_jsonl")
        return None, None

    env_validator = SchemaValidator(session_envelope_schema, strict=strict)
    env_res = env_validator.validate(data)
    if not env_res.is_valid:
        from core.error_handler import record_error

        record_error("validation-error", env_res.error_message, "session_envelope")
        if strict and not use_repair:
            return None, None

    if data.get("type") != "message":
        return data, None

    msg = data.get("message")
    if not isinstance(msg, dict):
        if use_repair:
            msg = {}
            data = {**data, "message": msg}
            audit_repair("message_coerce", line, json.dumps(data, ensure_ascii=False)[:500])
        else:
            return data, None

    msg_schema = dict(session_message_schema)
    if not strict:
        msg_schema = dict(msg_schema)
        msg_schema.pop("required", None)
    mv = SchemaValidator(msg_schema, strict=strict)
    mv_res = mv.validate(msg)
    if mv_res.is_valid:
        return data, msg

    if use_repair:
        repaired_msg = dict(msg)
        if "role" not in repaired_msg:
            repaired_msg["role"] = "assistant"
        relaxed = dict(msg_schema)
        relaxed.pop("required", None)
        mv2 = SchemaValidator(relaxed, strict=False)
        if mv2.validate(repaired_msg).is_valid:
            audit_repair("message_schema_repair", json.dumps(msg), json.dumps(repaired_msg))
            return data, repaired_msg

    from core.error_handler import record_error

    record_error("validation-error", mv_res.error_message, "session_message")
    if strict:
        return data, None
    return data, msg  # loose mode: return raw message even if schema warnings


def validate_message_dict(msg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    cfg = get_fortify_config()
    msg_schema = dict(session_message_schema)
    if not cfg.json_strict:
        msg_schema.pop("required", None)
    mv = SchemaValidator(msg_schema, strict=cfg.json_strict)
    r = mv.validate(msg)
    return r.is_valid, r.errors


def write_repaired_json_file(
    path: Path,
    new_content: str,
    *,
    operator: str = "backend",
) -> None:
    """Write repaired file with mandatory backup when config enables write-back."""
    cfg = get_fortify_config()
    if not cfg.auto_repair_write_back:
        raise RuntimeError("write-back disabled")
    backup_root = cfg.repair_backup_path
    if not backup_root:
        raise RuntimeError("OPENCLAW_REPAIR_BACKUP required for write-back")
    backup_dir = Path(backup_root)
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = __import__("time").strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.name}.{ts}.bak"
    if path.exists():
        shutil.copy2(path, backup_path)
    path.write_text(new_content, encoding="utf-8")
    audit_repair(
        "json_file_write_back",
        f"path={path} backup={backup_path}",
        _truncate(new_content, 800),
        operator=operator,
    )
