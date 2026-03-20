"""
版本信息 API 路由

提供 GET /api/version 端点，返回插件版本信息。
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

# 导入版本信息读取器
from data.version_info_reader import get_version_reader

router = APIRouter()


class VersionInfo(BaseModel):
    """版本信息数据模型"""
    version: str  # 版本号，如 "1.0.10"
    name: str  # 插件名称
    description: str  # 插件描述
    build_date: Optional[str] = None  # 构建时间（可选）
    git_commit: Optional[str] = None  # Git 提交哈希（可选）


@router.get("/version", response_model=VersionInfo)
async def get_version_info() -> VersionInfo:
    """
    获取插件版本信息
    
    Returns:
        VersionInfo: 包含版本号、名称、描述等信息的对象
    """
    reader = get_version_reader()
    version_data = reader.read_version_info()
    return VersionInfo(**version_data)
