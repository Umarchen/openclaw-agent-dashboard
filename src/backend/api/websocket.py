"""
WebSocket 路由
C0: 移除 _periodic_broadcast_loop 和 broadcast_full_state，
新增 EventBus subscriber 监听 agent_state_changed 进行增量 WS 推送。
bootstrap（send_initial_state）保留，仍推 type:"full_state" 旧格式。

C1: 新增 schemaVersion 协商和 FullStateSnapshot 支持。
向后兼容：无 hello 的客户端仍收到 type:"full_state"（旧格式）。

C2: FullStateSnapshot 瘦身（仅 agents/subagents/apiStatus），
新增 CollaborationChanged/TaskChanged/PerformanceSnapshot WS 广播。
collaboration/tasks/performance/workflows 通过独立 C2 事件交付。
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set, List, Dict, Any, Optional
import json
import asyncio
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from core.error_handler import record_error
from core.event_types import BaseEvent, AgentStateChangedEvent, FullStateSnapshotEvent, CollaborationChangedEvent, TaskChangedEvent, PerformanceSnapshotEvent

router = APIRouter()

# 活跃的 WebSocket 连接
active_connections: Set[WebSocket] = set()

# C0: EventBus subscriber 控制标志
_event_bus_subscribed = False

# C2: C2 event subscriber control flags
_collab_subscribed = False
_task_subscribed = False
_perf_subscribed = False

# C1: schemaVersion negotiation timeout (seconds)
_HELLO_TIMEOUT_SEC = 3.0


def _ensure_event_bus_subscriber() -> None:
    """确保 EventBus subscriber 已注册（仅注册一次）"""
    global _event_bus_subscribed
    if _event_bus_subscribed:
        return
    try:
        from core.event_bus import get_event_bus, TOPIC_AGENT_STATE_CHANGED

        bus = get_event_bus()
        bus.subscribe(TOPIC_AGENT_STATE_CHANGED, _on_agent_state_changed)
        _event_bus_subscribed = True
    except Exception as e:
        record_error("unknown", str(e), "websocket:event_bus_subscribe", exc=e)


def _ensure_c2_subscribers() -> None:
    """确保 C2 事件 subscriber 已注册（仅注册一次）"""
    global _collab_subscribed, _task_subscribed, _perf_subscribed
    try:
        from core.event_bus import get_event_bus, TOPIC_COLLABORATION_CHANGED, TOPIC_TASK_CHANGED, TOPIC_PERFORMANCE_SNAPSHOT

        bus = get_event_bus()

        if not _collab_subscribed:
            bus.subscribe(TOPIC_COLLABORATION_CHANGED, _on_collaboration_changed)
            _collab_subscribed = True

        if not _task_subscribed:
            bus.subscribe(TOPIC_TASK_CHANGED, _on_task_changed)
            _task_subscribed = True

        if not _perf_subscribed:
            bus.subscribe(TOPIC_PERFORMANCE_SNAPSHOT, _on_performance_snapshot)
            _perf_subscribed = True

        _LOG.info("C2 WS subscribers registered (collab, task, perf)")
    except Exception as e:
        record_error("unknown", str(e), "websocket:c2_subscribe", exc=e)


def _get_event_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_schema_version() -> int:
    """Get the server's current schema version from config."""
    try:
        from core.config_fortify import get_fortify_config
        cfg = get_fortify_config()
        return getattr(cfg, "ecs_full_state_schema_version", 2)
    except Exception:
        return 2


