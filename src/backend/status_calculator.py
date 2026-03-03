"""
状态计算器 - 计算 Agent 状态
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import time
from typing import Literal
from data.config_reader import get_agents_list, get_agent_config
from data.subagent_reader import is_agent_working, get_agent_runs
from data.session_reader import (
    has_recent_errors,
    get_last_error,
    has_recent_session_activity,
)


AgentStatus = Literal['idle', 'working', 'down']


def calculate_agent_status(agent_id: str) -> AgentStatus:
    """
    计算 Agent 状态（基于 runs.json + sessions.json）
    
    优先级:
    1. 异常 (down) - 最近5分钟有 stopReason=error
    2. 工作中 (working) - 有活跃 subagent run 或 session 正在处理（最近5分钟有活动）
    3. 空闲 (idle) - 无活跃 run 且最近5分钟无 session 活动
    """
    # 检查异常
    if has_recent_errors(agent_id, minutes=5):
        return 'down'
    
    # 检查工作中：subagent run 未结束，或 session 最近有活动
    if is_agent_working(agent_id):
        return 'working'
    if has_recent_session_activity(agent_id, minutes=5):
        return 'working'
    
    # 默认空闲
    return 'idle'


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
    
    # 截取前50个字符
    if len(task) > 50:
        task = task[:50] + '...'
    
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
