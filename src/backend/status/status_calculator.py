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
from data.session_reader import has_recent_errors, get_last_error


AgentStatus = Literal['idle', 'working', 'down']


def calculate_agent_status(agent_id: str) -> AgentStatus:
    """
    计算 Agent 状态
    
    优先级:
    1. 异常 (down) - 最近5分钟有错误
    2. 工作中 (working) - 有活跃的 subagent run
    3. 空闲 (idle) - 无活动
    """
    # 检查异常
    if has_recent_errors(agent_id, minutes=5):
        return 'down'
    
    # 检查工作中
    if is_agent_working(agent_id):
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
    """获取 Agent 最后活跃时间"""
    runs = get_agent_runs(agent_id, limit=1)
    if not runs:
        return 0
    
    run = runs[0]
    ended_at = run.get('endedAt')
    if ended_at:
        return ended_at
    
    started_at = run.get('startedAt', 0)
    return started_at


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