async def _collect_full_state_data() -> Dict[str, Any]:
    """Collect all sub-domain data for full state / FullStateSnapshot."""
    try:
        from .agents import get_agents as get_agents_list
        from .subagents import get_subagents, get_tasks
        from status.status_calculator import format_last_active
    except ImportError:
        return {}

    api_status = []
    try:
        from .api_status import get_api_status_list
        api_status = await get_api_status_list()
    except ImportError:
        pass

    agents = await get_agents_list()
    subagents = await get_subagents()

    for agent in agents:
        if agent.get("lastActiveAt"):
            agent["lastActiveFormatted"] = format_last_active(agent["lastActiveAt"])

    data: Dict[str, Any] = {
        'agents': agents,
        'subagents': subagents,
        'apiStatus': api_status,
    }

    # collaboration/tasks/performance 单独获取，失败不影响主数据
    try:
        from .collaboration import get_collaboration
        collab = await get_collaboration()
        data['collaboration'] = collab.model_dump() if hasattr(collab, "model_dump") else collab
    except Exception as e:
        record_error("unknown", str(e), "websocket:initial_collaboration", exc=e)
    try:
        tasks_result = await get_tasks()
        data['tasks'] = tasks_result.get("tasks", []) if isinstance(tasks_result, dict) else []
    except Exception as e:
        record_error("unknown", str(e), "websocket:initial_tasks", exc=e)
    try:
        from .performance import get_real_stats
        data['performance'] = await get_real_stats()
    except Exception as e:
        record_error("unknown", str(e), "websocket:initial_performance", exc=e)
    try:
        from .workflow import list_workflows
        data['workflows'] = await list_workflows()
    except Exception as e:
        record_error("unknown", str(e), "websocket:initial_workflows", exc=e)

    return data


def _on_agent_state_changed(event: BaseEvent) -> None:
    """EventBus 回调: AgentStateChangedEvent → WS 增量推送

    This runs in the publisher's thread (EventBus uses synchronous dispatch).
    We use asyncio.run_coroutine_threadsafe to schedule the WS push on the event loop.
    """
    if not isinstance(event, AgentStateChangedEvent):
        return

    if not active_connections:
        return

    payload = event.to_ws_payload()

    # Schedule WS push on the event loop
    loop = _get_event_loop()
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(_do_broadcast(payload), loop)


def _on_collaboration_changed(event: BaseEvent) -> None:
    """C2: EventBus callback: CollaborationChangedEvent → WS broadcast."""
    if not isinstance(event, CollaborationChangedEvent):
        return
    if not active_connections:
        return
    payload = event.to_ws_payload()
    loop = _get_event_loop()
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(_do_broadcast(payload), loop)


def _on_task_changed(event: BaseEvent) -> None:
    """C2: EventBus callback: TaskChangedEvent → WS broadcast."""
    if not isinstance(event, TaskChangedEvent):
        return
    if not active_connections:
        return
    payload = event.to_ws_payload()
    loop = _get_event_loop()
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(_do_broadcast(payload), loop)


def _on_performance_snapshot(event: BaseEvent) -> None:
    """C2: EventBus callback: PerformanceSnapshotEvent → WS broadcast."""
    if not isinstance(event, PerformanceSnapshotEvent):
        return
    if not active_connections:
        return
    payload = event.to_ws_payload()
    loop = _get_event_loop()
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(_do_broadcast(payload), loop)


async def _send_full_state_legacy(websocket: WebSocket) -> None:
    """Send type:'full_state' (C0 legacy format) for backward compatibility.

    Used when client doesn't send hello within timeout.
    """
    try:
        data = await _collect_full_state_data()
        await websocket.send_json({'type': 'full_state', 'data': data})
    except Exception as e:
        record_error("unknown", str(e), "websocket:send_full_state_legacy", exc=e)


async def _send_full_state_snapshot(websocket: WebSocket, trigger: str = "bootstrap") -> None:
    """Send type:'FullStateSnapshot' (C1+ new format).

    C2 slimmed: only includes agents, subagents, apiStatus.
    collaboration/tasks/performance/workflows are delivered via independent C2 events.

    Used when client sends hello with matching schemaVersion.
    """
    try:
        data = await _collect_slim_full_state_data()
        schema_ver = _get_schema_version()
        message = {
            'type': 'FullStateSnapshot',
            'payload': data,
            'schemaVersion': schema_ver,
            'timestamp': _now_iso(),
        }
        # Record metric
        _record_full_state_metric(trigger)
        await websocket.send_json(message)
    except Exception as e:
        record_error("unknown", str(e), "websocket:send_full_state_snapshot", exc=e)


