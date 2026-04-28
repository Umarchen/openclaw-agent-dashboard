"""
机制追踪 API - Memory/Skill/Channel/Heartbeat/Cron
"""
from fastapi import APIRouter
from typing import List, Dict, Any
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

router = APIRouter()


@router.get("/mechanisms")
async def get_mechanisms():
    """获取所有 Agent 的机制使用情况"""
    from mechanism_reader import get_all_agents_mechanisms
    return get_all_agents_mechanisms()


@router.get("/mechanisms/{agent_id}")
async def get_agent_mechanisms(agent_id: str):
    """获取单个 Agent 的机制使用情况"""
    from mechanism_reader import get_agent_mechanisms
    from data.config_reader import get_agent_config

    if not get_agent_config(agent_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    return get_agent_mechanisms(agent_id)
