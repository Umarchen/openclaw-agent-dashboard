"""
Agent API 路由
"""
import asyncio
import sys
from pathlib import Path
from typing import List, Optional

sys.path.append(str(Path(__file__).parent.parent))

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.input_safety import require_safe_agent_id

from status.status_calculator import (
    get_agents_with_status,
    format_last_active
)

router = APIRouter()


class AgentStatus(BaseModel):
    id: str
    name: str
    role: str
    status: str  # idle/working/down
    currentTask: Optional[str] = None
    lastActiveAt: Optional[int] = None
    lastActiveFormatted: Optional[str] = None
    error: Optional[dict] = None


@router.get("/agents", response_model=List[AgentStatus])
async def get_agents():
    """获取所有 Agent 列表及状态"""
    from core.error_handler import ErrorHandler

    def _load():
        h = ErrorHandler(max_retry=2, base_delay=0.5)
        return h.run_with_retry(
            lambda: get_agents_with_status(),
            operation="get_agents_with_status",
            error_type="io-error",
        )

    agents = await asyncio.to_thread(_load)
    
    # 格式化最后活跃时间
    for agent in agents:
        if agent.get('lastActiveAt'):
            agent['lastActiveFormatted'] = format_last_active(agent['lastActiveAt'])
    
    return agents


@router.get("/agents/{agent_id}", response_model=AgentStatus)
async def get_agent(agent_id: str):
    """获取单个 Agent 详情"""
    require_safe_agent_id(agent_id)
    from core.error_handler import ErrorHandler

    def _load():
        h = ErrorHandler(max_retry=2, base_delay=0.5)
        return h.run_with_retry(
            lambda: get_agents_with_status(),
            operation="get_agents_with_status",
            error_type="io-error",
        )

    agents = await asyncio.to_thread(_load)
    
    from data.config_reader import agent_ids_equal

    for agent in agents:
        if agent_ids_equal(agent['id'], agent_id):
            if agent.get('lastActiveAt'):
                agent['lastActiveFormatted'] = format_last_active(agent['lastActiveAt'])
            return agent
    
    raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


@router.get("/agents/{agent_id}/output")
async def get_agent_output(
    agent_id: str,
    limit: int = Query(50, ge=1, le=500, description="返回最近轮次数上限"),
):
    """
    获取 Agent 最近会话详情：每轮 user/assistant/toolResult 及 usage
    用于调试视图展示
    """
    require_safe_agent_id(agent_id)
    from data.session_reader import get_session_turns
    from data.config_reader import get_agent_config

    if not get_agent_config(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    from core.error_handler import ErrorHandler

    def _load_turns():
        h = ErrorHandler(max_retry=2, base_delay=0.5)
        return h.run_with_retry(
            lambda: get_session_turns(agent_id, limit=limit),
            operation="get_session_turns",
            error_type="io-error",
        )

    turns = await asyncio.to_thread(_load_turns)
    return {"agentId": agent_id, "turns": turns}
