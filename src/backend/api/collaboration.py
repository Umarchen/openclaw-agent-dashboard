"""
协作流程 API 路由
符合 PRD: 展示老 K 与所有子 Agents 之间的连接关系，任务从老 K 流向子 Agents
扩展: Agent 模型配置、模型节点、最近调用（光球展示）
"""
import re
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ_DISPLAY = ZoneInfo('Asia/Shanghai')

sys.path.append(str(Path(__file__).parent.parent))

router = APIRouter()
logger = logging.getLogger(__name__)


class CollaborationNode(BaseModel):
    id: str
    type: str  # agent/task/tool/model
    name: str
    status: str  # idle/working/error (Agent 状态: 空闲/工作中/异常)
    timestamp: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    # 当前任务（有效描述）
    currentTask: Optional[str] = None
    # 错误信息
    error: Optional[Dict[str, Any]] = None
    # 卡顿警告
    stuckWarning: Optional[Dict[str, Any]] = None


class CollaborationEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str  # delegates/calls/returns/error/model
    label: Optional[str] = None


class ModelCall(BaseModel):
    id: str
    agentId: str
    model: str  # provider/model
    sessionId: str
    trigger: str
    tokens: int
    timestamp: int  # ms
    time: str  # HH:MM:SS


class AgentDisplayStatus(BaseModel):
    """Agent 显示状态（基于时间阈值）"""
    status: str  # 'idle' | 'working'
    display: str  # 显示文本
    duration: int  # 持续时间（秒）
    alert: bool  # 是否需要警告


class ActiveTask(BaseModel):
    """单个活跃任务（用于多任务并行展示）"""
    id: str                      # task-{runId}
    name: str                    # 任务名称（清理后）
    status: str = "working"      # working | retrying | failed
    timestamp: Optional[int] = None  # 开始时间
    childAgentId: Optional[str] = None  # 主 Agent 任务时，指向被派发的子 Agent
    featureId: Optional[str] = None     # FEATURE_ID（如果有）


def _extract_feature_id(task_name: str) -> Optional[str]:
    """从任务名称中提取 FEATURE_ID"""
    if not task_name:
        return None
    # 匹配 [FEATURE_ID] xxx 格式
    match = re.search(r'\[FEATURE_ID\]\s*(\S+)', task_name)
    if match:
        return match.group(1)
    return None


def _build_agent_active_tasks(
    active_runs: List[Dict[str, Any]],
    main_agent_id: str
) -> Dict[str, List[Dict[str, Any]]]:
    """
    构建每个 Agent 的活跃任务列表（支持多任务并行展示）

    自适应不同组网：
    - 单 Agent 模式：main 没有子 agent，任务直接执行
    - 主从模式：main 派发给子 agent
    - 嵌套模式：子 agent 可以再派发给孙 agent

    Args:
        active_runs: 从 runs.json 读取的活跃任务
        main_agent_id: 主 Agent ID

    Returns:
        {
            "main": [task1, task2, ...],           # PM 派发的任务
            "analyst-agent": [task3, ...],          # 分析师执行的任务
            ...
        }
    """
    from data.config_reader import agent_ids_equal, canonical_agent_id_from_config

    agent_active_tasks: Dict[str, List[Dict[str, Any]]] = {}

    for run in active_runs:
        child_key = run.get('childSessionKey', '')
        requester_key = run.get('requesterSessionKey', '')

        # 解析执行者 Agent（会话 key 内为小写，映射到配置中的原始 id）
        raw_child = _parse_agent_id(child_key)
        raw_requester = _parse_agent_id(requester_key)
        child_agent_id = canonical_agent_id_from_config(raw_child) if raw_child else ''
        requester_agent_id = (
            canonical_agent_id_from_config(raw_requester) if raw_requester else ''
        )

        if not child_agent_id:
            continue

        # 清理任务名称
        task_name = _clean_task_name(run.get('task', ''))
        if not task_name:
            task_name = '未命名任务'

        run_id = run.get('runId', child_agent_id)

        # 提取 featureId
        feature_id = _extract_feature_id(run.get('task', ''))

        # 构建任务对象
        task_item: Dict[str, Any] = {
            'id': f"task-{run_id}",
            'name': task_name,
            'status': 'working',
            'timestamp': run.get('startedAt'),
            'featureId': feature_id
        }

        # 如果有派发者，添加 childAgentId（用于主 Agent 显示任务流向）
        if requester_agent_id and not agent_ids_equal(requester_agent_id, child_agent_id):
            task_item['childAgentId'] = child_agent_id

        # 1. 添加到派发者（如果派发者是某个已知 agent）
        if requester_agent_id:
            if requester_agent_id not in agent_active_tasks:
                agent_active_tasks[requester_agent_id] = []
            agent_active_tasks[requester_agent_id].append(task_item)

        # 2. 添加到执行者（不带 childAgentId）
        if child_agent_id not in agent_active_tasks:
            agent_active_tasks[child_agent_id] = []
        child_task = {k: v for k, v in task_item.items() if k != 'childAgentId'}
        agent_active_tasks[child_agent_id].append(child_task)

    return agent_active_tasks


