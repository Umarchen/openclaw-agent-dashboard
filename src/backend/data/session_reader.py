"""
会话读取器 - 读取 sessions/*.jsonl 和 sessions.json
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional


from data.config_reader import get_openclaw_root


def get_agent_sessions_path(agent_id: str) -> Optional[Path]:
    """获取 Agent 的 sessions 目录"""
    sessions_path = get_openclaw_root() / "agents" / agent_id / "sessions"
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
        try:
            data = json.loads(line)
            if data.get('type') == 'message':
                messages.append(data.get('message', {}))
                if len(messages) >= limit:
                    break
        except json.JSONDecodeError:
            continue
    return messages[-limit:] if len(messages) > limit else messages


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
    sessions_index = get_openclaw_root() / "agents" / agent_id / "sessions" / "sessions.json"
    if not sessions_index.exists():
        return 0
    
    try:
        with open(sessions_index, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return 0
        max_ts = 0
        for entry in data.values():
            if isinstance(entry, dict):
                ts = entry.get('updatedAt', 0)
                if isinstance(ts, (int, float)) and ts > max_ts:
                    max_ts = int(ts)
        return max_ts
    except (json.JSONDecodeError, IOError):
        return 0


def has_recent_session_activity(agent_id: str, minutes: int = 5) -> bool:
    """检查 Agent 最近 N 分钟内是否有 session 活动"""
    import time
    updated_at = get_session_updated_at(agent_id)
    if not updated_at:
        return False
    cutoff = int(time.time() * 1000) - (minutes * 60 * 1000)
    return updated_at > cutoff


def get_session_turns(agent_id: str, session_key: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """
    解析 jsonl 获取会话轮次，每轮包含 user/assistant/toolResult 及 usage
    返回格式: [{ turnIndex, role, content, usage?, toolCalls?, stopReason?, timestamp }]
    """
    sessions_index = get_openclaw_root() / "agents" / agent_id / "sessions" / "sessions.json"
    if not sessions_index.exists():
        return []
    
    session_file: Optional[Path] = None
    if session_key:
        try:
            with open(sessions_index, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            entry = index_data.get(session_key) if isinstance(index_data, dict) else None
            if entry and isinstance(entry, dict):
                sf = entry.get('sessionFile')
                sid = entry.get('sessionId')
                if sf:
                    session_file = Path(sf)
                elif sid:
                    session_file = get_openclaw_root() / "agents" / agent_id / "sessions" / f"{sid}.jsonl"
        except (json.JSONDecodeError, IOError):
            pass
    
    if not session_file or not session_file.exists():
        session_file = get_latest_session_file(agent_id)
    
    if not session_file:
        return []
    
    turns: List[Dict[str, Any]] = []
    turn_index = 0
    
    with open(session_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if data.get('type') != 'message':
                    continue
                msg = data.get('message', {})
                role = msg.get('role')
                if not role:
                    continue
                
                turn: Dict[str, Any] = {
                    'turnIndex': turn_index,
                    'role': role,
                    'timestamp': msg.get('timestamp') or data.get('timestamp'),
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
                
            except (json.JSONDecodeError, KeyError):
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
    """检查最近消息是否有 thinking 块"""
    messages = get_recent_messages(agent_id, limit=5)
    for msg in reversed(messages):
        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            if isinstance(content, str):
                continue
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
        try:
            data = json.loads(line)
            if data.get('type') == 'message':
                msg = data.get('message', {})
                messages.append({
                    'message': msg,
                    'timestamp': msg.get('timestamp', 0),
                    'data_timestamp': data.get('timestamp', ''),
                })
                if len(messages) >= limit:
                    break
        except json.JSONDecodeError:
            continue

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
