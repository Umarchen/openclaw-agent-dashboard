"""
WebSocket 路由
C0 改造: 移除 _periodic_broadcast_loop 和 broadcast_full_state，
新增 EventBus subscriber 监听 agent_state_changed 进行增量 WS 推送。
bootstrap（send_initial_state）保留，仍推 type:"full_state" 旧格式。
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set, List, Dict, Any
import json
import asyncio
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from core.error_handler import record_error
from core.event_types import BaseEvent, AgentStateChangedEvent

router = APIRouter()

# 活跃的 WebSocket 连接
active_connections: Set[WebSocket] = set()

# C0: EventBus subscriber 控制标志
_event_bus_subscribed = False


def _ensure_event_bus_subscriber() -> None:
    """确保 EventBus subscriber 已注册（仅注册一次）"""
    global _event_bus_subscribed
    if _event_bus_subscribed:
        return
    try:
        from core.event_bus import get_event_bus, TOPIC_AGENT_STATE_CHANGED

        bus = get_event_bus()
        bus.subscribe(TOPIC_AGENT_STATE_CHANGED, _on_agent_state_changed)
        _event_bus_subscribed = True
    except Exception as e:
        record_error("unknown", str(e), "websocket:event_bus_subscribe", exc=e)


def _on_agent_state_changed(event: BaseEvent) -> None:
    """EventBus 回调: AgentStateChangedEvent → WS 增量推送

    This runs in the publisher's thread (EventBus uses synchronous dispatch).
    We use asyncio.run_coroutine_threadsafe to schedule the WS push on the event loop.
    """
    if not isinstance(event, AgentStateChangedEvent):
        return

    if not active_connections:
        return

    payload = event.to_ws_payload()

    # Schedule WS push on the event loop
    loop = _get_event_loop()
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(_do_broadcast(payload), loop)


def _get_event_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点"""
    await websocket.accept()
    active_connections.add(websocket)

    # C0: 确保 EventBus subscriber 已注册
    _ensure_event_bus_subscriber()

    try:
        # 发送初始状态（bootstrap，保留 type:"full_state"）
        await send_initial_state(websocket)

        # 保持连接
        while True:
            # 心跳检测（同时支持纯文本 ping 和 JSON 格式）
            data = await websocket.receive_text()

            is_ping = False
            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and msg.get('type') == 'ping':
                    is_ping = True
            except json.JSONDecodeError:
                if data == 'ping':
                    is_ping = True

            if is_ping:
                await websocket.send_json({'type': 'pong', 'timestamp': int(asyncio.get_event_loop().time() * 1000)})
    except WebSocketDisconnect:
        active_connections.discard(websocket)


async def send_initial_state(websocket: WebSocket):
    """发送初始状态（bootstrap，保留 type:"full_state"）"""
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
            record_error("unknown", str(e), "websocket:initial_collaboration", exc=e)
        try:
            tasks_result = await get_tasks()
            data['tasks'] = tasks_result.get("tasks", []) if isinstance(tasks_result, dict) else []
        except Exception as e:
            record_error("unknown", str(e), "websocket:initial_tasks", exc=e)
        try:
            from .performance import get_real_stats
            data['performance'] = await get_real_stats()
        except Exception as e:
            record_error("unknown", str(e), "websocket:initial_performance", exc=e)
        try:
            from .workflow import list_workflows
            data['workflows'] = await list_workflows()
        except Exception as e:
            record_error("unknown", str(e), "websocket:initial_workflows", exc=e)

        await websocket.send_json({'type': 'full_state', 'data': data})
    except Exception as e:
        record_error("unknown", str(e), "websocket:send_initial_state", exc=e)


async def broadcast_agent_update(agent_id: str, status: str):
    """广播 Agent 状态更新（兼容旧接口）"""
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

    await _do_broadcast(message)


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

    await _do_broadcast(message)


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

    await _do_broadcast(message)


async def _do_broadcast(message: dict):
    """广播消息到所有连接（内部方法）"""
    disconnected = set()

    for connection in active_connections:
        try:
            await connection.send_json(message)
        except:
            disconnected.add(connection)

    # 清理断开的连接
    for connection in disconnected:
        active_connections.discard(connection)


def get_active_connections_count() -> int:
    """获取活跃连接数"""
    return len(active_connections)


@router.get("/connections")
async def get_connections():
    """获取活跃连接数"""
    return {"count": get_active_connections_count()}
