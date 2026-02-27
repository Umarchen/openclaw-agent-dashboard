"""
协作流程 API 路由
符合 PRD: 展示老 K 与所有子 Agents 之间的连接关系，任务从老 K 流向子 Agents
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

router = APIRouter()


class CollaborationNode(BaseModel):
    id: str
    type: str  # agent/task/tool
    name: str
    status: str  # idle/working/error (Agent 状态: 空闲/工作中/异常)
    timestamp: Optional[int] = None


class CollaborationEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str  # delegates/calls/returns/error
    label: Optional[str] = None


class CollaborationFlow(BaseModel):
    nodes: List[CollaborationNode]
    edges: List[CollaborationEdge]
    activePath: List[str]
    lastUpdate: int


def _parse_agent_id(child_key: str) -> str:
    """从 childSessionKey 解析 agentId"""
    parts = child_key.split(':')
    if len(parts) >= 2 and parts[0] == 'agent':
        return parts[1]
    return ''


@router.get("/collaboration", response_model=CollaborationFlow)
async def get_collaboration():
    """获取协作流程数据 - 老 K 与所有子 Agents 的拓扑关系"""
    from data.config_reader import get_agents_list
    from data.subagent_reader import get_active_runs
    from status.status_calculator import calculate_agent_status

    nodes = []
    edges = []
    active_path = []

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

        # 1. 主节点：老 K (Project Manager)
        main_status = "working" if active_runs else "idle"
        main_agent = CollaborationNode(
            id="main",
            type="agent",
            name=main_agent_config.get('name', '老 K') if main_agent_config else "老 K",
            status=main_status,
            timestamp=int(__import__('time').time() * 1000)
        )
        nodes.append(main_agent)

        # 2. 子 Agent 节点：分析师、架构师、DevOps 等（始终展示）
        agent_id_to_name = {}
        for agent in sub_agents_config:
            agent_id = agent.get('id', '')
            agent_name = agent.get('name', agent_id)
            agent_id_to_name[agent_id] = agent_name

            status = calculate_agent_status(agent_id)
            # 映射 down -> error, working -> working, idle -> idle
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
                timestamp=None
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

        # 3. 活跃任务：高亮当前正在执行的路径
        for run in active_runs[:10]:
            child_key = run.get('childSessionKey', '')
            agent_id = _parse_agent_id(child_key)
            if not agent_id:
                continue

            task_name = run.get('task', 'Unknown Task')
            if len(task_name) > 30:
                task_name = task_name[:30] + "..."

            # 任务节点（仅活跃任务）
            task_id = f"task-{run.get('runId', agent_id)}"
            task_node = CollaborationNode(
                id=task_id,
                type="task",
                name=task_name,
                status="working",
                timestamp=run.get('startedAt')
            )
            nodes.append(task_node)

            # 边：子 Agent -> 任务
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

    # 如果没有配置，返回默认结构
    if not nodes:
        nodes = [
            CollaborationNode(id="main", type="agent", name="老 K", status="idle"),
        ]

    return CollaborationFlow(
        nodes=nodes,
        edges=edges,
        activePath=list(set(active_path)),
        lastUpdate=int(__import__('time').time() * 1000)
    )
