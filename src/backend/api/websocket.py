"""
WebSocket 路由
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set
import json
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

router = APIRouter()

# 活跃的 WebSocket 连接
active_connections: Set[WebSocket] = set()

# 周期性推送间隔（秒）
BROADCAST_INTERVAL_SEC = 8
_broadcast_task: asyncio.Task | None = None


async def _periodic_broadcast_loop():
    """周期性广播完整状态，确保无文件变更时也有更新"""
    while True:
        await asyncio.sleep(BROADCAST_INTERVAL_SEC)
        if active_connections:
            await broadcast_full_state()


def _ensure_broadcast_task():
    """有连接时启动周期性推送"""
    global _broadcast_task
    if active_connections and (_broadcast_task is None or _broadcast_task.done()):
        _broadcast_task = asyncio.create_task(_periodic_broadcast_loop())


def _cancel_broadcast_task():
    """无连接时停止周期性推送"""
    global _broadcast_task
    if not active_connections and _broadcast_task and not _broadcast_task.done():
        _broadcast_task.cancel()
        _broadcast_task = None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点"""
    await websocket.accept()
    active_connections.add(websocket)
    _ensure_broadcast_task()
    
    try:
        # 发送初始状态
        await send_initial_state(websocket)
        
        # 保持连接
        while True:
            # 心跳检测
            data = await websocket.receive_text()
            
            if data == 'ping':
                await websocket.send_text('pong')
    except WebSocketDisconnect:
        active_connections.discard(websocket)
        _cancel_broadcast_task()


async def send_initial_state(websocket: WebSocket):
    """发送初始状态（含 collaboration，避免前端协作流程空白）"""
    try:
        from .agents import get_agents as get_agents_list
        from .subagents import get_subagents, get_tasks
        from .api_status import get_api_status_list
        from status.status_calculator import format_last_active

        agents = await get_agents_list()
        subagents = await get_subagents()
        api_status = await get_api_status_list()

        for agent in agents:
            if agent.get("lastActiveAt"):
                agent["lastActiveFormatted"] = format_last_active(agent["lastActiveAt"])

        data = {
            'agents': agents,
            'subagents': subagents,
            'apiStatus': api_status,
        }
        # collaboration/tasks/performance 单独获取，失败不影响主数据
        try:
            from .collaboration import get_collaboration
            collab = await get_collaboration()
            data['collaboration'] = collab.model_dump() if hasattr(collab, "model_dump") else collab
        except Exception as e:
            print(f"[WebSocket] collaboration 获取失败: {e}")
        try:
            tasks_result = await get_tasks()
            data['tasks'] = tasks_result.get("tasks", []) if isinstance(tasks_result, dict) else []
        except Exception as e:
            print(f"[WebSocket] tasks 获取失败: {e}")
        try:
            from .performance import get_real_stats
            data['performance'] = await get_real_stats()
        except Exception as e:
            print(f"[WebSocket] performance 获取失败: {e}")
        try:
            from .workflow import list_workflows
            data['workflows'] = await list_workflows()
        except Exception as e:
            print(f"[WebSocket] workflows 获取失败: {e}")

        await websocket.send_json({'type': 'full_state', 'data': data})
    except Exception as e:
        print(f"发送初始状态失败: {e}")


async def broadcast_agent_update(agent_id: str, status: str):
    """广播 Agent 状态更新"""
    if not active_connections:
        return
    
    message = {
        'type': 'agent_update',
        'data': {
            'agentId': agent_id,
            'status': status,
            'timestamp': int(asyncio.get_event_loop().time() * 1000)
        }
    }
    
    await broadcast_message(message)


async def broadcast_subagent_update(run_id: str, agent_id: str, outcome: str):
    """广播子代理状态更新"""
    if not active_connections:
        return
    
    message = {
        'type': 'subagent_update',
        'data': {
            'runId': run_id,
            'agentId': agent_id,
            'outcome': outcome,
            'timestamp': int(asyncio.get_event_loop().time() * 1000)
        }
    }
    
    await broadcast_message(message)


async def broadcast_api_status(provider: str, model: str, status: str):
    """广播 API 状态更新"""
    if not active_connections:
        return
    
    message = {
        'type': 'api_status_update',
        'data': {
            'provider': provider,
            'model': model,
            'status': status,
            'timestamp': int(asyncio.get_event_loop().time() * 1000)
        }
    }
    
    await broadcast_message(message)


async def broadcast_message(message: dict):
    """广播消息到所有连接"""
    disconnected = set()
    
    for connection in active_connections:
        try:
            await connection.send_json(message)
        except:
            disconnected.add(connection)
    
    # 清理断开的连接
    for connection in disconnected:
        active_connections.discard(connection)
    if not active_connections:
        _cancel_broadcast_task()


async def broadcast_full_state():
    """文件变更时广播完整状态（agents、subagents、apiStatus、collaboration、tasks、performance）"""
    if not active_connections:
        return
    try:
        from .agents import get_agents as get_agents_list
        from .subagents import get_subagents
        from .api_status import get_api_status_list
        from .collaboration import get_collaboration
        from .performance import get_real_stats
        from .workflow import list_workflows

        agents = await get_agents_list()
        subagents = await get_subagents()
        api_status = await get_api_status_list()
        collaboration = await get_collaboration()
        performance = await get_real_stats()
        workflows = await list_workflows()

        # tasks 来自 subagents 的 get_tasks
        from .subagents import get_tasks
        tasks_result = await get_tasks()
        tasks = tasks_result.get("tasks", []) if isinstance(tasks_result, dict) else []

        # 格式化 agents 的 lastActiveFormatted
        from status.status_calculator import format_last_active
        for agent in agents:
            if agent.get("lastActiveAt"):
                agent["lastActiveFormatted"] = format_last_active(agent["lastActiveAt"])

        await broadcast_message({
            "type": "full_state",
            "data": {
                "agents": agents,
                "subagents": subagents,
                "apiStatus": api_status,
                "collaboration": collaboration.model_dump() if hasattr(collaboration, "model_dump") else collaboration,
                "tasks": tasks,
                "performance": performance,
                "workflows": workflows,
            },
        })
    except Exception as e:
        print(f"[WebSocket] broadcast_full_state 失败: {e}")


def get_active_connections_count() -> int:
    """获取活跃连接数"""
    return len(active_connections)


@router.get("/connections")
async def get_connections():
    """获取活跃连接数"""
    return {"count": get_active_connections_count()}
