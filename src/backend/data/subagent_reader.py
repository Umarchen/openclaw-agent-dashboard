"""
子代理运行读取器 - 读取 subagents/runs.json
"""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from data.config_reader import get_openclaw_root, normalize_openclaw_agent_id
from data.session_reader import (
    normalize_sessions_index,
    resolve_session_jsonl_path,
    _load_sessions_index_file,
)
from core.config_fortify import get_fortify_config
from core.error_handler import record_error
from core.schemas.base import SchemaValidator
from core.schemas.subagent_schema import subagent_runs_root_schema
from utils.data_repair import parse_session_jsonl_line


def load_subagent_runs() -> List[Dict[str, Any]]:
    """加载子代理运行记录
    
    OpenClaw runs.json 格式: {"version": 2, "runs": { runId: record }}
    """
    runs_path = get_openclaw_root() / "subagents" / "runs.json"
    if not runs_path.exists():
        return []

    try:
        with open(runs_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        record_error("parsing-error", str(e), "subagent_runs")
        return []

    if not isinstance(data, dict):
        return []

    cfg = get_fortify_config()
    vr = SchemaValidator(subagent_runs_root_schema, strict=cfg.json_strict).validate(data)
    if not vr.is_valid:
        record_error("validation-error", vr.error_message, "subagent_runs")
        if cfg.json_strict:
            return []

    runs = data.get('runs', {})
    if isinstance(runs, dict):
        out: List[Dict[str, Any]] = []
        for run_id, rec in runs.items():
            if not isinstance(rec, dict):
                continue
            merged = dict(rec)
            if not merged.get('runId'):
                merged['runId'] = run_id
            out.append(merged)
        return out
    return runs if isinstance(runs, list) else []


def get_active_runs() -> List[Dict[str, Any]]:
    """获取活跃的运行（未结束）"""
    runs = load_subagent_runs()
    return [run for run in runs if run.get('endedAt') is None]


def get_agent_runs(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """获取指定 Agent 的运行记录"""
    runs = load_subagent_runs()
    agent_runs = []
    prefix = f"agent:{normalize_openclaw_agent_id(agent_id)}:"
    for run in runs:
        child_key = run.get('childSessionKey', '')
        if prefix in child_key:
            agent_runs.append(run)
    
    # 按开始时间倒序
    agent_runs.sort(key=lambda x: x.get('startedAt', 0), reverse=True)
    return agent_runs[:limit]


def is_agent_working(agent_id: str) -> bool:
    """
    判断 Agent 是否在工作中
    - 作为执行者：childSessionKey 包含 agent:{agent_id}:
    - 作为派发者：requesterSessionKey 包含 agent:{agent_id}:（主 Agent 等待子 Agent 完成）
    """
    active_runs = get_active_runs()
    prefix = f"agent:{normalize_openclaw_agent_id(agent_id)}:"
    for run in active_runs:
        child_key = run.get('childSessionKey', '')
        requester_key = run.get('requesterSessionKey', '')
        if prefix in child_key:
            return True
        if prefix in requester_key:
            return True
    return False


def get_waiting_child_agent(agent_id: str) -> Optional[str]:
    """
    获取正在等待的子代理名称

    当 Agent 作为 requester 派发任务给子 Agent 时，
    该 Agent 正在等待子 Agent 完成任务。

    Args:
        agent_id: Agent ID

    Returns:
        子代理 ID，如果没有则返回 None
    """
    active_runs = get_active_runs()
    prefix = f"agent:{normalize_openclaw_agent_id(agent_id)}:"
    for run in active_runs:
        requester_key = run.get('requesterSessionKey', '')
        # 检查这个 agent 是否是 requester（即它在等待子 agent）
        if prefix in requester_key:
            child_key = run.get('childSessionKey', '')
            if child_key and ':' in child_key:
                parts = child_key.split(':')
                if len(parts) >= 2 and parts[0] == 'agent':
                    return parts[1]
    return None


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
    agent_id = normalize_openclaw_agent_id(parts[1])
    
    openclaw_path = get_openclaw_root()
    sessions_index = openclaw_path / "agents" / agent_id / "sessions" / "sessions.json"
    if not sessions_index.exists():
        return None
    
    try:
        index_data = _load_sessions_index_file(sessions_index)
        if not index_data:
            return None
        index_map = normalize_sessions_index(index_data)
        entry = index_map.get(child_session_key)
        if not entry:
            return None
        sessions_dir = openclaw_path / "agents" / agent_id / "sessions"
        session_path = resolve_session_jsonl_path(sessions_dir, entry)
        if not session_path:
            return None
        
        last_text = None
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                envelope, msg = parse_session_jsonl_line(line)
                if not envelope or envelope.get('type') != 'message' or msg is None:
                    continue
                if msg.get('role') != 'assistant':
                    continue
                content = msg.get('content', [])
                for c in content:
                    if isinstance(c, dict) and c.get('type') == 'text':
                        text = c.get('text', '')
                        if text and text.strip():
                            last_text = text
                        break
        
        if not last_text or not last_text.strip():
            return None
        if len(last_text) > max_chars:
            return last_text[:max_chars] + '\n\n...(输出已截断)'
        return last_text
    except Exception as e:
        record_error("io-error", str(e), "subagent_reader:get_agent_output_for_run", exc=e)
        return None


def get_agent_files_for_run(child_session_key: str) -> List[str]:
    """
    从子 Agent 的 session 中提取本次任务生成/修改的文件路径。
    解析 write、edit 等工具调用中的 path 参数。
    
    Returns:
        去重后的文件路径列表
    """
    if not child_session_key or ':' not in child_session_key:
        return []
    parts = child_session_key.split(':')
    if len(parts) < 2 or parts[0] != 'agent':
        return []
    agent_id = normalize_openclaw_agent_id(parts[1])
    
    openclaw_path = get_openclaw_root()
    sessions_index = openclaw_path / "agents" / agent_id / "sessions" / "sessions.json"
    if not sessions_index.exists():
        return []
    
    try:
        index_data = _load_sessions_index_file(sessions_index)
        if not index_data:
            return []
        index_map = normalize_sessions_index(index_data)
        entry = index_map.get(child_session_key)
        if not entry:
            return []
        sessions_dir = openclaw_path / "agents" / agent_id / "sessions"
        session_path = resolve_session_jsonl_path(sessions_dir, entry)
        if not session_path:
            return []
        
        file_paths: List[str] = []
        file_tools = ('write', 'edit')
        
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                envelope, msg = parse_session_jsonl_line(line)
                if not envelope or envelope.get('type') != 'message' or msg is None:
                    continue
                if msg.get('role') != 'assistant':
                    continue
                content = msg.get('content', [])
                for c in content:
                    if not isinstance(c, dict) or c.get('type') != 'toolCall':
                        continue
                    name = c.get('name', '')
                    if name not in file_tools:
                        continue
                    args = c.get('arguments', {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            continue
                    path = args.get('path') or args.get('file_path')
                    if path and isinstance(path, str) and path.strip():
                        file_paths.append(path.strip())
        
        # 去重并保持顺序
        seen = set()
        result = []
        for p in file_paths:
            if p not in seen:
                seen.add(p)
                result.append(p)
        return result
    except Exception as e:
        record_error("io-error", str(e), "subagent_reader:get_agent_files_for_run", exc=e)
        return []
