"""
子代理运行读取器 - 读取 subagents/runs.json
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

SUBAGENTS_RUNS_PATH = Path.home() / ".openclaw" / "subagents" / "runs.json"


def load_subagent_runs() -> List[Dict[str, Any]]:
    """加载子代理运行记录
    
    OpenClaw runs.json 格式: {"version": 2, "runs": { runId: record }}
    """
    if not SUBAGENTS_RUNS_PATH.exists():
        return []
    
    with open(SUBAGENTS_RUNS_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    runs = data.get('runs', {})
    if isinstance(runs, dict):
        return list(runs.values())
    return runs if isinstance(runs, list) else []


def get_active_runs() -> List[Dict[str, Any]]:
    """获取活跃的运行（未结束）"""
    runs = load_subagent_runs()
    return [run for run in runs if run.get('endedAt') is None]


def get_agent_runs(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """获取指定 Agent 的运行记录"""
    runs = load_subagent_runs()
    agent_runs = []
    
    for run in runs:
        child_key = run.get('childSessionKey', '')
        if f'agent:{agent_id}:' in child_key:
            agent_runs.append(run)
    
    # 按开始时间倒序
    agent_runs.sort(key=lambda x: x.get('startedAt', 0), reverse=True)
    return agent_runs[:limit]


def is_agent_working(agent_id: str) -> bool:
    """判断 Agent 是否在工作中"""
    active_runs = get_active_runs()
    for run in active_runs:
        child_key = run.get('childSessionKey', '')
        if f'agent:{agent_id}:' in child_key:
            return True
    return False


def get_agent_output_for_run(child_session_key: str, max_chars: int = 10000) -> Optional[str]:
    """
    从子 Agent 的 session 文件中提取最后一次 assistant 消息的文本输出。
    用于任务成功时展示 Agent 的执行结果。
    
    Args:
        child_session_key: 格式 agent:<agentId>:subagent:<uuid>
        max_chars: 最大返回字符数，超出则截断
    
    Returns:
        Agent 的文本输出，若无法获取则返回 None
    """
    if not child_session_key or ':' not in child_session_key:
        return None
    parts = child_session_key.split(':')
    if len(parts) < 2 or parts[0] != 'agent':
        return None
    agent_id = parts[1]
    
    openclaw_path = Path.home() / ".openclaw"
    sessions_index = openclaw_path / "agents" / agent_id / "sessions" / "sessions.json"
    if not sessions_index.exists():
        return None
    
    try:
        with open(sessions_index, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        entry = index_data.get(child_session_key)
        if not entry:
            return None
        session_file = entry.get('sessionFile')
        session_id = entry.get('sessionId')
        if not session_file and not session_id:
            return None
        if not session_file:
            sessions_dir = openclaw_path / "agents" / agent_id / "sessions"
            session_file = str(sessions_dir / f"{session_id}.jsonl")
        
        session_path = Path(session_file)
        if not session_path.exists():
            return None
        
        last_text = None
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get('type') != 'message':
                        continue
                    msg = data.get('message', {})
                    if msg.get('role') != 'assistant':
                        continue
                    content = msg.get('content', [])
                    for c in content:
                        if isinstance(c, dict) and c.get('type') == 'text':
                            text = c.get('text', '')
                            if text and text.strip():
                                last_text = text
                            break
                except (json.JSONDecodeError, KeyError):
                    continue
        
        if not last_text or not last_text.strip():
            return None
        if len(last_text) > max_chars:
            return last_text[:max_chars] + '\n\n...(输出已截断)'
        return last_text
    except Exception as e:
        print(f"get_agent_output_for_run 失败: {e}")
        return None
