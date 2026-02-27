"""
会话读取器 - 读取 sessions/*.jsonl
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

OPENCLAW_DIR = Path.home() / ".openclaw"


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
    error_msg_lower = error_msg.lower()
    
    if '429' in error_msg or 'rate limit' in error_msg_lower:
        return 'rate-limit'
    elif 'token' in error_msg_lower or 'context' in error_msg_lower:
        return 'token-limit'
    elif 'timeout' in error_msg_lower or '超时' in error_msg_lower:
        return 'timeout'
    else:
        return 'unknown'
