"""
OpenClaw Agent Dashboard - 主入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import asyncio


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时启动文件监听，关闭时停止"""
    loop = asyncio.get_running_loop()
    try:
        from watchers.file_watcher import start_file_watcher
        start_file_watcher(loop)
    except Exception as e:
        print(f"[Main] 文件监听启动失败: {e}")
    yield
    try:
        from watchers.file_watcher import stop_file_watcher
        stop_file_watcher()
    except Exception:
        pass


# 创建 FastAPI 应用
app = FastAPI(
    lifespan=lifespan,
    title="OpenClow Agent Dashboard",
    description="多 Agent 可视化看板 API",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 导入路由（必须在 StaticFiles 之前注册，否则 /api 会被静态服务拦截）
import sys
sys.path.append(str(Path(__file__).parent))

from api import agents, subagents, workflow, api_status, websocket, performance, collaboration, agents_config

# 注册 API 路由
app.include_router(agents.router, prefix="/api", tags=["agents"])
app.include_router(agents_config.router, prefix="/api", tags=["agents-config"])
app.include_router(subagents.router, prefix="/api", tags=["subagents"])
app.include_router(workflow.router, prefix="/api", tags=["workflow"])
app.include_router(api_status.router, prefix="/api", tags=["api-status"])
app.include_router(websocket.router, tags=["websocket"])
app.include_router(performance.router, prefix="/api", tags=["performance"])
app.include_router(collaboration.router, prefix="/api", tags=["collaboration"])


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}


@app.get("/api/config")
async def get_config():
    """获取 Dashboard 配置（mainAgentId 等，便于前端自适应）"""
    try:
        from data.config_reader import get_main_agent_id
        return {"mainAgentId": get_main_agent_id()}
    except Exception:
        return {"mainAgentId": "main"}


# 前端静态文件（必须放在 API 路由之后，否则会拦截 /api 请求）
# 插件形态：dashboard/ 与 frontend-dist/ 同级；开发形态：src/backend/ 与 frontend/dist 同级
_plugin_frontend = Path(__file__).parent.parent / "frontend-dist"
_dev_frontend = Path(__file__).parent.parent.parent / "frontend" / "dist"
frontend_dist = _plugin_frontend if _plugin_frontend.exists() else _dev_frontend
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
