"""
Timeline API 路由 - 实时执行时序图
"""
import logging
import time
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path

LOG = logging.getLogger(__name__)
sys.path.append(str(Path(__file__).parent.parent))

from api.input_safety import require_safe_agent_id, require_safe_session_key
from core.error_handler import record_error
from core.safe_api_error import safe_api_error_detail
from data.timeline_reader import get_timeline_steps, StepType, StepStatus
from data.config_reader import get_agent_config

router = APIRouter()


class TimelineStats(BaseModel):
    totalDuration: int
    totalInputTokens: int
    totalOutputTokens: int
    toolCallCount: int
    stepCount: int


class LLMRound(BaseModel):
    id: str
    index: int
    trigger: str
    triggerBy: Optional[str] = None
    stepIds: List[str] = []
    duration: int = 0
    tokens: Optional[Dict[str, int]] = None


class TimelineResponse(BaseModel):
    sessionId: Optional[str] = None
    agentId: str
    agentName: Optional[str] = None
    model: Optional[str] = None
    startedAt: Optional[int] = None
    runStartedAt: Optional[int] = None
    status: str
    steps: List[Dict[str, Any]]
    stats: TimelineStats
    message: Optional[str] = None
    # 主 Agent 无会话文件时由后端置 True，避免前端误用「子代理」空态文案
    isMainAgent: Optional[bool] = None
    # LLM 轮次分组
    rounds: Optional[List[LLMRound]] = None
    roundMode: Optional[bool] = None
    dataSource: Optional[str] = None


@router.get("/timeline/{agent_id}", response_model=TimelineResponse)
async def get_timeline(
    agent_id: str,
    session_key: Optional[str] = Query(None, description="指定 session key，默认最新"),
    limit: int = Query(100, ge=1, le=500, description="步骤数量限制")
):
    """
    获取 Agent 会话的完整时序数据

    返回用户与 Agent 的交互时序，包括：
    - 用户消息
    - Agent 思考过程 (thinking)
    - 工具调用及结果
    - 错误信息
    """
    require_safe_agent_id(agent_id)
    session_key = require_safe_session_key(session_key)
    agent_info = get_agent_config(agent_id)
    if not agent_info:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    t0 = time.perf_counter()
    try:
        result = get_timeline_steps(agent_id, session_key, limit)
    except Exception as e:
        record_error("unknown", str(e), "api:timeline:get", exc=e)
        raise HTTPException(status_code=500, detail=safe_api_error_detail(e)) from e
    elapsed_ms = (time.perf_counter() - t0) * 1000
    if elapsed_ms >= 200.0:
        LOG.info(
            "timeline agent=%s limit=%d steps=%d ms=%.1f",
            agent_id,
            limit,
            len(result.get("steps", [])),
            elapsed_ms,
        )

    # 补充 Agent 信息
    result['agentName'] = agent_info.get('name', agent_id)

    # 处理 model 字段：可能是字符串或字典
    model_info = agent_info.get('model', 'unknown')
    if isinstance(model_info, dict):
        result['model'] = model_info.get('primary', 'unknown')
    else:
        result['model'] = model_info

    return result


@router.get("/timeline/{agent_id}/steps")
async def get_timeline_steps_only(
    agent_id: str,
    session_key: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    step_type: Optional[str] = Query(None, description="过滤步骤类型: user, thinking, toolCall, toolResult, error")
):
    """
    获取时序步骤（简化版，只返回步骤列表）

    可按步骤类型过滤
    """
    require_safe_agent_id(agent_id)
    session_key = require_safe_session_key(session_key)
    if not get_agent_config(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    try:
        result = get_timeline_steps(agent_id, session_key, limit)
    except Exception as e:
        record_error("unknown", str(e), "api:timeline:steps", exc=e)
        raise HTTPException(status_code=500, detail=safe_api_error_detail(e)) from e
    steps = result.get('steps', [])

    # 类型过滤
    if step_type:
        steps = [s for s in steps if s.get('type') == step_type]

    return {"steps": steps, "count": len(steps)}


@router.get("/timeline/{agent_id}/summary")
async def get_timeline_summary(agent_id: str, session_key: Optional[str] = Query(None)):
    """
    获取时序摘要统计

    快速查看会话概览，不返回详细步骤
    """
    require_safe_agent_id(agent_id)
    session_key = require_safe_session_key(session_key)
    if not get_agent_config(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")

    try:
        result = get_timeline_steps(agent_id, session_key, limit=10)  # 只需基本信息
    except Exception as e:
        record_error("unknown", str(e), "api:timeline:summary", exc=e)
        raise HTTPException(status_code=500, detail=safe_api_error_detail(e)) from e

    # 统计各类型步骤数量
    steps = result.get('steps', [])
    type_counts = {}
    for step in steps:
        t = step.get('type', 'unknown')
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "agentId": agent_id,
        "sessionId": result.get('sessionId'),
        "status": result.get('status'),
        "stats": result.get('stats'),
        "typeCounts": type_counts
    }
