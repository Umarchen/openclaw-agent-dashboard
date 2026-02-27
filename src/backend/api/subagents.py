"""
Subagent API 路由
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from data.subagent_reader import (
    load_subagent_runs,
    get_active_runs,
    get_agent_runs
)
import time

router = APIRouter()


class SubagentRun(BaseModel):
    runId: str
    agentId: str
    task: str
    startedAt: int
    startedAtFormatted: str
    endedAt: Optional[int] = None
    endedAtFormatted: Optional[str] = None
    outcome: Optional[str] = None
    runtime: Optional[str] = None
    totalTokens: Optional[int] = None


def format_timestamp(timestamp: int) -> str:
    """格式化时间戳"""
    if not timestamp:
        return ''
    dt = time.localtime(timestamp / 1000)
    return time.strftime('%Y-%m-%d %H:%M:%S', dt)


def calculate_runtime(started_at: int, ended_at: Optional[int]) -> str:
    """计算运行时长"""
    end = ended_at if ended_at else int(time.time() * 1000)
    diff_seconds = (end - started_at) / 1000

    if diff_seconds < 60:
        return f"{int(diff_seconds)}秒"
    elif diff_seconds < 3600:
        return f"{int(diff_seconds / 60)}分钟"
    else:
        return f"{int(diff_seconds / 3600)}小时"


def parse_agent_id(child_key: str) -> str:
    """从 childSessionKey 解析 agentId"""
    # 格式: agent:devops-agent:subagent:uuid
    parts = child_key.split(':')
    if len(parts) >= 2 and parts[0] == 'agent':
        return parts[1]
    return ''


def extract_outcome(outcome: Any) -> Optional[str]:
    """提取 outcome 字符串"""
    if isinstance(outcome, str):
        return outcome
    if isinstance(outcome, dict):
        return outcome.get('status')
    return None


@router.get("/subagents")
async def get_subagents():
    """获取当前子代理运行（活跃 + 最近完成）"""
    try:
        all_runs = load_subagent_runs()

        # 按开始时间倒序，取前20个
        all_runs.sort(key=lambda x: x.get('startedAt', 0), reverse=True)
        recent_runs = all_runs[:20]

        result = []
        for run in recent_runs:
            agent_id = parse_agent_id(run.get('childSessionKey', ''))
            outcome = run.get('outcome')

            result.append({
                'runId': run.get('runId', ''),
                'agentId': agent_id,
                'task': run.get('task', ''),
                'startedAt': run.get('startedAt', 0),
                'startedAtFormatted': format_timestamp(run.get('startedAt', 0)),
                'endedAt': run.get('endedAt'),
                'endedAtFormatted': format_timestamp(run.get('endedAt')) if run.get('endedAt') else None,
                'outcome': extract_outcome(outcome),
                'runtime': calculate_runtime(
                    run.get('startedAt', 0),
                    run.get('endedAt')
                ),
                'totalTokens': run.get('totalTokens')
            })

        return result
    except Exception as e:
        print(f"Error in get_subagents: {e}")
        import traceback
        traceback.print_exc()
        return []


@router.get("/subagents/active")
async def get_active_subagents():
    """获取活跃的子代理运行"""
    try:
        active_runs = get_active_runs()

        result = []
        for run in active_runs:
            agent_id = parse_agent_id(run.get('childSessionKey', ''))

            result.append({
                'runId': run.get('runId', ''),
                'agentId': agent_id,
                'task': run.get('task', ''),
                'startedAt': run.get('startedAt', 0),
                'startedAtFormatted': format_timestamp(run.get('startedAt', 0)),
                'endedAt': None,
                'endedAtFormatted': None,
                'outcome': None,
                'runtime': calculate_runtime(run.get('startedAt', 0), None),
                'totalTokens': run.get('totalTokens')
            })

        return result
    except Exception as e:
        print(f"Error in get_active_subagents: {e}")
        return []


def _get_agent_name(agent_id: str) -> str:
    """从配置获取 Agent 显示名称"""
    try:
        from data.config_reader import get_agent_config
        config = get_agent_config(agent_id)
        return config.get('name', agent_id) if config else agent_id
    except Exception:
        return agent_id


def _map_run_status(run: Dict[str, Any]) -> str:
    """映射 run 状态为任务状态: pending/running/completed/failed"""
    ended_at = run.get('endedAt')
    if ended_at is None:
        return 'running'  # 执行中

    outcome = run.get('outcome')
    if isinstance(outcome, dict):
        status = outcome.get('status', '')
        if status == 'ok':
            return 'completed'
        if status in ('error', 'failed'):
            return 'failed'
    elif isinstance(outcome, str) and outcome.lower() in ('error', 'failed'):
        return 'failed'

    return 'completed'


@router.get("/tasks")
async def get_tasks():
    """获取任务列表 - 符合 PRD 任务状态展示格式 (待分配/分配中/执行中/已完成/失败)"""
    try:
        all_runs = load_subagent_runs()
        all_runs.sort(key=lambda x: x.get('startedAt', 0), reverse=True)
        recent_runs = all_runs[:50]

        tasks = []
        for run in recent_runs:
            agent_id = parse_agent_id(run.get('childSessionKey', ''))
            outcome = run.get('outcome')

            status = _map_run_status(run)
            task_name = run.get('task', 'Unknown Task')
            if len(task_name) > 100:
                task_name = task_name[:100] + '...'

            # 进度：运行中默认 50%，已完成 100%
            progress = 100 if run.get('endedAt') else 50

            error_msg = None
            if isinstance(outcome, dict) and outcome.get('status') in ('error', 'failed'):
                error_msg = outcome.get('error', outcome.get('message', '任务失败'))

            tasks.append({
                'id': run.get('runId', ''),
                'name': task_name,
                'status': status,
                'progress': progress,
                'startTime': run.get('startedAt'),
                'endTime': run.get('endedAt'),
                'agentId': agent_id,
                'agentName': _get_agent_name(agent_id),
                'error': error_msg
            })

        return {'tasks': tasks}
    except Exception as e:
        print(f"Error in get_tasks: {e}")
        import traceback
        traceback.print_exc()
        return {'tasks': []}
