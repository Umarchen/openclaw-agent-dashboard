"""
Subagent API 路由
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json
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


def _get_session_message_count(child_session_key: str) -> int:
    """
    从子 Agent 的 session 文件中统计消息数量。
    用于估算任务进度。

    Args:
        child_session_key: 格式 agent:<agentId>:subagent:<uuid>

    Returns:
        消息数量，若无法获取则返回 0
    """
    if not child_session_key or ':' not in child_session_key:
        return 0
    parts = child_session_key.split(':')
    if len(parts) < 2 or parts[0] != 'agent':
        return 0
    agent_id = parts[1]

    try:
        from data.config_reader import get_openclaw_root
        openclaw_path = get_openclaw_root()
        sessions_index = openclaw_path / "agents" / agent_id / "sessions" / "sessions.json"
        if not sessions_index.exists():
            return 0

        with open(sessions_index, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        entry = index_data.get(child_session_key)
        if not entry:
            return 0
        session_file = entry.get('sessionFile')
        session_id = entry.get('sessionId')
        if not session_file and not session_id:
            return 0
        if not session_file:
            sessions_dir = openclaw_path / "agents" / agent_id / "sessions"
            session_file = str(sessions_dir / f"{session_id}.jsonl")

        session_path = Path(session_file)
        if not session_path.exists():
            return 0

        count = 0
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get('type') == 'message':
                        count += 1
                except json.JSONDecodeError:
                    continue
        return count
    except Exception as e:
        print(f"_get_session_message_count 失败: {e}")
        return 0


def _calculate_progress(run: Dict[str, Any]) -> int:
    """
    计算任务的真实进度（0-100）。

    进度估算逻辑：
    - 已完成任务: 100%
    - 运行中任务: 基于会话消息数量估算
      - 0-5 条消息: 20%
      - 6-15 条消息: 40%
      - 16-30 条消息: 60%
      - 31+ 条消息: 80%
      - 最大 80%（运行中的任务不超过 80%）

    Args:
        run: 运行记录

    Returns:
        进度百分比 (0-100)
    """
    # 已完成任务直接返回 100
    if run.get('endedAt'):
        return 100

    # 运行中任务，基于消息数量估算
    child_key = run.get('childSessionKey', '')
    if not child_key:
        return 10  # 无法获取 session 时，给一个基础进度

    msg_count = _get_session_message_count(child_key)

    if msg_count <= 5:
        return 20
    elif msg_count <= 15:
        return 40
    elif msg_count <= 30:
        return 60
    else:
        return 80


def _extract_subtasks_from_session(child_session_key: str) -> List[Dict[str, Any]]:
    """
    从子 Agent 的 session 文件中提取嵌套的子任务（subagent 调用）。

    Args:
        child_session_key: 格式 agent:<agentId>:subagent:<uuid>

    Returns:
        子任务列表，每个包含: {task, agentId, status}
    """
    if not child_session_key or ':' not in child_session_key:
        return []
    parts = child_session_key.split(':')
    if len(parts) < 2 or parts[0] != 'agent':
        return []
    agent_id = parts[1]

    try:
        from data.config_reader import get_openclaw_root
        openclaw_path = get_openclaw_root()
        sessions_index = openclaw_path / "agents" / agent_id / "sessions" / "sessions.json"
        if not sessions_index.exists():
            return []

        with open(sessions_index, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        entry = index_data.get(child_session_key)
        if not entry:
            return []
        session_file = entry.get('sessionFile')
        session_id = entry.get('sessionId')
        if not session_file and not session_id:
            return []
        if not session_file:
            sessions_dir = openclaw_path / "agents" / agent_id / "sessions"
            session_file = str(sessions_dir / f"{session_id}.jsonl")

        session_path = Path(session_file)
        if not session_path.exists():
            return []

        subtasks: List[Dict[str, Any]] = []
        seen_tasks = set()

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
                        if not isinstance(c, dict) or c.get('type') != 'toolCall':
                            continue
                        name = c.get('name', '')
                        if name not in ('subagent', 'delegate', 'spawn'):
                            continue
                        args = c.get('arguments', {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                continue
                        # 提取子任务信息
                        task_desc = args.get('task') or args.get('prompt') or args.get('instruction', '')
                        sub_agent_id = args.get('agentId') or args.get('agent') or args.get('agent_id', '')
                        if task_desc and task_desc not in seen_tasks:
                            seen_tasks.add(task_desc)
                            subtasks.append({
                                'task': task_desc[:200] if len(task_desc) > 200 else task_desc,
                                'agentId': sub_agent_id,
                                'status': 'unknown'  # 无法从 session 确定状态
                            })
                except (json.JSONDecodeError, KeyError):
                    continue

        return subtasks[:5]  # 最多返回 5 个子任务
    except Exception as e:
        print(f"_extract_subtasks_from_session 失败: {e}")
        return []


def _run_to_task(run: Dict[str, Any]) -> Dict[str, Any]:
    """将 run 转为任务展示格式"""
    agent_id = parse_agent_id(run.get('childSessionKey', ''))
    outcome = run.get('outcome')
    status = _map_run_status(run)
    task_raw = run.get('task', 'Unknown Task')
    task_name = _extract_task_summary(task_raw)
    task_path = _extract_task_path(task_raw)
    progress = _calculate_progress(run)
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
    # 从 session 提取子任务（嵌套 subagent 调用）
    child_key = run.get('childSessionKey', '')
    if child_key:
        subtasks = _extract_subtasks_from_session(child_key)
        if subtasks:
            result['subtasks'] = subtasks
    # 任务成功时，从 session 提取 Agent 输出和生成的文件
    if status == 'completed' and child_key:
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


def _extract_timeline_from_session(child_session_key: str) -> List[Dict[str, Any]]:
    """
    从 session 文件中提取任务执行时间线。

    Args:
        child_session_key: 格式 agent:<agentId>:subagent:<uuid>

    Returns:
        时间线事件列表，每个包含: {time, type, description}
    """
    if not child_session_key or ':' not in child_session_key:
        return []
    parts = child_session_key.split(':')
    if len(parts) < 2 or parts[0] != 'agent':
        return []
    agent_id = parts[1]

    try:
        from data.config_reader import get_openclaw_root
        openclaw_path = get_openclaw_root()
        sessions_index = openclaw_path / "agents" / agent_id / "sessions" / "sessions.json"
        if not sessions_index.exists():
            return []

        with open(sessions_index, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        entry = index_data.get(child_session_key)
        if not entry:
            return []
        session_file = entry.get('sessionFile')
        session_id = entry.get('sessionId')
        if not session_file and not session_id:
            return []
        if not session_file:
            sessions_dir = openclaw_path / "agents" / agent_id / "sessions"
            session_file = str(sessions_dir / f"{session_id}.jsonl")

        session_path = Path(session_file)
        if not session_path.exists():
            return []

        timeline: List[Dict[str, Any]] = []
        event_count = 0
        max_events = 50  # 限制最大事件数

        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                if event_count >= max_events:
                    break
                try:
                    data = json.loads(line)
                    ts = data.get('timestamp')
                    # 确保 ts 是整数毫秒时间戳
                    if isinstance(ts, str):
                        # ISO 格式转毫秒时间戳
                        try:
                            from datetime import datetime
                            # 处理 ISO 格式：2026-03-07T04:07:25.262Z
                            if 'T' in ts:
                                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                ts = int(dt.timestamp() * 1000)
                            else:
                                ts = int(ts)
                        except (ValueError, TypeError):
                            ts = 0
                    elif isinstance(ts, (int, float)):
                        ts = int(ts)
                    else:
                        ts = 0

                    if data.get('type') == 'message':
                        msg = data.get('message', {})
                        role = msg.get('role', '')
                        content = msg.get('content', [])

                        if role == 'user':
                            # 用户消息（任务开始）
                            for c in content:
                                if isinstance(c, dict) and c.get('type') == 'text':
                                    text = c.get('text', '')[:100]
                                    timeline.append({
                                        'time': ts,
                                        'type': 'start',
                                        'description': f'收到任务: {text}...' if len(c.get('text', '')) > 100 else f'收到任务: {text}'
                                    })
                                    event_count += 1
                                    break

                        elif role == 'assistant':
                            # 助手响应中的工具调用
                            for c in content:
                                if not isinstance(c, dict):
                                    continue
                                if c.get('type') == 'toolCall':
                                    tool_name = c.get('name', 'unknown')
                                    args = c.get('arguments', {})
                                    if isinstance(args, str):
                                        try:
                                            args = json.loads(args)
                                        except json.JSONDecodeError:
                                            args = {}

                                    # 生成描述
                                    desc = _describe_tool_call(tool_name, args)
                                    timeline.append({
                                        'time': ts,
                                        'type': 'tool',
                                        'tool': tool_name,
                                        'description': desc
                                    })
                                    event_count += 1

                                elif c.get('type') == 'text':
                                    # 文本响应（可能是最终答案）
                                    text = c.get('text', '')
                                    if text.strip() and len(text) > 50:
                                        # 简单判断是否是最终答案
                                        keywords = ['完成', '成功', 'finished', 'done', 'result', '总结']
                                        if any(kw in text.lower() for kw in keywords):
                                            timeline.append({
                                                'time': ts,
                                                'type': 'response',
                                                'description': f'输出结果 ({len(text)} 字符)'
                                            })
                                            event_count += 1

                except (json.JSONDecodeError, KeyError):
                    continue

        return timeline
    except Exception as e:
        print(f"_extract_timeline_from_session 失败: {e}")
        return []


def _describe_tool_call(tool_name: str, args: Dict[str, Any]) -> str:
    """生成工具调用的可读描述"""
    tool_descriptions = {
        'read': '读取文件',
        'write': '写入文件',
        'edit': '编辑文件',
        'bash': '执行命令',
        'grep': '搜索内容',
        'glob': '查找文件',
        'webfetch': '获取网页',
        'websearch': '网络搜索',
        'subagent': '派发子任务',
        'delegate': '委托任务',
    }

    base_desc = tool_descriptions.get(tool_name.lower(), f'调用 {tool_name}')

    # 添加更多上下文
    if tool_name.lower() in ('read', 'write', 'edit'):
        path = args.get('path') or args.get('file_path', '')
        if path:
            filename = Path(path).name if isinstance(path, str) else str(path)
            return f'{base_desc}: {filename}'
    elif tool_name.lower() == 'bash':
        cmd = args.get('command', '') or args.get('cmd', '')
        if cmd:
            cmd_short = cmd[:50] + '...' if len(cmd) > 50 else cmd
            return f'{base_desc}: {cmd_short}'
    elif tool_name.lower() in ('subagent', 'delegate'):
        task = args.get('task', '') or args.get('prompt', '')
        if task:
            task_short = task[:50] + '...' if len(task) > 50 else task
            return f'{base_desc}: {task_short}'

    return base_desc


@router.get("/tasks/{run_id}/timeline")
async def get_task_timeline(run_id: str):
    """
    获取任务执行时间线。

    Args:
        run_id: 任务运行 ID

    Returns:
        时间线事件列表
    """
    try:
        # 从 runs.json 查找对应的 session key
        all_runs = load_subagent_runs()
        target_run = None
        for run in all_runs:
            if run.get('runId') == run_id:
                target_run = run
                break

        if not target_run:
            # 尝试从历史记录查找
            from data.task_history import load_task_history
            history = load_task_history()
            for record in history:
                if record.get('id') == run_id:
                    target_run = record
                    break

        if not target_run:
            return {'timeline': [], 'error': 'Task not found'}

        child_key = target_run.get('childSessionKey', '')
        if not child_key:
            return {'timeline': [], 'error': 'No session key'}

        timeline = _extract_timeline_from_session(child_key)

        # 添加任务开始和结束事件
        # 兼容两种字段名：startedAt (runs.json) 和 startTime (task_history)
        started_at = target_run.get('startedAt') or target_run.get('startTime')
        ended_at = target_run.get('endedAt') or target_run.get('endTime')
        outcome = target_run.get('outcome')

        if started_at:
            timeline.insert(0, {
                'time': started_at,
                'type': 'created',
                'description': '任务创建'
            })

        if ended_at:
            if isinstance(outcome, dict) and outcome.get('status') == 'ok':
                end_type = 'completed'
                end_desc = '任务完成'
            elif isinstance(outcome, dict) and outcome.get('status') in ('error', 'failed'):
                end_type = 'failed'
                err_msg = outcome.get('error') or outcome.get('message') or '任务失败'
                end_desc = f'任务失败: {err_msg}'
            elif isinstance(outcome, str) and outcome.lower() in ('error', 'failed'):
                end_type = 'failed'
                end_desc = f'任务失败: {outcome}'
            else:
                end_type = 'completed'
                end_desc = '任务结束'

            timeline.append({
                'time': ended_at,
                'type': end_type,
                'description': end_desc
            })

        # 按时间排序（确保 time 是数字）
        def get_sort_time(x):
            t = x.get('time', 0)
            if isinstance(t, (int, float)):
                return int(t)
            elif isinstance(t, str):
                try:
                    return int(t)
                except ValueError:
                    return 0
            return 0
        timeline.sort(key=get_sort_time)

        return {'timeline': timeline, 'runId': run_id}
    except Exception as e:
        print(f"Error in get_task_timeline: {e}")
        import traceback
        traceback.print_exc()
        return {'timeline': [], 'error': str(e)}
