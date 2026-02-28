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
    get_agent_runs,
    get_agent_output_for_run,
    get_agent_files_for_run
)
from data.task_history import merge_with_history
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


def _get_agent_workspace(agent_id: str) -> Optional[str]:
    """从配置获取 Agent 工作区路径"""
    if not agent_id:
        return None
    try:
        from data.config_reader import get_agent_config
        config = get_agent_config(agent_id)
        return config.get('workspace') if config else None
    except Exception:
        return None


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


def _extract_task_summary(task_raw: str) -> str:
    """从完整任务文本提取首行摘要（不截断）"""
    if not task_raw or not task_raw.strip():
        return 'Unknown Task'
    lines = [ln.strip() for ln in task_raw.split('\n') if ln.strip()]
    first = lines[0] if lines else task_raw.strip()
    # 去除 markdown 粗体
    if first.startswith('**') and '**' in first[2:]:
        first = first.split('**', 2)[-1].strip()
    return first


def _extract_task_path(task_raw: str) -> str | None:
    """从任务文本提取项目路径"""
    if not task_raw:
        return None
    import re
    # 匹配 **项目路径：** `path` 或 项目路径：path
    m = re.search(r'\*\*项目路径[：:]\*\*\s*`([^`]+)`', task_raw)
    if m:
        return m.group(1).strip()
    m = re.search(r'项目路径[：:]\s*`?([^`\n]+)`?', task_raw)
    if m:
        return m.group(1).strip()
    return None


def _sanitize_task_display(text: str) -> str:
    """去除任务展示中的 Markdown 符号：** 粗体、路径的 `` 反引号"""
    if not text or not isinstance(text, str):
        return text or ''
    import re
    # 去除 ** 粗体标记
    s = re.sub(r'\*\*', '', text)
    # 去除路径等外层的反引号：`path` -> path
    s = re.sub(r'`([^`]+)`', r'\1', s)
    return s


def _format_error_message(raw: str) -> str:
    """将原始错误信息转为更明确的用户可读描述"""
    if not raw or not isinstance(raw, str):
        return '未知'
    raw = raw.strip().lower()
    mapping = {
        'terminated': '任务被终止（可能是超时或被用户取消）',
        'timeout': '任务执行超时',
        'cancelled': '任务已取消',
        'canceled': '任务已取消',
        'killed': '任务被终止',
        'subagent-error': '子任务执行异常',
        'error': '执行出错',
    }
    for key, desc in mapping.items():
        if key in raw:
            return desc
    return raw.strip() or '未知'


def _run_to_task(run: Dict[str, Any]) -> Dict[str, Any]:
    """将 run 转为任务展示格式"""
    agent_id = parse_agent_id(run.get('childSessionKey', ''))
    outcome = run.get('outcome')
    status = _map_run_status(run)
    task_raw = run.get('task', 'Unknown Task')
    task_name = _extract_task_summary(task_raw)
    task_path = _extract_task_path(task_raw)
    progress = 100 if run.get('endedAt') else 50
    error_msg = None
    if status == 'failed':
        if isinstance(outcome, dict):
            raw_err = outcome.get('error', outcome.get('message', outcome.get('reason', '任务失败')))
            error_msg = _format_error_message(str(raw_err)) if raw_err else '任务失败'
        elif isinstance(outcome, str):
            error_msg = _format_error_message(outcome) if outcome.strip() else '任务失败'
    task_display = task_raw if isinstance(task_raw, str) else str(task_raw)
    task_display = _sanitize_task_display(task_display)
    task_name = _sanitize_task_display(task_name)
    result: Dict[str, Any] = {
        'id': run.get('runId', ''),
        'name': task_name,
        'task': task_display,
        'status': status,
        'progress': progress,
        'startTime': run.get('startedAt'),
        'endTime': run.get('endedAt'),
        'agentId': agent_id,
        'agentName': _get_agent_name(agent_id),
        'agentWorkspace': _get_agent_workspace(agent_id),
        'error': error_msg,
        'childSessionKey': run.get('childSessionKey')
    }
    if task_path:
        result['taskPath'] = task_path
    # 任务成功时，从 session 提取 Agent 输出和生成的文件
    if status == 'completed':
        child_key = run.get('childSessionKey', '')
        if child_key:
            output = get_agent_output_for_run(child_key)
            if output:
                result['output'] = output
            files = get_agent_files_for_run(child_key)
            if files:
                result['generatedFiles'] = files
    return result


@router.get("/tasks")
async def get_tasks():
    """获取任务列表 - 合并 runs.json 与持久化历史，确保已完成任务不丢失"""
    try:
        all_runs = load_subagent_runs()
        all_runs.sort(key=lambda x: x.get('startedAt', 0), reverse=True)

        tasks = merge_with_history(all_runs, _run_to_task)
        # 对历史任务补充缺失字段
        for t in tasks:
            if t.get('status') == 'completed' and t.get('childSessionKey'):
                if not t.get('output'):
                    output = get_agent_output_for_run(t['childSessionKey'])
                    if output:
                        t['output'] = output
                if not t.get('generatedFiles'):
                    files = get_agent_files_for_run(t['childSessionKey'])
                    if files:
                        t['generatedFiles'] = files
            if not t.get('agentWorkspace') and t.get('agentId'):
                t['agentWorkspace'] = _get_agent_workspace(t['agentId'])
        return {'tasks': tasks}
    except Exception as e:
        print(f"Error in get_tasks: {e}")
        import traceback
        traceback.print_exc()
        return {'tasks': []}
