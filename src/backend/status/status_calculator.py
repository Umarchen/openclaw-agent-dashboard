"""
状态计算器 - 计算 Agent 状态
集成缓存机制，提升状态计算性能
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import logging
import time
from typing import Literal, Dict, Any, List
from data.config_reader import get_agents_list, get_agent_config, get_main_agent_id, agent_ids_equal
from data.subagent_reader import is_agent_working, get_agent_runs
from data.session_reader import (
    has_recent_errors,
    get_last_error,
    get_session_updated_at,
    get_pending_tool_call_with_timestamp,
)

# 导入缓存和变化跟踪
from .status_cache import get_cache
from .change_tracker import get_tracker

logger = logging.getLogger(__name__)

# 主 Agent 无 run、且尚无 thinking/未完成 tool 时，用会话最近写入时间兜底 working（秒）。
# 过短则首包前易显示空闲；过长则停跑后若仍有会话文件写入可能短暂误显 working。
MAIN_AGENT_SOLO_STREAM_GRACE_SEC = 20

AgentStatus = Literal['idle', 'working', 'down']


def _main_agent_solo_processing(agent_id: str) -> bool:
    """
    主 Agent 未出现在「进行中 run」的 child/requester 里时，是否仍可视作在处理。
    强信号：thinking 块、尚未收到 toolResult 的工具调用。
    弱信号（短窗）：sessions 聚合 updatedAt 在 MAIN_AGENT_SOLO_STREAM_GRACE_SEC 内——覆盖纯等模型首包、
    流式尚未落 thinking/tool 的阶段；不用于填充 currentTask，避免假任务文案。
    """
    if not agent_ids_equal(agent_id, get_main_agent_id()):
        return False
    if is_agent_working(agent_id):
        return False
    from data.session_reader import (
        get_pending_tool_call_with_timestamp,
        has_thinking_block,
        is_session_updated_within_seconds,
    )
    if has_thinking_block(agent_id):
        return True
    pending = get_pending_tool_call_with_timestamp(agent_id)
    if pending and not pending.get('hasResult'):
        return True
    return is_session_updated_within_seconds(agent_id, MAIN_AGENT_SOLO_STREAM_GRACE_SEC)


def calculate_agent_status(agent_id: str, use_cache: bool = True) -> AgentStatus:
    """
    计算 Agent 状态（基于 runs.json + sessions.json）
    
    优先级:
    1. 异常 (down) - 最近5分钟有 stopReason=error
    2. 工作中 (working) - 有活跃 subagent run；或主 Agent 且无 run 时 thinking / 未完成工具 / 短窗内会话写入
    3. 空闲 (idle) - 其余情况（子 Agent 无 run 即空闲，与协作图 activePath 一致）
    
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

    try:
        # 重新计算
        if has_recent_errors(agent_id, minutes=5):
            status = 'down'
        elif is_agent_working(agent_id):
            status = 'working'
        elif _main_agent_solo_processing(agent_id):
            status = 'working'
        else:
            status = 'idle'
    except OSError as e:
        from core.error_handler import classify_exception, record_error
        from core.fallback_manager import run_fallback

        cat = classify_exception(e)
        record_error(cat, str(e), f"status_calculator:calculate:{agent_id}", exc=e)
        fb = run_fallback(cat, agent_id=agent_id)
        if fb is not None:
            return fb  # type: ignore[return-value]
        return 'idle'

    # 更新缓存（只缓存状态）
    if use_cache:
        cache = get_cache()
        cache.set(agent_id, {'status': status})

    return status


def get_agents_with_status() -> list:
    """获取所有 Agent 及其状态"""
    try:
        agents = get_agents_list()
    except OSError as e:
        from core.error_handler import classify_exception, record_error

        record_error(classify_exception(e), str(e), "get_agents_with_status:list", exc=e)
        return []

    result = []

    for agent in agents:
        agent_id = agent.get('id')
        try:
            status = calculate_agent_status(agent_id)
            current_task = get_current_task(agent_id)
            if status == 'idle':
                current_task = ''
            last_active = get_last_active_time(agent_id)
            last_error = get_last_error(agent_id) if status == 'down' else None
        except OSError as e:
            from core.error_handler import classify_exception, record_error
            from core.fallback_manager import run_fallback

            cat = classify_exception(e)
            record_error(cat, str(e), f"get_agents_with_status:{agent_id}", exc=e)
            status = run_fallback(cat, agent_id=agent_id) or 'idle'
            current_task = ''
            last_active = 0
            last_error = None

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
    """
    获取 Agent 当前任务描述。
    仅从未结束的 run（endedAt 为空）读取；已结束的 run 只代表历史，不应在空闲时仍当「当前任务」展示。
    """
    runs = get_agent_runs(agent_id, limit=40)
    for run in runs:
        if run.get('endedAt') is not None:
            continue
        task = run.get('task', '') or ''
        if len(task) > 60:
            task = task[:57] + '...'
        return task

    return ''


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

    # 无活跃 run：子 Agent 与协作图连线一致，直接空闲；主 Agent 仅在有 solo 处理信号时显示忙碌
    if not is_agent_working(agent_id):
        if _main_agent_solo_processing(agent_id):
            return {'status': 'working', 'display': '处理中...', 'duration': 0, 'alert': False}
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
        if status == 'idle':
            current_task = ''
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