async def _collect_slim_full_state_data() -> Dict[str, Any]:
    """Collect slimmed full state data for C2 FullStateSnapshot.

    C2 slimmed format: only agents, subagents, apiStatus.
    collaboration/tasks/performance/workflows removed — delivered via C2 events.
    """
    try:
        from .agents import get_agents as get_agents_list
        from .subagents import get_subagents
        from status.status_calculator import format_last_active
    except ImportError:
        return {}

    api_status = []
    try:
        from .api_status import get_api_status_list
        api_status = await get_api_status_list()
    except ImportError:
        pass

    agents = await get_agents_list()
    subagents = await get_subagents()

    for agent in agents:
        if agent.get("lastActiveAt"):
            agent["lastActiveFormatted"] = format_last_active(agent["lastActiveAt"])

    data: Dict[str, Any] = {
        'agents': agents,
        'subagents': subagents,
        'apiStatus': api_status,
    }

    return data


async def _record_full_state_metric(trigger: str) -> None:
    """Record full_state / FullStateSnapshot push metric."""
    try:
        from core.metrics_collector import get_metrics
        metrics = get_metrics()
        metrics.increment("dashboard_full_state_total")
    except Exception:
        pass


async def _send_state_update_to_ws(event: AgentStateChangedEvent) -> None:
    """Send AgentStateChanged as C1+ type:'AgentStateChanged' with proper frame format."""
    if not active_connections:
        return

    message = {
        'type': 'AgentStateChanged',
        'payload': {
            'agent_id': event.agent_id,
            'diffs': [
                {'field': field, 'changed': changed}
                for field, changed in event.changes.items()
            ],
            'version': 0,  # placeholder; StateStore version tracked separately in C1
            'timestamp': _now_iso(),
        },
        'timestamp': _now_iso(),
    }

    # Record metric
    try:
        from core.metrics_collector import get_metrics
        metrics = get_metrics()
        metrics.increment("dashboard_state_update_total")
    except Exception:
        pass

    # Record payload size metric
    try:
        payload_bytes = len(json.dumps(message).encode('utf-8'))
        from core.metrics_collector import get_metrics
        metrics = get_metrics()
        metrics.record_latency("dashboard_ws_payload_bytes", float(payload_bytes))
    except Exception:
        pass

    await _do_broadcast(message)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点 — C1: supports schemaVersion negotiation.

    Handshake flow:
    1. Accept connection
    2. Wait up to 3s for client hello message
    3. If hello received with schemaVersion:
       - If schemaVersion matches server: send FullStateSnapshot, then ready
       - If mismatch: send FullStateSnapshot (forces client to re-sync)
    4. If no hello within timeout: send type:'full_state' (legacy, backward compatible)
    5. Enter message receive loop
    """
    await websocket.accept()
    active_connections.add(websocket)

    # C0: 确保 EventBus subscriber 已注册
    _ensure_event_bus_subscriber()

    # C1: Register FullStateSnapshot subscriber on EventBus (if not already)
    _ensure_full_state_snapshot_subscriber()

    # C2: Register C2 event subscribers (CollaborationChanged, TaskChanged, PerformanceSnapshot)
    _ensure_c2_subscribers()

    try:
        # C1: schemaVersion negotiation
        hello_received = False
        client_schema_version: Optional[int] = None

        try:
            # Wait for hello message with timeout
            raw = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=_HELLO_TIMEOUT_SEC,
            )
            try:
                msg = json.loads(raw)
                if isinstance(msg, dict) and msg.get('type') == 'hello':
                    hello_received = True
                    client_schema_version = msg.get('schemaVersion')
                    _LOG.info(
                        "Client hello: schemaVersion=%s",
                        client_schema_version,
                    )
            except (json.JSONDecodeError, TypeError):
                pass
        except asyncio.TimeoutError:
            _LOG.debug("No hello received within timeout, using legacy full_state")

        if hello_received and client_schema_version is not None:
            # C1+: Send FullStateSnapshot (new format)
            server_version = _get_schema_version()
            if client_schema_version != server_version:
                trigger = "schema_mismatch"
            else:
                trigger = "bootstrap"
            await _send_full_state_snapshot(websocket, trigger=trigger)
        else:
            # Backward compatible: send type:'full_state' (legacy format)
            await _send_full_state_legacy(websocket)
            # Record metric for legacy bootstrap too
            _record_full_state_metric("bootstrap")

        # 保持连接
        while True:
            data = await websocket.receive_text()

            is_ping = False
            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and msg.get('type') == 'ping':
                    is_ping = True
            except json.JSONDecodeError:
                if data == 'ping':
                    is_ping = True

            if is_ping:
                await websocket.send_json({'type': 'pong', 'timestamp': int(asyncio.get_event_loop().time() * 1000)})
    except WebSocketDisconnect:
        active_connections.discard(websocket)


# ── FullStateSnapshot EventBus subscriber (C1) ────────────────────

_full_state_snapshot_subscribed = False


def _ensure_full_state_snapshot_subscriber() -> None:
    """Register WS FullStateSnapshot broadcaster on EventBus."""
    global _full_state_snapshot_subscribed
    if _full_state_snapshot_subscribed:
        return
    try:
        from core.event_bus import get_event_bus, TOPIC_STATE_UPDATES
        bus = get_event_bus()
        bus.subscribe(TOPIC_STATE_UPDATES, _on_full_state_snapshot_event)
        _full_state_snapshot_subscribed = True
    except Exception as e:
        record_error("unknown", str(e), "websocket:full_snapshot_subscribe", exc=e)


def _on_full_state_snapshot_event(event: BaseEvent) -> None:
    """Handle FullStateSnapshotEvent from EventBus → broadcast to all WS clients."""
    if not isinstance(event, FullStateSnapshotEvent):
        return

    if not active_connections:
        return

    message = {
        'type': 'FullStateSnapshot',
        'payload': event.data,
        'schemaVersion': event.schema_version,
        'timestamp': _now_iso(),
    }

    _record_full_state_metric_sync(event.trigger)

    loop = _get_event_loop()
    if loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(_do_broadcast(message), loop)


def _record_full_state_metric_sync(trigger: str) -> None:
    """Synchronous version of metric recording (called from EventBus thread)."""
    try:
        from core.metrics_collector import get_metrics
        metrics = get_metrics()
        metrics.increment("dashboard_full_state_total")
    except Exception:
        pass


async def send_initial_state(websocket: WebSocket):
    """发送初始状态 — backward compatible (type:'full_state').

    This function is retained for any code paths that need the legacy format.
    For new WS connections, websocket_endpoint handles the schemaVersion negotiation.
    """
    await _send_full_state_legacy(websocket)


async def broadcast_agent_update(agent_id: str, status: str):
    """广播 Agent 状态更新（兼容旧接口）"""
    if not active_connections:
        return

    message = {
        'type': 'agent_update',
        'data': {
            'agentId': agent_id,
            'status': status,
            'timestamp': int(asyncio.get_event_loop().time() * 1000)
        }
    }

    await _do_broadcast(message)


async def broadcast_subagent_update(run_id: str, agent_id: str, outcome: str):
    """广播子代理状态更新"""
    if not active_connections:
        return

    message = {
        'type': 'subagent_update',
        'data': {
            'runId': run_id,
            'agentId': agent_id,
            'outcome': outcome,
            'timestamp': int(asyncio.get_event_loop().time() * 1000)
        }
    }

    await _do_broadcast(message)


async def broadcast_api_status(provider: str, model: str, status: str):
    """广播 API 状态更新"""
    if not active_connections:
        return

    message = {
        'type': 'api_status_update',
        'data': {
            'provider': provider,
            'model': model,
            'status': status,
            'timestamp': int(asyncio.get_event_loop().time() * 1000)
        }
    }

    await _do_broadcast(message)


async def _do_broadcast(message: dict):
    """广播消息到所有连接（内部方法）"""
    disconnected = set()

    for connection in active_connections:
        try:
            await connection.send_json(message)
        except:
            disconnected.add(connection)

    # 清理断开的连接
    for connection in disconnected:
        active_connections.discard(connection)


def get_active_connections_count() -> int:
    """获取活跃连接数"""
    return len(active_connections)


@router.get("/connections")
async def get_connections():
    """获取活跃连接数"""
    return {"count": get_active_connections_count()}


# Module-level logger
import logging
_LOG = logging.getLogger(__name__)