def _get_display_task_summary(tasks: List[Dict[str, Any]]) -> str:
    """
    获取用于显示的任务摘要

    策略：
    - 0 个任务：返回空
    - 1 个任务：显示任务名称
    - 2+ 个任务：显示 "N 个任务进行中"
    """
    count = len(tasks)
    if count == 0:
        return ''
    elif count == 1:
        # 截断过长任务名
        name = tasks[0].get('name', '')
        return name[:50] + '...' if len(name) > 50 else name
    else:
        return f"{count} 个任务进行中"


class CollaborationFlow(BaseModel):
    nodes: List[CollaborationNode]
    edges: List[CollaborationEdge]
    activePath: List[str]
    lastUpdate: int
    mainAgentId: Optional[str] = None  # 主 Agent ID，前端用于布局与样式
    agentModels: Optional[Dict[str, Dict[str, Any]]] = None
    models: Optional[List[str]] = None
    recentCalls: Optional[List[ModelCall]] = None
    hierarchy: Optional[Dict[str, List[str]]] = None  # agentId -> 子 agent 列表
    depths: Optional[Dict[str, int]] = None  # agentId -> 层级深度 (0=主, 1=子, 2=孙...)
    # 多任务并行展示：每个 Agent 的活跃任务列表
    agentActiveTasks: Optional[Dict[str, List[ActiveTask]]] = None
    # 多任务并行展示：每个 Agent 的活跃任务列表
    agentActiveTasks: Optional[Dict[str, List[ActiveTask]]] = None


def _parse_agent_id(session_key: str) -> str:
    """从 sessionKey (childSessionKey 或 requesterSessionKey) 解析 agentId"""
    parts = (session_key or '').split(':')
    if len(parts) >= 2 and parts[0] == 'agent':
        return parts[1]
    return ''


# ============================================================================
# 模型 ID 规范化（TR9-2）
# ============================================================================

# 模块级缓存
_model_mapping_cache: Optional[Dict[str, str]] = None


def _get_model_mapping() -> Dict[str, str]:
    """
    获取 model 映射（带缓存）

    Returns:
        {'claude-sonnet-4.6': 'anthropic/claude-sonnet-4.6', ...}
    """
    global _model_mapping_cache
    if _model_mapping_cache is None:
        try:
            from data.config_reader import get_all_models_from_agents
            _model_mapping_cache = {}
            for model_id in get_all_models_from_agents():
                short = model_id.split('/')[-1]
                # 精确匹配
                _model_mapping_cache[short] = model_id
                # 去除日期版本号的映射（使用正则精确匹配 -20YYMMDD）
                base = re.sub(r'-20\d{6}$', '', short)
                if base != short:
                    _model_mapping_cache[base] = model_id
        except Exception as e:
            logger.warning(f"Failed to build model mapping: {e}")
            _model_mapping_cache = {}
    return _model_mapping_cache


