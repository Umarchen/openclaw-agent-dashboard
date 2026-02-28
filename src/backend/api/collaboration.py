"""
协作流程 API 路由
符合 PRD: 展示老 K 与所有子 Agents 之间的连接关系，任务从老 K 流向子 Agents
扩展: Agent 模型配置、模型节点、最近调用（光球展示）
"""
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


class CollaborationNode(BaseModel):
    id: str
    type: str  # agent/task/tool/model
    name: str
    status: str  # idle/working/error (Agent 状态: 空闲/工作中/异常)
    timestamp: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


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


class CollaborationFlow(BaseModel):
    nodes: List[CollaborationNode]
    edges: List[CollaborationEdge]
    activePath: List[str]
    lastUpdate: int
    agentModels: Optional[Dict[str, Dict[str, Any]]] = None  # agentId -> {primary, fallbacks}
    models: Optional[List[str]] = None  # model ids
    recentCalls: Optional[List[ModelCall]] = None  # 最近调用（光球数据）


def _parse_agent_id(child_key: str) -> str:
    """从 childSessionKey 解析 agentId"""
    parts = child_key.split(':')
    if len(parts) >= 2 and parts[0] == 'agent':
        return parts[1]
    return ''


def _get_recent_model_calls(minutes: int = 30) -> List[Dict]:
    """获取最近 N 分钟的模型调用记录（用于光球展示）"""
    from api.performance import parse_session_file_with_details

    records = []
    openclaw_path = Path.home() / '.openclaw'
    agents_path = openclaw_path / 'agents'
    if not agents_path.exists():
        return []

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
                if r['timestamp'] >= since:
                    ts = r['timestamp']
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ts_local = ts.astimezone(TZ_DISPLAY)
                    records.append({
                        'agentId': agent_id,
                        'model': r.get('model', ''),
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
        get_agents_list, get_agent_models, get_all_models_from_agents,
        get_model_display_name, get_main_agent_id
    )
    from data.subagent_reader import get_active_runs
    from status.status_calculator import calculate_agent_status

    nodes = []
    edges = []
    active_path = []
    agent_models: Dict[str, Dict[str, Any]] = {}
    models_list: List[str] = []
    recent_calls: List[Dict] = []

    try:
        agents_list = get_agents_list()
        active_runs = get_active_runs()

        # 分离主 Agent (老 K) 和子 Agents
        main_agent_config = None
        sub_agents_config = []

        for agent in agents_list:
            agent_id = agent.get('id', '')
            if agent_id == 'main':
                main_agent_config = agent
            else:
                sub_agents_config.append(agent)

        # 0. 收集 Agent 模型配置、模型列表
        all_agents = [a for a in agents_list if a.get('id')]
        for agent in all_agents:
            aid = agent.get('id', '')
            agent_models[aid] = get_agent_models(aid)
        models_list = get_all_models_from_agents()
        recent_calls = _get_recent_model_calls(30)

        # 1. 主节点：老 K (Project Manager)
        main_status = "working" if active_runs else "idle"
        main_agent = CollaborationNode(
            id="main",
            type="agent",
            name=main_agent_config.get('name', '老 K') if main_agent_config else "老 K",
            status=main_status,
            timestamp=int(__import__('time').time() * 1000),
            metadata=agent_models.get('main')
        )
        nodes.append(main_agent)

        # 2. 子 Agent 节点：分析师、架构师、DevOps 等（始终展示）
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

            sub_node = CollaborationNode(
                id=agent_id,
                type="agent",
                name=agent_name,
                status=status,
                timestamp=None,
                metadata=agent_models.get(agent_id)
            )
            nodes.append(sub_node)

            # 创建边：老 K -> 子 Agent（任务委托）
            edges.append(CollaborationEdge(
                id=f"edge-main-{agent_id}",
                source="main",
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

        # 5. 活跃任务：高亮当前正在执行的路径
        for run in active_runs[:10]:
            child_key = run.get('childSessionKey', '')
            agent_id = _parse_agent_id(child_key)
            if not agent_id:
                continue

            task_name = run.get('task', 'Unknown Task')
            # 取首行作为节点名，不截断
            first_line = task_name.split('\n')[0].strip() if task_name else 'Unknown Task'
            task_name = first_line if first_line else task_name

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
                id=f"edge-{agent_id}-{task_id}",
                source=agent_id,
                target=task_id,
                type="calls",
                label="执行"
            ))

            active_path.extend(["main", agent_id, task_id])

    except Exception as e:
        print(f"Error building collaboration data: {e}")
        import traceback
        traceback.print_exc()

    if not nodes:
        nodes = [
            CollaborationNode(id="main", type="agent", name="老 K", status="idle"),
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

    return CollaborationFlow(
        nodes=nodes,
        edges=edges,
        activePath=list(set(active_path)),
        lastUpdate=int(__import__('time').time() * 1000),
        agentModels=agent_models,
        models=models_list,
        recentCalls=model_calls
    )
