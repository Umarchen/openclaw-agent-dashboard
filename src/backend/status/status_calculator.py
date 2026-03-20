"""
状态计算器 - 计算 Agent 状态
集成缓存机制，提升状态计算性能
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import logging
import time
from typing import Literal, Dict, Any, List, Optional
from data.config_reader import get_agents_list, get_agent_config
from data.subagent_reader import is_agent_working, get_agent_runs
from data.session_reader import (
    has_recent_errors,
    get_last_error,
    has_recent_session_activity,
    get_session_updated_at,
    get_pending_tool_call_with_timestamp,
)

# 导入缓存和变化跟踪
from .status_cache import get_cache
from .change_tracker import get_tracker

logger = logging.getLogger(__name__)


AgentStatus = Literal['idle', 'working', 'down']


def calculate_agent_status(agent_id: str, use_cache: bool = True) -> AgentStatus:
    """
    计算 Agent 状态（基于 runs.json + sessions.json）
    
    优先级:
    1. 异常 (down) - 最近5分钟有 stopReason=error
    2. 工作中 (working) - 有活跃 subagent run 或 session 正在处理（最近5分钟有活动）
    3. 空闲 (idle) - 无活跃 run 且最近5分钟无 session 活动
    
    Args:
        agent_id: Agent ID
        use_cache: 是否使用缓存（默认 True）
    
    Returns:
        Agent 状态
    """
    # 先查缓存
    if use_cache:
        cache = get_cache()
        cached = cache.get(agent_id)
        if cached and 'status' in cached:
            return cached['status']
    
    # 重新计算
    # 检查异常
    if has_recent_errors(agent_id, minutes=5):
        status = 'down'
    # 检查工作中：subagent run 未结束，或 session 最近有活动
    elif is_agent_working(agent_id):
        status = 'working'
    elif has_recent_session_activity(agent_id, minutes=2):
        status = 'working'
    else:
        # 默认空闲
        status = 'idle'
    
    # 更新缓存（只缓存状态）
    if use_cache:
        cache = get_cache()
        cache.set(agent_id, {'status': status})
    
    return status


def get_agents_with_status() -> list:
    """获取所有 Agent 及其状态"""
    agents = get_agents_list()
    result = []
    
    for agent in agents:
        agent_id = agent.get('id')
        status = calculate_agent_status(agent_id)
        
        # 获取当前任务
        current_task = get_current_task(agent_id)
        
        # 获取最后活跃时间
        last_active = get_last_active_time(agent_id)
        
        # 获取错误信息
        last_error = get_last_error(agent_id) if status == 'down' else None
        
        result.append({
            'id': agent_id,
            'name': agent.get('name'),
            'role': agent.get('name'),
            'status': status,
            'currentTask': current_task,
            'lastActiveAt': last_active,
            'error': last_error
        })
    
    return result


def get_current_task(agent_id: str) -> str:
    """获取 Agent 当前任务"""
    runs = get_agent_runs(agent_id, limit=1)
    if not runs:
        return ''

    run = runs[0]
    task = run.get('task', '')

    # 截取前60个字符（统一长度）
    if len(task) > 60:
        task = task[:57] + '...'

    return task


def get_last_active_time(agent_id: str) -> int:
    """获取 Agent 最后活跃时间（runs 或 sessions.json updatedAt）"""
    from data.session_reader import get_session_updated_at
    
    runs = get_agent_runs(agent_id, limit=1)
    run_ts = 0
    if runs:
        run = runs[0]
        run_ts = run.get('endedAt') or run.get('startedAt', 0)
    
    session_ts = get_session_updated_at(agent_id)
    return max(run_ts, session_ts)


def format_last_active(timestamp: int) -> str:
    """格式化最后活跃时间为相对时间"""
    if not timestamp:
        return '未知'
    
    now = int(time.time() * 1000)
    diff_seconds = (now - timestamp) / 1000
    
    if diff_seconds < 60:
        return f"{int(diff_seconds)}秒前"
    elif diff_seconds < 3600:
        return f"{int(diff_seconds / 60)}分钟前"
    elif diff_seconds < 86400:
        return f"{int(diff_seconds / 3600)}小时前"
    else:
        return f"{int(diff_seconds / 86400)}天前"


def get_detailed_status(agent_id: str) -> dict:
    """
    获取 Agent 详细状态（包含子状态和当前动作）

    Returns:
        {
            'status': 'idle' | 'working' | 'down',
            'subStatus': 'thinking' | 'tool_executing' | 'waiting_llm' | 'waiting_child' | None,
            'currentAction': '思考中...' | '执行: Read' | '等待: xxx' | None,
            'toolName': str | None,
            'waitingFor': str | None
        }
    """
    from data.session_reader import get_latest_tool_call, has_thinking_block
    from data.subagent_reader import get_active_runs

    base_status = calculate_agent_status(agent_id)

    # 非 working 状态不返回子状态
    if base_status != 'working':
        return {
            'status': base_status,
            'subStatus': None,
            'currentAction': None,
            'toolName': None,
            'waitingFor': None
        }

    # 检查是否在执行工具（最近有 toolCall 且无对应 toolResult）
    tool_call = get_latest_tool_call(agent_id)
    if tool_call and not tool_call.get('hasResult'):
        tool_name = tool_call.get('name', 'unknown')
        return {
            'status': 'working',
            'subStatus': 'tool_executing',
            'currentAction': f'执行: {tool_name}',
            'toolName': tool_name,
            'waitingFor': None
        }

    # 检查是否有 thinking 块
    if has_thinking_block(agent_id):
        return {
            'status': 'working',
            'subStatus': 'thinking',
            'currentAction': '思考中...',
            'toolName': None,
            'waitingFor': None
        }

    # 检查是否在等待子代理
    for run in get_active_runs():
        requester_key = run.get('requesterSessionKey', '')
        # 如果这个 agent 是 requester，说明它在等待子 agent
        if f'agent:{agent_id}:' in requester_key:
            child_key = run.get('childSessionKey', '')
            child_agent_id = _parse_agent_id_from_key(child_key)
            if child_agent_id:
                return {
                    'status': 'working',
                    'subStatus': 'waiting_child',
                    'currentAction': f'等待: {child_agent_id}',
                    'toolName': None,
                    'waitingFor': child_agent_id
                }

    # 默认：等待模型响应
    return {
        'status': 'working',
        'subStatus': 'waiting_llm',
        'currentAction': '等待模型响应',
        'toolName': None,
        'waitingFor': None
    }


def _parse_agent_id_from_key(session_key: str) -> str:
    """从 sessionKey 解析 agentId"""
    parts = (session_key or '').split(':')
    if len(parts) >= 2 and parts[0] == 'agent':
        return parts[1]
    return ''


def get_display_status(agent_id: str) -> Dict[str, Any]:
    """
    获取用于前端显示的状态（基于时间阈值）

    核心原则：
    1. 不追求精确：快速动作无法精确捕获
    2. 关注异常：只显示超过阈值的"卡顿"状态
    3. 提供上下文：显示等待对象、持续时间
    4. 减少闪烁：用"处理中..."作为过渡状态

    Args:
        agent_id: Agent ID

    Returns:
        {
            'status': 'idle' | 'working',
            'display': str,      # 显示文本
            'duration': int,     # 持续时间（秒）
            'alert': bool,       # 是否需要警告
        }
    """
    from data.subagent_reader import get_waiting_child_agent

    # 无任务
    if not is_agent_working(agent_id):
        return {'status': 'idle', 'display': '空闲', 'duration': 0, 'alert': False}

    # 计算空闲时间（使用 sessions.json 的 updatedAt）
    last_activity = get_session_updated_at(agent_id)
    now = int(time.time() * 1000)
    idle_seconds = int((now - last_activity) / 1000) if last_activity else 0

    # 检查等待子代理（阈值：3秒）
    waiting_for = get_waiting_child_agent(agent_id)
    if waiting_for and idle_seconds > 3:
        logger.debug(f"[{agent_id}] Waiting for child: {waiting_for}, duration: {idle_seconds}s")
        return {
            'status': 'working',
            'display': f'等待 {waiting_for}',
            'duration': idle_seconds,
            'alert': idle_seconds > 60  # 超过 60 秒警告
        }

    # 检查工具执行（使用消息级别的时间戳计算 duration）
    tool_call = get_pending_tool_call_with_timestamp(agent_id)
    if tool_call:
        tool_timestamp = tool_call.get('timestamp', 0)
        tool_duration = int((now - tool_timestamp) / 1000) if tool_timestamp else 0
        tool_name = tool_call.get('name', '')

        # 只有未完成且超过阈值才显示
        if not tool_call.get('hasResult') and tool_duration > 2:
            logger.debug(f"[{agent_id}] Tool executing: {tool_name}, duration: {tool_duration}s")
            if tool_name == 'Bash':
                return {
                    'status': 'working',
                    'display': '执行命令',
                    'duration': tool_duration,
                    'alert': tool_duration > 30  # 超过 30 秒警告
                }
            elif tool_name in ('Write', 'Edit'):
                return {
                    'status': 'working',
                    'display': '读写文件',
                    'duration': tool_duration,
                    'alert': False
                }
            elif tool_duration > 3:
                return {
                    'status': 'working',
                    'display': '执行工具',
                    'duration': tool_duration,
                    'alert': False
                }

    # 检查等待模型（阈值：5秒）
    if idle_seconds > 5:
        alert = idle_seconds > 15  # 超过 15 秒可能是限流
        display = '等待响应' + (' (可能限流)' if alert else '')
        logger.debug(f"[{agent_id}] Waiting for model, duration: {idle_seconds}s, alert: {alert}")
        return {
            'status': 'working',
            'display': display,
            'duration': idle_seconds,
            'alert': alert
        }

    # 快速执行中
    return {'status': 'working', 'display': '处理中...', 'duration': 0, 'alert': False}


async def get_changed_agents() -> List[Dict[str, Any]]:
    """
    获取状态发生变化的 Agent 列表
    
    用于增量推送，只返回状态发生变化的 Agent
    
    Returns:
        变化的 Agent 状态列表（包含 id, status, currentTask, lastActiveAt, error 等）
    """
    tracker = get_tracker()
    
    agents = get_agents_list()
    changed_agents = []
    
    for agent in agents:
        agent_id = agent.get('id')
        
        # 计算状态（会使用缓存）
        status = calculate_agent_status(agent_id)
        current_task = get_current_task(agent_id)
        last_active = get_last_active_time(agent_id)
        last_error = get_last_error(agent_id) if status == 'down' else None
        
        state_data = {
            'id': agent_id,
            'name': agent.get('name'),
            'status': status,
            'currentTask': current_task,
            'lastActiveAt': last_active,
            'error': last_error
        }
        
        # 更新跟踪器并检查是否变化
        if tracker.update(agent_id, state_data):
            changed_agents.append(state_data)
    
    # 清除变化标记
    tracker.clear_changes()
    
    return changed_agents