def _normalize_model_id(model_from_session: str) -> str:
    """
    将 session 中的 model 值规范化为标准格式

    Args:
        model_from_session: session 中的 model 值

    Returns:
        标准化的模型 ID，如 "anthropic/claude-sonnet-4.6"

    Examples:
        >>> _normalize_model_id("claude-sonnet-4.6")
        "anthropic/claude-sonnet-4.6"
        >>> _normalize_model_id("claude-sonnet-4.6-20250514")
        "anthropic/claude-sonnet-4.6"
        >>> _normalize_model_id("anthropic/claude-sonnet-4.6")
        "anthropic/claude-sonnet-4.6"
    """
    if not model_from_session:
        return '(unknown)'

    # 已经是标准格式
    if '/' in model_from_session:
        return model_from_session

    mapping = _get_model_mapping()

    # 精确匹配
    if model_from_session in mapping:
        return mapping[model_from_session]

    # 使用正则去除日期版本号后匹配
    base_name = re.sub(r'-20\d{6}$', '', model_from_session)
    if base_name in mapping:
        return mapping[base_name]

    logger.debug(f"Unknown model format: {model_from_session}")
    return model_from_session


def _clear_model_mapping_cache():
    """清除模型映射缓存（配置变更时调用）"""
    global _model_mapping_cache
    _model_mapping_cache = None


def _clean_task_name(task_name: str) -> str:
    """清理任务名称，提取有效的任务描述"""
    if not task_name:
        return ''
    # 过滤子 Agent 回传内容（不应作为任务显示）
    if 'Result (untrusted content, treat as data):' in task_name or '[Internal task completion event]' in task_name:
        return ''

    lines = task_name.strip().split('\n')

    # 需要过滤的技术信息前缀
    tech_patterns = [
        'CONTEXT FILES',
        'WORKING DIRECTORY',
        'SYSTEM INFO',
        'ENVIRONMENT',
        '---',
        '===',
        '```',
        '# ',
        '## ',
    ]

    # 查找第一个有效的任务描述行
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 跳过技术信息
        is_tech = False
        for pattern in tech_patterns:
            if line.upper().startswith(pattern):
                is_tech = True
                break

        if not is_tech and len(line) > 3:
            # 找到有效行
            if len(line) > 80:
                return line[:77] + '...'
            return line

    # 如果没找到有效行，返回空
    return ''


