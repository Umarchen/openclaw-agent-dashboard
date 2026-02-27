"""
API Status 路由
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from status.error_detector import get_api_status
import time

router = APIRouter()


class ApiStatus(BaseModel):
    provider: str
    model: str
    status: str  # healthy/degraded/down
    lastError: Optional[dict] = None
    errorCount: int = 0


def parse_provider(model: str) -> str:
    """从模型名解析服务商"""
    if model.startswith('glm'):
        return 'zhipu'
    elif model.startswith('qwen'):
        return 'qwen'
    elif model.startswith('kimi'):
        return 'moonshot'
    else:
        return 'unknown'


@router.get("/api-status", response_model=List[ApiStatus])
async def get_api_status_list():
    """获取 API 状态"""
    statuses = get_api_status()
    
    result = []
    for status in statuses:
        model = status['model']
        provider = parse_provider(model)
        
        result.append({
            'provider': provider,
            'model': model,
            'status': status['status'],
            'lastError': status.get('lastError'),
            'errorCount': status.get('errorCount', 0)
        })
    
    return result
