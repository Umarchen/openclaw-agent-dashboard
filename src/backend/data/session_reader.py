"""
会话读取器 - 读取 sessions/*.jsonl 和 sessions.json
"""
import hashlib
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional


from data.config_reader import get_openclaw_root, normalize_openclaw_agent_id
from utils.data_repair import parse_session_jsonl_line

_META_SESSION_INDEX_KEYS = frozenset({"entries", "version", "schema"})

# 校验报告：大文件仅哈希尾部，与 tail 读取策略一致；小文件全量哈希
_MAX_FULL_HASH_BYTES = 4 * 1024 * 1024
_TAIL_HASH_BYTES = 512 * 1024


def compute_session_file_integrity(path: Path) -> Dict[str, Any]:
    """文件级完整性元数据：size、mtime、sha256（全文件或尾部窗口）。"""
    try:
        st = path.stat()
    except OSError as e:
        return {"path": str(path), "error": f"stat_failed:{e}"}
    size = int(st.st_size)
    mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
    out: Dict[str, Any] = {
        "path": str(path.resolve()),
        "size_bytes": size,
        "mtime_ns": mtime_ns,
    }
    try:
        if size == 0:
            out["sha256"] = hashlib.sha256(b"").hexdigest()
            out["hash_scope"] = "full"
            return out
        if size <= _MAX_FULL_HASH_BYTES:
            with open(path, "rb") as f:
                out["sha256"] = hashlib.sha256(f.read()).hexdigest()
            out["hash_scope"] = "full"
        else:
            with open(path, "rb") as f:
                f.seek(max(0, size - _TAIL_HASH_BYTES))
                tail = f.read()
            out["sha256"] = hashlib.sha256(tail).hexdigest()
            out["hash_scope"] = "tail_512kb"
            out["tail_hashed_bytes"] = len(tail)
    except OSError as e:
        out["error"] = f"read_failed:{e}"
    return out


def resolve_validated_session_jsonl(agent_id: str, relative: str) -> Optional[Path]:
    """将相对路径解析为 agents/{id}/sessions 下的 .jsonl，禁止逃逸。"""
    if not relative or not relative.strip():
        return None
    aid = normalize_openclaw_agent_id(agent_id)
    base = get_openclaw_root() / "agents" / aid / "sessions"
    if not base.is_dir():
        return None
    try:
        base_r = base.resolve()
    except OSError:
        return None
    rel = Path(relative.strip())
    if rel.is_absolute() or ".." in rel.parts:
        return None
    try:
        cand = (base_r / rel).resolve()
        cand.relative_to(base_r)
    except ValueError:
        return None
    if not cand.is_file() or cand.suffix.lower() != ".jsonl":
        return None
    return cand


def normalize_sessions_index(raw: Any) -> Dict[str, Dict[str, Any]]:
    """
    统一 sessions.json 结构（跨平台兼容 OpenClaw 不同版本）：
    - 常见嵌套：{"entries": {"agent:...": {...}}}
    - 扁平：{"agent:...": {...}}
    """
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    inner = raw.get("entries")
    if isinstance(inner, dict):
        for k, v in inner.items():
            if isinstance(v, dict):
                out[str(k)] = v
    for k, v in raw.items():
        if k in _META_SESSION_INDEX_KEYS or not isinstance(v, dict):
            continue
        out.setdefault(str(k), v)
    return out


def resolve_session_jsonl_path(sessions_dir: Path, entry: Dict[str, Any]) -> Optional[Path]:
    """
    由 sessions.json 单条记录解析真实 .jsonl 路径。
    兼容：绝对路径、相对 sessions 目录、仅文件名（避免 Windows 下 cwd 非 sessions 导致找不到文件）。
    """
    sf = entry.get("sessionFile")
    sid = entry.get("sessionId")
    try:
        sessions_dir = sessions_dir.resolve()
    except OSError:
        sessions_dir = sessions_dir

    if sf:
        p = Path(str(sf))
        try:
            if p.is_file():
                return p.resolve()
        except OSError:
            pass
        for cand in (sessions_dir / sf, sessions_dir / p.name):
            try:
                if cand.is_file():
                    return cand.resolve()
            except OSError:
                continue
    if sid:
        cand = sessions_dir / f"{sid}.jsonl"
        try:
            if cand.is_file():
                return cand.resolve()
        except OSError:
            pass
    return None


