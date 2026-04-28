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
    probe_stop = None
    try:
        from watchers.file_watcher import start_file_watcher
        from core.config_fortify import get_fortify_config

        start_file_watcher(loop)
        cfg = get_fortify_config()
        if cfg.cache_preload:
            try:
                from status.status_calculator import get_agents_with_status

                get_agents_with_status()
            except Exception as e:
                from core.error_handler import record_error

                record_error("unknown", str(e), "main:cache_preload", exc=e)
        from status.cache_fp_probe import start_cache_fp_probe_background

        probe_stop = start_cache_fp_probe_background()
    except Exception as e:
        from core.error_handler import record_error

        record_error("unknown", str(e), "main:file_watcher_start", exc=e)
    yield
    try:
        if probe_stop is not None:
            probe_stop.set()
        from watchers.file_watcher import stop_file_watcher

        stop_file_watcher()
    except Exception:
        pass


# 创建 FastAPI 应用
app = FastAPI(
    lifespan=lifespan,
    title="OpenClaw Agent Dashboard",
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

from api import agents, subagents, websocket, performance, collaboration, agents_config, errors, timeline, chains, agent_config_api, error_analysis, debug_paths, version, fortify_routes

# 注册 API 路由
app.include_router(agents.router, prefix="/api", tags=["agents"])
app.include_router(errors.router, prefix="/api", tags=["errors"])
app.include_router(fortify_routes.router, prefix="/api", tags=["fortify"])
app.include_router(agents_config.router, prefix="/api", tags=["agents-config"])
app.include_router(subagents.router, prefix="/api", tags=["subagents"])
app.include_router(websocket.router, tags=["websocket"])
app.include_router(performance.router, prefix="/api", tags=["performance"])
app.include_router(collaboration.router, prefix="/api", tags=["collaboration"])
app.include_router(timeline.router, prefix="/api", tags=["timeline"])
app.include_router(chains.router, prefix="/api", tags=["chains"])
app.include_router(agent_config_api.router, prefix="/api", tags=["agent-config"])
app.include_router(error_analysis.router, prefix="/api", tags=["error-analysis"])
app.include_router(debug_paths.router, prefix="/api", tags=["debug"])
app.include_router(version.router, prefix="/api", tags=["version"])


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
