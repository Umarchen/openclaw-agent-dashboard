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
