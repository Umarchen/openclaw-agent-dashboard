"""
会话读取器 - 读取 sessions/*.jsonl 和 sessions.json
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional


def _openclaw_home() -> Path:
    """OpenClaw 根目录，优先使用 OPENCLAW_HOME 环境变量"""
    env = os.environ.get("OPENCLAW_HOME")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
    return Path.home() / ".openclaw"


OPENCLAW_DIR = _openclaw_home()


def get_agent_sessions_path(agent_id: str) -> Optional[Path]:
    """获取 Agent 的 sessions 目录"""
    sessions_path = OPENCLAW_DIR / f"agents/{agent_id}/sessions"
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


def get_recent_messages(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """获取最近的会话消息"""
    session_file = get_latest_session_file(agent_id)
    if not session_file:
        return []
    
    messages = []
    with open(session_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if data.get('type') == 'message':
                    messages.append(data.get('message', {}))
            except json.JSONDecodeError:
                continue
    
    # 只取最后 N 条
    return messages[-limit:]


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
    sessions_index = OPENCLAW_DIR / f"agents/{agent_id}/sessions/sessions.json"
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
    sessions_index = OPENCLAW_DIR / f"agents/{agent_id}/sessions/sessions.json"
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
                    session_file = OPENCLAW_DIR / f"agents/{agent_id}/sessions/{sid}.jsonl"
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
