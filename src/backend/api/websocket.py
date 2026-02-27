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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点"""
    await websocket.accept()
    active_connections.add(websocket)
    
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
        active_connections.remove(websocket)


async def send_initial_state(websocket: WebSocket):
    """发送初始状态"""
    try:
        # 获取 Agent 状态
        from .agents import get_agents as get_agents_list
        from .subagents import get_subagents
        from .api_status import get_api_status_list
        
        # 获取 Agent 状态
        agents = await get_agents_list()
        
        # 获取子代理状态
        subagents = await get_subagents()
        
        # 获取 API 状态
        api_status = await get_api_status_list()
        
        # 发送完整状态
        await websocket.send_json({
            'type': 'full_state',
            'data': {
                'agents': agents,
                'subagents': subagents,
                'apiStatus': api_status
            }
        })
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
        active_connections.remove(connection)


def get_active_connections_count() -> int:
    """获取活跃连接数"""
    return len(active_connections)


@router.get("/connections")
async def get_connections():
    """获取活跃连接数"""
    return {"count": get_active_connections_count()}
