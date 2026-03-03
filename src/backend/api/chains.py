"""
任务链路 API 路由
"""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from data.chain_reader import (
    build_task_chains,
    get_task_chain,
    get_active_chain,
    get_chains_summary
)

router = APIRouter()


class ChainNode(BaseModel):
    agentId: str
    agentName: str
    role: str
    status: str
    startedAt: Optional[int] = None
    endedAt: Optional[int] = None
    duration: Optional[int] = None
    task: Optional[str] = None
    runId: Optional[str] = None
    input: Optional[str] = None
    output: Optional[str] = None
    artifacts: List[str] = []
    toolCallCount: int = 0
    tokenUsage: Dict[str, int] = {"input": 0, "output": 0}


class ChainEdge(BaseModel):
    from_: str
    to: str


class TaskChain(BaseModel):
    chainId: str
    projectId: Optional[str] = None
    rootTask: str
    startedAt: Optional[int] = None
    status: str
    nodes: List[ChainNode]
    edges: List[Dict[str, str]]
    progress: float
    completedNodes: int
    totalNodes: int
    totalDuration: int


class TaskChainListResponse(BaseModel):
    chains: List[TaskChain]
    activeChain: Optional[TaskChain] = None


class ChainSummaryResponse(BaseModel):
    total: int
    running: int
    completed: int
    error: int
    chains: List[Dict[str, Any]]


@router.get("/chains", response_model=TaskChainListResponse)
async def list_chains(
    limit: int = Query(20, ge=1, le=100, description="返回链路数量")
):
    """
    获取所有任务链路列表

    返回 Agent 间的任务派发链路，包括：
    - 链路中的所有节点（Agent）
    - 节点间的派发关系
    - 各节点的状态和进度
    """
    chains = build_task_chains(limit=limit)
    active = get_active_chain()

    return {
        "chains": chains,
        "activeChain": active
    }


@router.get("/chains/summary", response_model=ChainSummaryResponse)
async def get_summary():
    """
    获取任务链路摘要统计

    快速查看所有链路的状态分布
    """
    return get_chains_summary()


@router.get("/chains/active")
async def get_active():
    """
    获取当前活跃的任务链路

    返回正在执行的任务链
    """
    chain = get_active_chain()
    if not chain:
        return {"activeChain": None, "message": "当前没有正在执行的任务链"}

    return {"activeChain": chain}


@router.get("/chains/{chain_id}")
async def get_chain(chain_id: str):
    """
    获取单个任务链的详情

    返回完整的链路信息，包括所有节点和边
    """
    chain = get_task_chain(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail=f"Chain {chain_id} not found")

    return chain
