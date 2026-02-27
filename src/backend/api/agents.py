"""
Agent API 路由
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

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
    agents = get_agents_with_status()
    
    # 格式化最后活跃时间
    for agent in agents:
        if agent.get('lastActiveAt'):
            agent['lastActiveFormatted'] = format_last_active(agent['lastActiveAt'])
    
    return agents


@router.get("/agents/{agent_id}", response_model=AgentStatus)
async def get_agent(agent_id: str):
    """获取单个 Agent 详情"""
    agents = get_agents_with_status()
    
    for agent in agents:
        if agent['id'] == agent_id:
            if agent.get('lastActiveAt'):
                agent['lastActiveFormatted'] = format_last_active(agent['lastActiveAt'])
            return agent
    
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
