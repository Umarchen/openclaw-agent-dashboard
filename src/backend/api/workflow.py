"""
Workflow API 路由
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
import os

router = APIRouter()


def _get_project_root() -> Path:
    """获取项目根目录，支持环境变量配置"""
    env_root = os.environ.get("VRT_PROJECTS_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    # 默认使用 ~/vrt-projects
    return Path.home() / "vrt-projects"


# 项目根目录
PROJECT_ROOT = _get_project_root()


class WorkflowStatus(BaseModel):
    projectId: str
    projectName: str
    stages: dict
    currentStage: Optional[str] = None
    artifacts: List[str] = []


class WorkflowStage(BaseModel):
    name: str
    status: str  # pending/in-progress/done


def get_workflow_state(project_id: str) -> Optional[dict]:
    """获取项目工作流状态"""
    workflow_file = PROJECT_ROOT / f"projects/{project_id}/.staging/workflow_state.json"
    
    if not workflow_file.exists():
        return None
    
    import json
    with open(workflow_file, 'r', encoding='utf-8') as f:
        return json.load(f)


@router.get("/workflow/{project_id}", response_model=WorkflowStatus)
async def get_workflow(project_id: str):
    """获取项目工作流状态"""
    workflow_state = get_workflow_state(project_id)
    
    if not workflow_state:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Workflow for {project_id} not found")
    
    return {
        'projectId': project_id,
        'projectName': project_id,
        'stages': workflow_state.get('stages', {}),
        'currentStage': workflow_state.get('currentStage'),
        'artifacts': workflow_state.get('artifacts', [])
    }


@router.get("/workflows", response_model=List[dict])
async def list_workflows():
    """列出所有项目的工作流状态"""
    projects_dir = PROJECT_ROOT / "projects"
    
    if not projects_dir.exists():
        return []
    
    workflows = []
    
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            project_id = project_dir.name
            workflow_state = get_workflow_state(project_id)
            
            if workflow_state:
                workflows.append({
                    'projectId': project_id,
                    'projectName': project_id,
                    'stages': workflow_state.get('stages', {}),
                    'currentStage': workflow_state.get('currentStage')
                })
    
    return workflows