def _load_sessions_index_file(sessions_index: Path) -> Optional[Dict[str, Any]]:
    """读取 sessions.json；可选 JSON Schema 校验（OPENCLAW_JSON_STRICT）。失败返回 None 并记录错误。"""
    if not sessions_index.exists():
        return None
    try:
        with open(sessions_index, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        from core.error_handler import record_error

        record_error("parsing-error", str(e), "sessions_index", exc=e)
        return None
    if not isinstance(data, dict):
        from core.error_handler import record_error

        record_error("validation-error", "sessions index root is not an object", "sessions_index")
        return None
    from core.config_fortify import get_fortify_config
    from core.schemas.base import SchemaValidator
    from core.schemas.session_schema import sessions_index_schema

    cfg = get_fortify_config()
    vr = SchemaValidator(sessions_index_schema, strict=cfg.json_strict).validate(data)
    if not vr.is_valid:
        from core.error_handler import record_error

        record_error("validation-error", vr.error_message, "sessions_index")
        if cfg.json_strict:
            return None
    return data


def get_agent_sessions_path(agent_id: str) -> Optional[Path]:
    """获取 Agent 的 sessions 目录"""
    sessions_path = get_openclaw_root() / "agents" / normalize_openclaw_agent_id(agent_id) / "sessions"
    if not sessions_path.exists():
        return None
    return sessions_path


def get_latest_session_file(agent_id: str) -> Optional[Path]:
    """获取最新的 session 文件"""
    sessions_path = get_agent_sessions_path(agent_id)
    if not sessions_path:
        return None
    
    jsonl_files = list(sessions_path.glob("*.jsonl"))
    if not jsonl_files:
        return None
    
    # 按修改时间排序，取最新的
    jsonl_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return jsonl_files[0]


def _read_tail_lines(filepath: Path, max_lines: int) -> List[str]:
    """从文件尾部读取最多 max_lines 行，避免全量遍历大文件"""
    try:
        with open(filepath, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []
            # 读取末尾约 512KB，通常足够覆盖 500 行
            to_read = min(512 * 1024, size)
            f.seek(size - to_read)
            buf = f.read(to_read)
            lines = buf.split(b'\n')
            # 若未从文件头开始读，首行可能是断行，丢弃
            if size > to_read and lines:
                lines = lines[1:]
            decoded = [ln.decode('utf-8', errors='replace') for ln in lines[-max_lines:] if ln]
            return decoded
    except (IOError, OSError):
        return []


def get_recent_messages(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """获取最近的会话消息（尾部读取，避免全量遍历大 jsonl）"""
    session_file = get_latest_session_file(agent_id)
    if not session_file:
        return []
    # 多读一些行以过滤 type!=message 的行
    raw_lines = _read_tail_lines(session_file, max(limit * 5, 500))
    messages = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        _, msg = parse_session_jsonl_line(line)
        if msg is not None:
            messages.append(msg)
    # 必须取尾部：原先在扫描到 limit 条就 break，会拿到「窗口内较早」的消息而非最新，导致 tool/ thinking 误判
    return messages[-limit:] if len(messages) > limit else messages


def get_latest_user_message_text(agent_id: str, scan_limit: int = 80) -> str:
    """
    从最新会话中取最近一条 user 消息的文本（不做截断）。
    用于无 subagent run 时展示当前任务摘要（独立 PM / 仅主会话）。
    """
    messages = get_recent_messages(agent_id, limit=scan_limit)
    for msg in reversed(messages):
        if msg.get('role') != 'user':
            continue
        content = msg.get('content', [])
        if isinstance(content, str):
            t = content.strip()
            if t:
                return t
        elif isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'text':
                    t = (c.get('text') or '').strip()
                    if t:
                        return t
    return ''


def has_recent_errors(agent_id: str, minutes: int = 5) -> bool:
    """检查最近是否有错误"""
    messages = get_recent_messages(agent_id, limit=50)
    
    import time
    cutoff_time = int(time.time() * 1000) - (minutes * 60 * 1000)
    
    for msg in messages:
        if msg.get('stopReason') == 'error':
            timestamp = msg.get('timestamp', 0)
            if timestamp > cutoff_time:
                return True
    
    return False


def get_last_error(agent_id: str) -> Optional[Dict[str, Any]]:
    """获取最近的错误信息"""
    messages = get_recent_messages(agent_id, limit=100)
    
    for msg in reversed(messages):
        if msg.get('stopReason') == 'error':
            return {
                'type': detect_error_type(msg.get('errorMessage', '')),
                'message': msg.get('errorMessage', ''),
                'timestamp': msg.get('timestamp', 0)
            }
    
    return None


def detect_error_type(error_msg: str) -> str:
    """检测错误类型"""
    error_msg_lower = (error_msg or '').lower()
    
    if '429' in error_msg or 'rate limit' in error_msg_lower:
        return 'rate-limit'
    elif 'token' in error_msg_lower or 'context' in error_msg_lower:
        return 'token-limit'
    elif 'timeout' in error_msg_lower or '超时' in error_msg_lower:
        return 'timeout'
    elif '余额不足' in (error_msg or ''):
        return 'quota'
    else:
        return 'unknown'


def get_session_updated_at(agent_id: str) -> int:
    """
    获取 Agent 会话的最后更新时间（sessions.json 中 updatedAt 的最大值）
    用于判断「最近 5 分钟是否有 session 活动」
    """
    aid = normalize_openclaw_agent_id(agent_id)
    sessions_index = get_openclaw_root() / "agents" / aid / "sessions" / "sessions.json"
    if not sessions_index.exists():
        return 0

    data = _load_sessions_index_file(sessions_index)
    if not data:
        return 0
    index_map = normalize_sessions_index(data)
    max_ts = 0
    for entry in index_map.values():
        ts = entry.get("updatedAt") or entry.get("lastMessageAt") or 0
        if isinstance(ts, (int, float)) and ts > max_ts:
            max_ts = int(ts)
    return max_ts


def has_recent_session_activity(agent_id: str, minutes: int = 5) -> bool:
    """检查 Agent 最近 N 分钟内是否有 session 活动"""
    import time
    updated_at = get_session_updated_at(agent_id)
    if not updated_at:
        return False
    cutoff = int(time.time() * 1000) - (minutes * 60 * 1000)
    return updated_at > cutoff


def is_session_updated_within_seconds(agent_id: str, max_seconds: int) -> bool:
    """
    sessions.json 聚合的 updatedAt 是否在 max_seconds 秒内。
    用于主 Agent 纯流式/首包前等「暂无 thinking、无 tool」时的短时 working 兜底。
    """
    import time
    if max_seconds <= 0:
        return False
    updated_at = get_session_updated_at(agent_id)
    if not updated_at:
        return False
    cutoff = int(time.time() * 1000) - max_seconds * 1000
    return updated_at > cutoff


def get_session_turns(agent_id: str, session_key: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    解析 jsonl 获取会话轮次，每轮包含 user/assistant/toolResult 及 usage
    返回格式: [{ turnIndex, role, content, usage?, toolCalls?, stopReason?, timestamp }]
    """
    aid = normalize_openclaw_agent_id(agent_id)
    sessions_index = get_openclaw_root() / "agents" / aid / "sessions" / "sessions.json"
    if not sessions_index.exists():
        return []
    
    session_file: Optional[Path] = None
    sessions_path = get_openclaw_root() / "agents" / aid / "sessions"
    if session_key:
        index_data = _load_sessions_index_file(sessions_index)
        if index_data:
            index_map = normalize_sessions_index(index_data)
            entry = index_map.get(session_key)
            if entry:
                session_file = resolve_session_jsonl_path(sessions_path, entry)
    
    if not session_file or not session_file.exists():
        session_file = get_latest_session_file(agent_id)
    
    if not session_file:
        return []
    
    turns: List[Dict[str, Any]] = []
    turn_index = 0
    
    with open(session_file, 'r', encoding='utf-8') as f:
        for line in f:
            envelope, msg = parse_session_jsonl_line(line.strip())
            if not envelope or envelope.get('type') != 'message' or msg is None:
                continue
            role = msg.get('role')
            if not role:
                continue

            try:
                turn: Dict[str, Any] = {
                    'turnIndex': turn_index,
                    'role': role,
                    'timestamp': msg.get('timestamp') or envelope.get('timestamp'),
                    'content': [],
                    'usage': msg.get('usage'),
                    'stopReason': msg.get('stopReason'),
                    'toolCalls': [],
                    'toolName': None,
                }
                
                content = msg.get('content', [])
                if isinstance(content, str):
                    content = [{'type': 'text', 'text': content}]
                
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    ct = c.get('type')
                    if ct == 'text':
                        if role == 'toolResult':
                            turn['content'].append({
                                'type': 'toolResult',
                                'content': c.get('text', ''),
                                'status': msg.get('details', {}).get('status'),
                                'error': msg.get('details', {}).get('error'),
                            })
                        else:
                            turn['content'].append({'type': 'text', 'text': c.get('text', '')})
                    elif ct == 'thinking':
                        turn['content'].append({'type': 'thinking', 'text': c.get('thinking', '')})
                    elif ct == 'toolCall':
                        turn['toolCalls'].append({
                            'name': c.get('name'),
                            'arguments': c.get('arguments'),
                            'id': c.get('id'),
                        })
                        turn['toolName'] = c.get('name')
                
                if role == 'toolResult':
                    turn['toolName'] = msg.get('toolName')
                    if not turn['content']:
                        details = msg.get('details', {})
                        turn['content'].append({
                            'type': 'toolResult',
                            'status': details.get('status'),
                            'error': details.get('error'),
                        })
                
                turns.append(turn)
                turn_index += 1

            except (KeyError, TypeError):
                continue
    
    return turns[-limit:] if len(turns) > limit else turns


def get_latest_tool_call(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    获取最近的工具调用（检查是否已完成）

    Returns:
        {'id': str, 'name': str, 'hasResult': bool} or None
    """
    messages = get_recent_messages(agent_id, limit=30)

    # 收集所有 toolCall 和 toolResult
    tool_calls = {}  # id -> {name, hasResult}
    tool_results = set()  # toolCallIds that have results

    for msg in messages:
        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            if isinstance(content, str):
                content = [{'type': 'text', 'text': content}]
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'toolCall':
                    tool_id = c.get('id')
                    tool_name = c.get('name')
                    if tool_id:
                        tool_calls[tool_id] = {'name': tool_name, 'hasResult': False}
        elif msg.get('role') == 'toolResult':
            # toolResult 通过 toolCallId 关联
            tool_call_id = msg.get('toolCallId') or msg.get('tool_call_id')
            if tool_call_id:
                tool_results.add(tool_call_id)

    # 标记已有结果的 toolCall
    for tool_id in tool_calls:
        if tool_id in tool_results:
            tool_calls[tool_id]['hasResult'] = True

    # 返回最后一个未完成的 toolCall
    for tool_id in reversed(list(tool_calls.keys())):
        info = tool_calls[tool_id]
        if not info['hasResult']:
            return {
                'id': tool_id,
                'name': info['name'],
                'hasResult': False
            }

    # 所有 toolCall 都已完成，返回最后一个（表示刚完成）
    if tool_calls:
        last_id = list(tool_calls.keys())[-1]
        return {
            'id': last_id,
            'name': tool_calls[last_id]['name'],
            'hasResult': True
        }

    return None


def has_thinking_block(agent_id: str) -> bool:
    """
    是否处于「当前回合的思考阶段」。
    仅看会话中**最后一条**消息：已完成回合的 assistant 往往在 content 里仍保留 thinking 块，
    若仍按「最近任意 assistant 含 thinking」会长期误判为工作中。
    """
    messages = get_recent_messages(agent_id, limit=24)
    if not messages:
        return False
    last = messages[-1]
    if last.get('role') != 'assistant':
        return False
    # 已结束的一轮通常带 stopReason；此时 content 里的 thinking 只算历史，不算仍在思考
    if last.get('stopReason'):
        return False
    content = last.get('content', [])
    if isinstance(content, str):
        return False
    for c in content:
        if isinstance(c, dict) and c.get('type') == 'thinking':
            return True
    return False


def get_latest_assistant_message(agent_id: str) -> Optional[Dict[str, Any]]:
    """获取最近的 assistant 消息"""
    messages = get_recent_messages(agent_id, limit=10)
    for msg in reversed(messages):
        if msg.get('role') == 'assistant':
            return msg
    return None


def get_recent_messages_with_timestamp(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    获取最近的会话消息（包含时间戳）

    Args:
        agent_id: Agent ID
        limit: 返回消息数量限制

    Returns:
        [{'message': {...}, 'timestamp': int, 'data_timestamp': str}, ...]
        - timestamp: 消息中的时间戳（毫秒）
        - data_timestamp: JSONL 行的 timestamp 字段（ISO 格式字符串）
    """
    session_file = get_latest_session_file(agent_id)
    if not session_file:
        return []

    raw_lines = _read_tail_lines(session_file, max(limit * 5, 500))
    messages = []

    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        env, msg = parse_session_jsonl_line(line)
        if msg is None:
            continue
        messages.append({
            'message': msg,
            'timestamp': msg.get('timestamp', 0),
            'data_timestamp': (env or {}).get('timestamp', ''),
        })

    return messages[-limit:] if len(messages) > limit else messages


def get_pending_tool_call_with_timestamp(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    获取待处理的工具调用（包含时间戳）

    复用 get_latest_tool_call 的匹配逻辑，但返回消息级别的时间戳

    Args:
        agent_id: Agent ID

    Returns:
        {'id': str, 'name': str, 'hasResult': bool, 'timestamp': int} or None
        - timestamp: 工具调用时的时间戳（毫秒）
    """
    messages = get_recent_messages_with_timestamp(agent_id, limit=30)

    tool_calls = {}  # id -> {name, timestamp, hasResult}
    tool_results = set()

    for item in messages:
        msg = item.get('message', {})
        ts = item.get('timestamp', 0)

        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            if isinstance(content, str):
                continue
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'toolCall':
                    tool_id = c.get('id')
                    if tool_id:
                        tool_calls[tool_id] = {
                            'id': tool_id,
                            'name': c.get('name', 'unknown'),
                            'timestamp': ts,
                            'hasResult': False
                        }

        elif msg.get('role') == 'toolResult':
            tool_call_id = msg.get('toolCallId') or msg.get('tool_call_id')
            if tool_call_id:
                tool_results.add(tool_call_id)

    # 标记已有结果的 toolCall
    for tool_id in tool_calls:
        if tool_id in tool_results:
            tool_calls[tool_id]['hasResult'] = True

    # 返回最后一个未完成的 toolCall
    for tool_id in reversed(list(tool_calls.keys())):
        info = tool_calls[tool_id]
        if not info['hasResult']:
            return info

    # 所有 toolCall 都已完成，返回最后一个
    if tool_calls:
        last_id = list(tool_calls.keys())[-1]
        return tool_calls[last_id]

    return None


def get_session_validation_report(
    agent_id: str,
    *,
    relative_session_file: Optional[str] = None,
    auto_repair: Optional[bool] = None,
    include_details: bool = False,
    max_lines: int = 1000,
) -> Dict[str, Any]:
    """Validate session JSONL for an agent; used by GET /api/data/validate."""
    from core.config_fortify import get_fortify_config

    aid = normalize_openclaw_agent_id(agent_id)
    sessions_dir = get_openclaw_root() / "agents" / aid / "sessions"
    sessions_index_path = sessions_dir / "sessions.json"
    cfg = get_fortify_config()
    read_path_policy = {
        "memory_auto_repair_default": cfg.auto_repair_json,
        "disk_write_back_enabled": cfg.auto_repair_write_back,
        "note": "本报告仅校验与统计；读路径不自动写盘，写回仅在显式修复工具中且受 OPENCLAW_AUTO_REPAIR_WB 控制。",
    }

    session_file: Optional[Path] = None
    if relative_session_file and relative_session_file.strip():
        session_file = resolve_validated_session_jsonl(agent_id, relative_session_file)
        if not session_file:
            return {
                "agent_id": agent_id,
                "validation_passed": False,
                "sessions_index_path": str(sessions_index_path)
                if sessions_index_path.exists()
                else None,
                "session_file": None,
                "session_file_query": relative_session_file.strip(),
                "file_integrity": None,
                "read_path_policy": read_path_policy,
                "total_lines": 0,
                "valid_messages": 0,
                "repaired_messages": 0,
                "errors": [
                    {
                        "type": "invalid_session_file",
                        "message": "path not found, not .jsonl, or escapes sessions dir",
                    }
                ],
                "repair_report": {
                    "repaired_count": 0,
                    "repair_success_rate": 1.0,
                    "failed_repairs": [],
                },
            }
    else:
        session_file = get_latest_session_file(agent_id)

    if not session_file:
        return {
            "agent_id": agent_id,
            "validation_passed": True,
            "sessions_index_path": str(sessions_index_path)
            if sessions_index_path.exists()
            else None,
            "session_file": None,
            "session_file_query": None,
            "file_integrity": None,
            "read_path_policy": read_path_policy,
            "total_lines": 0,
            "valid_messages": 0,
            "repaired_messages": 0,
            "errors": [],
            "repair_report": {"repaired_count": 0, "repair_success_rate": 1.0, "failed_repairs": []},
        }

    raw_lines = _read_tail_lines(session_file, max_lines)
    errors: List[Dict[str, Any]] = []
    valid_messages = 0
    repaired_messages = 0
    failed_repairs: List[Dict[str, Any]] = []

    for i, line in enumerate(raw_lines):
        stripped = line.strip()
        if not stripped:
            continue
        env_probe, _ = parse_session_jsonl_line(
            stripped, auto_repair=False, json_strict=False
        )
        if env_probe and env_probe.get("type") != "message":
            continue
        _env_strict, msg_strict = parse_session_jsonl_line(
            stripped, auto_repair=False, json_strict=True
        )
        if msg_strict is not None:
            valid_messages += 1
            continue
        _env_loose, msg_loose = parse_session_jsonl_line(
            stripped,
            auto_repair=auto_repair if auto_repair is not None else True,
            json_strict=False,
        )
        if msg_loose is not None:
            repaired_messages += 1
        else:
            failed_repairs.append({"line_index": i, "reason": "unparseable_or_invalid_schema"})
            if include_details:
                errors.append(
                    {
                        "type": "validation_failed",
                        "line_index_in_tail_window": i,
                        "reason": "unparseable_or_invalid_schema",
                        "sample": stripped[:200],
                    }
                )

    total_non_empty = sum(1 for ln in raw_lines if ln.strip())
    validation_passed = len(failed_repairs) == 0
    denom = repaired_messages + valid_messages
    rate = 1.0 if denom == 0 else repaired_messages / max(denom, 1)

    return {
        "agent_id": agent_id,
        "validation_passed": validation_passed,
        "sessions_index_path": str(sessions_index_path)
        if sessions_index_path.exists()
        else None,
        "session_file": str(session_file.resolve()),
        "session_file_query": relative_session_file.strip() if relative_session_file else None,
        "file_integrity": compute_session_file_integrity(session_file),
        "read_path_policy": read_path_policy,
        "tail_lines_scanned": max_lines,
        "total_lines": total_non_empty,
        "valid_messages": valid_messages,
        "repaired_messages": repaired_messages,
        "errors": errors,
        "repair_report": {
            "repaired_count": repaired_messages,
            "repair_success_rate": rate,
            "failed_repairs": failed_repairs,
        },
    }