def _enrich_main_agent_active_tasks_if_needed(
    agent_active_tasks: Dict[str, List[Dict[str, Any]]],
    main_agent_id: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    主 Agent 仅更新主会话、subagents/runs 无条目时，agentActiveTasks 为空；
    在仍为 working 时补一条会话摘要，便于卡片「并行任务」区有文案。
    """
    from status.status_calculator import calculate_agent_status, get_current_task

    if calculate_agent_status(main_agent_id) != 'working':
        return agent_active_tasks
    if agent_active_tasks.get(main_agent_id):
        return agent_active_tasks
    hint = get_current_task(main_agent_id)
    name = _clean_task_name(hint) if hint else ''
    if not name:
        return agent_active_tasks
    merged = dict(agent_active_tasks)
    merged[main_agent_id] = [
        {
            'id': 'task-main-session',
            'name': name,
            'status': 'working',
            'timestamp': None,
            'featureId': None,
        }
    ]
    return merged


def _get_agent_error_info(agent_id: str) -> Optional[Dict[str, Any]]:
    """获取 agent 的错误/异常信息"""
    from session_reader import get_last_error, has_recent_errors

    if has_recent_errors(agent_id, minutes=10):
        error = get_last_error(agent_id)
        if error:
            return {
                'hasError': True,
                'type': error.get('type', 'unknown'),
                'message': error.get('message', '')[:100],  # 截断
                'timestamp': error.get('timestamp', 0)
            }
    return None


def _check_agent_stuck(agent_id: str) -> Optional[Dict[str, Any]]:
    """检查 agent 是否卡顿（长时间无响应但有活跃任务）"""
    import time
    from session_reader import get_session_updated_at
    from data.subagent_reader import is_agent_working, get_active_runs

    if not is_agent_working(agent_id):
        return None

    last_update = get_session_updated_at(agent_id)
    if not last_update:
        return None

    now = int(time.time() * 1000)
    idle_seconds = (now - last_update) / 1000

    # 超过 60 秒无响应视为可能卡顿
    if idle_seconds > 60:
        # 分析卡顿原因
        reason = _analyze_stuck_reason(agent_id, idle_seconds)
        return {
            'isStuck': True,
            'idleSeconds': int(idle_seconds),
            'lastUpdate': last_update,
            'reason': reason.get('type', 'unknown'),
            'reasonDetail': reason.get('detail', ''),
            'waitingFor': reason.get('waitingFor')
        }
    return None


def _analyze_stuck_reason(agent_id: str, idle_seconds: int) -> Dict[str, Any]:
    """
    分析 Agent 卡顿的原因

    Returns:
        {
            'type': 'waiting_subagent' | 'model_delay' | 'tool_execution' | 'unknown',
            'detail': '详细描述',
            'waitingFor': {'agentId': 'xxx', 'task': 'xxx'} | None
        }
    """
    from data.subagent_reader import get_active_runs
    from data.config_reader import normalize_openclaw_agent_id

    # 检查是否在等待子 agent
    active_runs = get_active_runs()
    prefix = f"agent:{normalize_openclaw_agent_id(agent_id)}:"
    for run in active_runs:
        requester_key = run.get('requesterSessionKey', '')
        # 如果这个 agent 是 requester，说明它在等待子 agent
        if prefix in requester_key:
            child_key = run.get('childSessionKey', '')
            if child_key and ':' in child_key:
                parts = child_key.split(':')
                if len(parts) >= 2:
                    child_agent_id = parts[1]
                    task = run.get('task', '')[:50]
                    return {
                        'type': 'waiting_subagent',
                        'detail': f'等待子代理 {child_agent_id} 完成任务',
                        'waitingFor': {
                            'agentId': child_agent_id,
                            'task': task
                        }
                    }

    # 检查最近是否有模型调用（可能是模型响应慢）
    # 这里简单判断：如果 idle 时间很长但没有等待子 agent，可能是模型或工具问题
    if idle_seconds > 120:
        return {
            'type': 'model_delay',
            'detail': '模型响应时间过长，可能遇到限流或网络问题',
            'waitingFor': None
        }

    if idle_seconds > 60:
        return {
            'type': 'tool_execution',
            'detail': '工具执行中或等待外部资源',
            'waitingFor': None
        }

    return {
        'type': 'unknown',
        'detail': '原因未知',
        'waitingFor': None
    }


def _get_recent_model_calls(minutes: int = 30) -> List[Dict]:
    """
    获取最近 N 分钟的模型调用记录（用于光球展示）

    Args:
        minutes: 时间范围（分钟）

    Returns:
        调用记录列表，model 字段已规范化

    注意:
        - since 为 timezone-aware datetime (UTC)
        - timestamp 统一处理为 UTC timezone-aware
        - model 字段规范化为 provider/model 格式
    """
    from api.performance import parse_session_file_with_details

    records = []
    from data.config_reader import get_openclaw_root
    openclaw_path = get_openclaw_root()
    agents_path = openclaw_path / 'agents'
    if not agents_path.exists():
        return []

    # 确保 since 是 UTC timezone-aware
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=minutes)

    for agent_dir in agents_path.iterdir():
        if not agent_dir.is_dir():
            continue
        agent_id = agent_dir.name
        sessions_path = agent_dir / 'sessions'
        if not sessions_path.exists():
            continue
        for session_file in sessions_path.glob('*.jsonl'):
            if 'lock' in session_file.name or 'deleted' in session_file.name:
                continue
            for r in parse_session_file_with_details(session_file, agent_id):
                ts = r['timestamp']
                # 确保 timestamp 是 timezone-aware
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                if ts >= since:
                    ts_local = ts.astimezone(TZ_DISPLAY)
                    # 规范化 model 字段
                    normalized_model = _normalize_model_id(r.get('model', ''))

                    records.append({
                        'agentId': agent_id,
                        'model': normalized_model,  # 使用规范化后的值
                        'sessionId': r['sessionId'],
                        'trigger': r.get('trigger', ''),
                        'tokens': r.get('tokens', 0),
                        'timestamp': int(ts.timestamp() * 1000),
                        'time': ts_local.strftime('%H:%M:%S')
                    })

    records.sort(key=lambda x: x['timestamp'])
    return records[-100:]  # 最多 100 条


@router.get("/collaboration", response_model=CollaborationFlow)
async def get_collaboration():
    """获取协作流程数据 - 主 Agent 与子 Agents 的拓扑关系，含模型配置与最近调用"""
    from data.config_reader import (
        get_agents_list, get_agent_models, get_models_configured_by_agents,
        get_model_display_name, get_main_agent_id,
        agent_ids_equal, normalize_openclaw_agent_id, canonical_agent_id_from_config,
    )
    from data.subagent_reader import get_active_runs
    from status.status_calculator import calculate_agent_status, get_current_task

    nodes = []
    edges = []
    active_path = []
    agent_models: Dict[str, Dict[str, Any]] = {}
    models_list: List[str] = []
    recent_calls: List[Dict] = []
    active_runs: List[Dict[str, Any]] = []

    main_agent_id = 'main'
    try:
        main_agent_id = get_main_agent_id()
        agents_list = get_agents_list()
        active_runs = get_active_runs()

        main_agent_id = get_main_agent_id()
        main_agent_config = next(
            (a for a in agents_list if agent_ids_equal(a.get('id'), main_agent_id)), None
        )
        sub_agents_config = [a for a in agents_list if not agent_ids_equal(a.get('id'), main_agent_id)]

        all_agents = [a for a in agents_list if a.get('id')]
        for agent in all_agents:
            aid = agent.get('id', '')
            agent_models[aid] = get_agent_models(aid)
        models_list = get_models_configured_by_agents()
        recent_calls = _get_recent_model_calls(30)

        main_display_name = (main_agent_config.get('name') if main_agent_config else None) or "主 Agent"
        # 与子 Agent 一致：基于 runs + session 活动判断；独立 PM 无 subagent run 时仍可能在工作
        main_raw = calculate_agent_status(main_agent_id)
        if main_raw == 'down':
            main_status = 'error'
        elif main_raw == 'working':
            main_status = 'working'
        else:
            main_status = 'idle'

        # 获取主 agent 的当前任务和错误信息
        main_current_task = ''
        main_error = None
        main_stuck = None
        if active_runs:
            # 找到主 agent 作为 requester 的任务
            main_prefix = f"agent:{normalize_openclaw_agent_id(main_agent_id)}:"
            for run in active_runs:
                requester_key = run.get('requesterSessionKey', '')
                if main_prefix in requester_key:
                    main_current_task = _clean_task_name(run.get('task', ''))
                    break
            if not main_current_task and active_runs:
                main_current_task = _clean_task_name(active_runs[0].get('task', ''))
        if not main_current_task:
            main_current_task = _clean_task_name(get_current_task(main_agent_id))
        main_error = _get_agent_error_info(main_agent_id)
        main_stuck = _check_agent_stuck(main_agent_id)

        main_ct = main_current_task if main_current_task else None
        if main_status == 'idle':
            main_ct = None

        main_agent = CollaborationNode(
            id=main_agent_id,
            type="agent",
            name=main_display_name,
            status=main_status,
            timestamp=int(__import__('time').time() * 1000),
            metadata=agent_models.get(main_agent_id),
            currentTask=main_ct,
            error=main_error,
            stuckWarning=main_stuck
        )
        nodes.append(main_agent)

        for agent in sub_agents_config:
            agent_id = agent.get('id', '')
            agent_name = agent.get('name', agent_id)

            status = calculate_agent_status(agent_id)
            if status == 'down':
                status = 'error'
            elif status == 'working':
                status = 'working'
            else:
                status = 'idle'

            # 获取子 agent 的当前任务
            current_task = ''
            child_prefix = f"agent:{normalize_openclaw_agent_id(agent_id)}:"
            for run in active_runs:
                child_key = run.get('childSessionKey', '')
                if child_prefix in child_key:
                    current_task = _clean_task_name(run.get('task', ''))
                    break

            if status == 'idle':
                current_task = ''

            # 获取错误和卡顿信息
            error_info = _get_agent_error_info(agent_id)
            stuck_info = _check_agent_stuck(agent_id)

            sub_node = CollaborationNode(
                id=agent_id,
                type="agent",
                name=agent_name,
                status=status,
                timestamp=None,
                metadata=agent_models.get(agent_id),
                currentTask=current_task if current_task else None,
                error=error_info,
                stuckWarning=stuck_info
            )
            nodes.append(sub_node)

            edges.append(CollaborationEdge(
                id=f"edge-{main_agent_id}-{agent_id}",
                source=main_agent_id,
                target=agent_id,
                type="delegates",
                label="委托"
            ))

        # 3. 模型节点（右侧）
        for i, model_id in enumerate(models_list):
            model_node = CollaborationNode(
                id=f"model-{model_id.replace('/', '-')}",
                type="model",
                name=get_model_display_name(model_id),
                status="idle",
                timestamp=None,
                metadata={"modelId": model_id}
            )
            nodes.append(model_node)

        # 4. Agent -> Model 边（配置了该模型的 Agent）
        for agent in all_agents:
            aid = agent.get('id', '')
            cfg = agent_models.get(aid, {})
            primary = cfg.get('primary', '')
            fallbacks = cfg.get('fallbacks', [])
            all_models = [primary] + [f for f in fallbacks if f != primary]
            for mid in all_models:
                if mid and mid in models_list:
                    mid_safe = mid.replace('/', '-')
                    edges.append(CollaborationEdge(
                        id=f"edge-{aid}-model-{mid_safe}",
                        source=aid,
                        target=f"model-{mid_safe}",
                        type="model",
                        label=mid
                    ))

        # 5. 活跃任务与 spawn 链：requesterSessionKey -> childSessionKey -> task
        for run in active_runs[:20]:
            child_key = run.get('childSessionKey', '')
            requester_key = run.get('requesterSessionKey', '')
            agent_id = _parse_agent_id(child_key)
            requester_id = _parse_agent_id(requester_key)
            if not agent_id:
                continue

            agent_id_canon = canonical_agent_id_from_config(agent_id)
            requester_id_canon = (
                canonical_agent_id_from_config(requester_id) if requester_id else requester_id
            )

            task_name = _clean_task_name(run.get('task', ''))

            task_id = f"task-{run.get('runId', agent_id)}"
            task_node = CollaborationNode(
                id=task_id,
                type="task",
                name=task_name,
                status="working",
                timestamp=run.get('startedAt')
            )
            nodes.append(task_node)

            edges.append(CollaborationEdge(
                id=f"edge-{agent_id_canon}-{task_id}",
                source=agent_id_canon,
                target=task_id,
                type="calls",
                label="执行"
            ))

            # Spawn 链：主 Agent 派发 -> 子 Agent 执行
            if requester_id and requester_id != agent_id:
                edges.append(CollaborationEdge(
                    id=f"edge-spawn-{requester_id_canon}-{task_id}",
                    source=requester_id_canon,
                    target=task_id,
                    type="delegates",
                    label="派发"
                ))
                # 如果 requester 是主 agent，给主 agent 也添加一个任务节点（用户命令）
                # 移除 main_agent_task_created 限制，支持多任务并行显示
                if agent_ids_equal(requester_id, main_agent_id):
                    # 主 agent 的任务就是用户原始命令
                    main_task_id = f"task-main-{run.get('runId', 'current')}"
                    main_task_node = CollaborationNode(
                        id=main_task_id,
                        type="task",
                        name=task_name,  # 用户命令
                        status="working",
                        timestamp=run.get('startedAt')
                    )
                    nodes.append(main_task_node)
                    edges.append(CollaborationEdge(
                        id=f"edge-{main_agent_id}-{main_task_id}",
                        source=main_agent_id,
                        target=main_task_id,
                        type="calls",
                        label="执行"
                    ))

            active_path.extend([main_agent_id, agent_id_canon, task_id])

    except Exception as e:
        print(f"Error building collaboration data: {e}")
        import traceback
        traceback.print_exc()

    if not nodes:
        try:
            main_agent_id = get_main_agent_id()
        except Exception:
            main_agent_id = 'main'
        nodes = [
            CollaborationNode(id=main_agent_id, type="agent", name="主 Agent", status="idle"),
        ]

    # 构建 recentCalls 带 id
    model_calls = [
        ModelCall(
            id=f"call-{i}",
            agentId=r["agentId"],
            model=r.get("model", ""),
            sessionId=r.get("sessionId", ""),
            trigger=r.get("trigger", ""),
            tokens=r.get("tokens", 0),
            timestamp=r.get("timestamp", 0),
            time=r.get("time", "")
        )
        for i, r in enumerate(recent_calls)
    ]

    # 计算层级深度 (depths) 和层级关系 (hierarchy)
    # 从 edges 中提取 agent 之间的父子关系
    hierarchy: Dict[str, List[str]] = {}
    agent_ids = set(n.id for n in nodes if n.type == "agent")

    # 构建 delegate 关系: source -> [targets]
    for edge in edges:
        if edge.type == "delegates":
            source = edge.source
            target = edge.target
            # 只处理 agent 之间的委托关系
            if source in agent_ids and target in agent_ids:
                if source not in hierarchy:
                    hierarchy[source] = []
                if target not in hierarchy[source]:
                    hierarchy[source].append(target)

    # 计算 depth: 主 agent depth=0, 其子 agent depth=1, 孙 agent depth=2...
    depths: Dict[str, int] = {}
    depths[main_agent_id] = 0

    # BFS 计算深度
    queue = [main_agent_id]
    while queue:
        parent = queue.pop(0)
        parent_depth = depths.get(parent, 0)
        for child in hierarchy.get(parent, []):
            if child not in depths:
                depths[child] = parent_depth + 1
                queue.append(child)

    # 未在 hierarchy 中的 agent 默认 depth=1 (作为主 agent 的直接子节点)
    for aid in agent_ids:
        if aid not in depths:
            depths[aid] = 1

    # 构建多任务并行数据
    agent_active_tasks = _enrich_main_agent_active_tasks_if_needed(
        _build_agent_active_tasks(active_runs, main_agent_id),
        main_agent_id,
    )

    return CollaborationFlow(
        nodes=nodes,
        edges=edges,
        activePath=list(set(active_path)),
        lastUpdate=int(__import__('time').time() * 1000),
        mainAgentId=main_agent_id,
        agentModels=agent_models,
        models=models_list,
        recentCalls=model_calls,
        hierarchy=hierarchy,
        depths=depths,
        agentActiveTasks=agent_active_tasks
    )


class CollaborationDynamic(BaseModel):
    """仅动态数据：状态、小球、任务节点，不包含静态拓扑"""
    activePath: List[str]
    recentCalls: List[ModelCall]
    agentStatuses: Dict[str, str]  # agentId -> idle/working/error
    agentDynamicStatuses: Optional[Dict[str, AgentDisplayStatus]] = None  # 详细显示状态
    taskNodes: List[CollaborationNode]
    taskEdges: List[CollaborationEdge]
    mainAgentId: str
    lastUpdate: int
    # 多任务并行展示：每个 Agent 的活跃任务列表
    agentActiveTasks: Optional[Dict[str, List[ActiveTask]]] = None


@router.get("/collaboration/dynamic", response_model=CollaborationDynamic)
async def get_collaboration_dynamic():
    """轻量接口：仅返回状态、小球、任务等动态数据，用于静默刷新，不触发整体重载"""
    from data.config_reader import get_agents_list, get_main_agent_id
    from data.subagent_reader import get_active_runs
    from status.status_calculator import calculate_agent_status, get_display_status

    active_path = []
    agent_statuses: Dict[str, str] = {}
    agent_dynamic_statuses: Dict[str, AgentDisplayStatus] = {}
    task_nodes: List[CollaborationNode] = []
    task_edges: List[CollaborationEdge] = []
    main_agent_id = 'main'
    active_runs: List[Dict[str, Any]] = []

    try:
        main_agent_id = get_main_agent_id()
        agents_list = get_agents_list()
        active_runs = get_active_runs()

        for agent in agents_list:
            aid = agent.get('id', '')
            if not aid:
                continue
            status = calculate_agent_status(aid)
            if status == 'down':
                status = 'error'
            elif status == 'working':
                status = 'working'
            else:
                status = 'idle'
            agent_statuses[aid] = status

            # 获取详细显示状态
            try:
                dyn_status = get_display_status(aid)
                agent_dynamic_statuses[aid] = AgentDisplayStatus(
                    status=dyn_status['status'],
                    display=dyn_status['display'],
                    duration=dyn_status['duration'],
                    alert=dyn_status['alert']
                )
            except Exception as e:
                logger.warning(f"Failed to get display status for {aid}: {e}")

        # 主 Agent 状态已在上方循环中与 calculate_agent_status 一致，勿再用「有无 active_runs」覆盖
        # （独立 PM 仅更新主会话时 runs 可能为空，否则会误显示空闲）

        # 处理活跃任务（简化：不在流程图中创建任务节点，任务信息由 agentActiveTasks 提供）
        # 任务详情在 Agent 卡片内显示，流程图只显示 Agent 之间的委托关系
        for run in active_runs[:20]:
            child_key = run.get('childSessionKey', '')
            requester_key = run.get('requesterSessionKey', '')
            agent_id = _parse_agent_id(child_key)
            requester_id = _parse_agent_id(requester_key)
            if not agent_id:
                continue
            # 只更新 activePath，不创建任务节点
            active_path.extend([agent_id])
            if requester_id and requester_id != agent_id:
                active_path.extend([requester_id])
    except Exception as e:
        logger.error(f"Error building collaboration dynamic: {e}")

    recent_calls_raw = _get_recent_model_calls(30)
    model_calls = [
        ModelCall(
            id=f"call-{i}",
            agentId=r["agentId"],
            model=r.get("model", ""),
            sessionId=r.get("sessionId", ""),
            trigger=r.get("trigger", ""),
            tokens=r.get("tokens", 0),
            timestamp=r.get("timestamp", 0),
            time=r.get("time", "")
        )
        for i, r in enumerate(recent_calls_raw)
    ]

    # 构建多任务并行数据
    agent_active_tasks = _enrich_main_agent_active_tasks_if_needed(
        _build_agent_active_tasks(active_runs, main_agent_id),
        main_agent_id,
    )

    return CollaborationDynamic(
        activePath=list(set(active_path)),
        recentCalls=model_calls,
        agentStatuses=agent_statuses,
        agentDynamicStatuses=agent_dynamic_statuses,
        taskNodes=task_nodes,
        taskEdges=task_edges,
        mainAgentId=main_agent_id,
        lastUpdate=int(__import__('time').time() * 1000),
        agentActiveTasks=agent_active_tasks
    )
