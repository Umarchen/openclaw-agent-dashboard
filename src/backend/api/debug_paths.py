"""
诊断接口 - 路径解析与关键文件检查
用于 Windows 等跨机器环境排查协作流程、模型配置等问题
"""
from fastapi import APIRouter

from core.error_handler import record_error
from core.safe_api_error import safe_client_string

router = APIRouter()


@router.get("/debug/paths")
async def get_debug_paths():
    """
    返回后端当前解析出的 OpenClaw 根目录及关键文件/目录存在性。
    用于跨机器环境（如 Windows）排查协作流程、时序视图、模型列表等问题。
    """
    try:
        from data.config_reader import get_openclaw_root
        root = get_openclaw_root()
    except Exception as e:
        record_error("unknown", str(e), "api:debug_paths", exc=e)
        return {
            "success": False,
            "error": safe_client_string(str(e)),
            "openclawRoot": None,
            "openclawJsonExists": False,
            "agentsDirExists": False,
            "subagentsRunsExists": False,
        }

    openclaw_json = root / "openclaw.json"
    agents_dir = root / "agents"
    subagents_runs = root / "subagents" / "runs.json"

    return {
        "success": True,
        "openclawRoot": str(root),
        "openclawJsonExists": openclaw_json.exists(),
        "agentsDirExists": agents_dir.exists() and agents_dir.is_dir(),
        "subagentsRunsExists": subagents_runs.exists(),
    }
