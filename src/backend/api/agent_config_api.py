"""
Agent 配置 API - 提供配置读取和修改接口
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from data.agent_config_manager import (
    get_agent_full_info,
    get_all_agents_info,
    get_all_available_models,
    update_agent_model,
    get_agent_model_config,
)

router = APIRouter()


class UpdateModelRequest(BaseModel):
    primary: Optional[str] = None
    fallbacks: Optional[List[str]] = None


@router.get("/agent-config")
async def list_agent_configs():
    """获取所有 Agent 配置概览"""
    try:
        agents = get_all_agents_info()
        return {
            'agents': agents,
            'total': len(agents),
        }
    except Exception as e:
        return {'agents': [], 'total': 0, 'error': str(e)}


@router.get("/agent-config/{agent_id}")
async def get_agent_config(agent_id: str):
    """获取单个 Agent 的详细配置"""
    try:
        info = get_agent_full_info(agent_id)
        if not info.get('found'):
            raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
        return info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/agent-config/{agent_id}/model")
async def update_agent_model_config(agent_id: str, request: UpdateModelRequest):
    """更新 Agent 的模型配置"""
    try:
        result = update_agent_model(
            agent_id,
            primary=request.primary,
            fallbacks=request.fallbacks
        )
        if not result.get('success'):
            raise HTTPException(
                status_code=400,
                detail=result.get('error', 'Failed to update model config')
            )
        return {
            'success': True,
            'agent_id': agent_id,
            'model': get_agent_model_config(agent_id),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/available-models")
async def list_available_models():
    """获取所有可用模型列表"""
    try:
        models = get_all_available_models()
        return {
            'models': models,
            'total': len(models),
        }
    except Exception as e:
        return {'models': [], 'total': 0, 'error': str(e)}
