"""
Agent API 路由
"""
from fastapi import APIRouter, HTTPException
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
    
    raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


class TimelineContextResponse(BaseModel):
    """供「实时执行时序」与 runs.json 对齐：使用最新 run 的 childSessionKey 解析独立会话。"""
    childSessionKey: Optional[str] = None


@router.get("/agents/{agent_id}/timeline-context", response_model=TimelineContextResponse)
async def get_agent_timeline_context(agent_id: str):
    """
    返回该 Agent 在 runs.json 中最近一条 run 的 childSessionKey（若有）。
    前端传给 GET /api/timeline/{agent_id}?session_key= 以命中 sessions.json 指定 jsonl，
    避免仅靠 mtime 选文件或误扫主会话合并路径。
    """
    from data.config_reader import get_agents_list
    from data.subagent_reader import get_agent_runs

    agents = get_agents_list()
    if not any(a.get("id") == agent_id for a in agents):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    runs = get_agent_runs(agent_id, limit=1)
    key = None
    if runs:
        key = runs[0].get("childSessionKey") or None
        if isinstance(key, str) and not key.strip():
            key = None
    return TimelineContextResponse(childSessionKey=key)


@router.get("/agents/{agent_id}/output")
async def get_agent_output(agent_id: str, limit: int = 50):
    """
    获取 Agent 最近会话详情：每轮 user/assistant/toolResult 及 usage
    用于调试视图展示
    """
    from data.session_reader import get_session_turns
    from data.config_reader import get_agents_list
    
    agents = get_agents_list()
    if not any(a.get('id') == agent_id for a in agents):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    turns = get_session_turns(agent_id, limit=limit)
    return {"agentId": agent_id, "turns": turns}
