# openclaw-agent-dashboard ECS 架构设计

> **项目名称**: openclaw-agent-dashboard  
> **特性标识**: ECS (Event-Driven ChangeStream)  
> **版本**: v1.1.0  
> **编写日期**: 2026-05-28  
> **修订日期**: 2026-05-28  
> **编写人员**: 架构师 (SA)  
> **项目模式**: 🟠 增量模式 (Incremental) — 存量系统架构改造

---

## 修订记录

| 版本 | 日期 | 修订要点 |
|------|------|----------|
| v1.1.0 | 2026-05-28 | **评审后修订** — 按评审意见逐项修正 |

**PM 已拍板决策**:
1. **阻塞 1**: C0 双通道方案 A — C0 前端约 20 行最小改动，RealtimeDataManager 新增 AgentStateChanged 处理，映射到现有 agents_update merge 逻辑
2. **阻塞 2**: C0 移除 _periodic_broadcast_loop，不再保留作补强
3. **阻塞 3**: polling 降级路径 (filepath=None) 走 EventBus，定义为 HeartbeatTickEvent
4. **附加决策**: bootstrap 仍只推 full_state（旧格式），增量只推 AgentStateChanged（新格式），FullStateSnapshot 延到 C1

**修正项**: #4(React→Vue 3)、#5(状态投影规则)、#6(subagents/runs.json)、#7(payload_bytes)、#8(延迟指标口径)、#9(EventBus 跨线程)、#10(冷启动白屏)、#12(ChangeTracker 说明)、#14(schemaVersion hello)、#15(集成测试 polling)

---

## 1. 设计概述

### 1.1 设计目标

| # | 目标 | 量化指标 | 对应 PRD 需求 |
|---|------|---------|-------------|
| G-1 | 消除运行时全量推送 | 正常运行 full_state 推送频率 = 0 次/分钟 (bootstrap 除外) | [REQ_ECS_005], [REQ_ECS_006] |
| G-2 | 降低端到端延迟 | 文件变更→前端感知 p95 < 200ms | [REQ_ECS_004] |
| G-3 | 减少无效计算 | jsonl 增量解析（tail-read ≤ 50 行） | [REQ_ECS_004], [REQ_ECS_008] |
| G-4 | 渐进交付 | C0→C1→C2→C3，每期独立可验收可回滚 | 全局分期约束 |

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **单一数据源** | StateStore 作为所有 agent 状态的 Single Source of Truth，替代 status_cache 运行时缓存职责 |
| **事件驱动解耦** | file_watcher 不再直接调用 broadcast_full_state，改为发布到 EventBus |
| **增量最小化** | 仅推送变化的字段（field-level diff），不推送未变化的子域 |
| **零新增依赖** | 不引入第三方库；EventBus 基于 asyncio.Queue，Metrics 自实现 |
| **向后兼容** | C0 阶段 bootstrap 仍推 full_state（旧格式），增量推 AgentStateChanged（新格式）；前端约 20 行最小改动（RealtimeDataManager 新增 case），FullStateSnapshot 延到 C1 |

### 1.3 架构分层

```
┌──────────────────────────────────────────────────────────────────────┐
│                    L5 — 前端 (Vue 3 SPA)                           │
│              WebSocket 客户端 + REST 消费者                            │
│              C0: 接收 full_state + AgentStateChanged (约 20 行改动)      │
│              C1-C3: 完整 AgentStateChanged + 多事件处理               │
└──────────────┬───────────────────────────────────────────────────────┘
               │  WS: FullStateSnapshot / AgentStateChanged / ...
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│              L4 — api/websocket.py (WS 广播层)                        │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │  WS Broadcaster (EventBus subscriber)                      │     │
│  │    订阅: AgentStateChanged, FullStateSnapshot, ...           │     │
│  │    职责: 将事件序列化为 WS 协议帧，推送给 active_connections  │     │
│  └────────────────────────────────────────────────────────────┘     │
│  保留: send_initial_state() → bootstrap 推送 (仅 3 个允许场景)        │
│  移除: _periodic_broadcast_loop — C0 一并移除，不再保留             │
└──────────────┬──────────────────────────────────────────────────────┘
               │
        ┌──────┴──────────────────────────────┐
        ▼                                     ▼
┌──────────────────────┐          ┌──────────────────────────────┐
│ L3.5 — EventBus      │          │ L3.6 — MetricsCollector       │
│ (进程内事件总线)       │          │ (轻量进程内指标)               │
│  publish / subscribe │          │  Counter / Histogram         │
│  asyncio.Queue       │          │  GET /api/metrics             │
└──────┬───────────────┘          └──────────────────────────────┘
       │ publish / subscribe
       ▼
┌──────────────────────────────────────────────────────────────────────┐
│              L3 — ingest/ (增量摄入层)                                 │
│  ┌──────────────────┐  ┌───────────────────────────────────────┐     │
│  │ FileChangeClassifier│ │ AgentStateIngestor                  │     │
│  │ 路径→事件类型分类  │  │ 消费 agent_session_changed/run_changed│     │
│  │ 产出 FileChangeEvent│ │ tail-read jsonl → 提取状态字段        │     │
│  └──────────────────┘  │ → StateStore.update_agent()            │     │
│                        │ → publish(AgentStateChanged)           │     │
│                        └───────────────────────────────────────┘     │
└──────────────┬───────────────────────────────────────────────────────┘
               │ read/write
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│              L2.5 — StateStore (集中式内存状态存储)                    │
│  dict[agent_id, AgentState]                                          │
│  update_agent() → field-level diff → version++                       │
│  get_agent() / get_all_agents() / get_snapshot()                    │
└──────────────┬───────────────────────────────────────────────────────┘
               │ miss fallback
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│              L2 — data/ (数据读取层，保留)                              │
│  session_reader │ subagent_reader │ config_reader │ ...              │
│  新增: tail_read() 接口 (C0)                                        │
│  保留: status_cache 作为冷启动/降级回退                               │
└──────────────┬───────────────────────────────────────────────────────┘
               │
        ┌──────┴──────┐                  ┌────────────────┐
        ▼             ▼                  ▼                ▼
┌────────────────┐ ┌──────────┐  ┌────────────────┐ ┌────────────┐
│ L1 — watchers/ │ │ L0a —   │  │ L0c — 自有数据 │ │ L0d — core │
│ file_watcher   │ │ OpenClaw │  │ task_history   │ │ 配置/错误   │
│ → EventBus    │ │ FS       │  │                │ │            │
│ (不再调 full_  │ │ JSON/JSONL│ │                │ │            │
│  state)        │ │          │  │                │ │            │
└────────────────┘ └──────────┘  └────────────────┘ └────────────┘
```

### 1.4 架构拓扑对比

#### 改造前（双轨制）

```
                    ┌──────────────────────────────────────────────┐
  watchdog ──────────┤  路径A: _on_file_changed → broadcast_full_state│──→ WS → 前端
                    │    (串行 7+ 数据源，含 2 次全量扫盘)             │
                    └──────────────────────────────────────────────┘
                    ┌──────────────────────────────────────────────┐
  定时轮询 (5-30s) ─┤  路径B: _periodic_broadcast_loop             │──→ WS → 前端
                    │    get_changed_agents → 4 字段 diff              │
                    └──────────────────────────────────────────────┘
```

**瓶颈**: 任何文件变更 → 全量 7 子域重算；collaboration + performance 各需全量扫盘所有 session 文件。

#### 改造后（事件驱动）

```
  watchdog → DebouncedHandler → FileChangeClassifier → EventBus.publish(FileChangeEvent)
                                                           │
                                    ┌──────────────────────┤
                                    ▼                      ▼
                          AgentStateIngestor         WS Broadcaster
                          (tail-read → StateStore     (send to clients)
                           → publish(AgentStateChanged))
                                    │
                                    ▼
                              StateStore
                              (内存 dict)
```

**核心改进**:
1. **消除全量推送**: 文件变更仅触发对应文件的增量读取（tail-read ≤ 50 行）
2. **解耦**: file_watcher 不再直接调用 broadcast_full_state
3. **单一数据流**: FileChange → Ingest → StateStore → Diff → Event → WS

---

## 2. 模块设计

### 2.1 新增模块

#### 2.1.1 EventBus `[src/backend/events/event_bus.py]`

**职责**: 进程内事件总线，解耦 file_watcher 与 WS 推送。基于 `asyncio.Queue` 实现，支持按事件类型过滤订阅、通配订阅、背压丢弃。

**核心数据结构**:

```python
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional
from collections import defaultdict
import asyncio
import time
import logging

_LOG = logging.getLogger("openclaw.ecs.eventbus")

@dataclass
class Event:
    """事件基类"""
    event_type: str
    payload: Any = None
    timestamp: float = field(default_factory=time.time)

@dataclass
class FileChangeEvent:
    """文件变更事件 (REQ_ECS_002)"""
    event_type: str          # agent_session_changed | run_changed | config_changed | error_log_changed | unknown_file_changed
    filepath: str            # 变更文件的绝对路径
    agent_id: Optional[str]  # 从路径提取的 agent_id
    timestamp: float         # time.time()
    change_type: str          # "modified" | "created" | "deleted"

@dataclass
class AgentStateChangedEvent:
    """Agent 状态变更事件 (REQ_ECS_005)"""
    event_type: str = "AgentStateChanged"
    agent_id: str = ""
    diffs: list[dict] = field(default_factory=list)  # [{field, old_value, new_value}]
    version: int = 0
    timestamp: float = field(default_factory=time.time)

@dataclass
class FullStateSnapshotEvent:
    """全量状态快照事件 (REQ_ECS_005)"""
    event_type: str = "FullStateSnapshot"
    data: dict = field(default_factory=dict)
    trigger: str = "bootstrap"  # bootstrap | reconnect | schema_mismatch
    timestamp: float = field(default_factory=time.time)

class EventBus:
    """进程内事件总线 (REQ_ECS_001)"""

    def __init__(self, queue_size: int = 1024):
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=queue_size)
        self._subscribers: dict[str, list[Callable[[Event], Coroutine]]] = defaultdict(list)
        self._wildcard_subscribers: list[Callable[[Event], Coroutine]] = []
        self._running = False
        self._dispatch_task: Optional[asyncio.Task] = None
        self._dropped_total = 0  # 背压丢弃计数

    async def start(self) -> None:
        """启动事件分发循环（必须在 asyncio event loop 中调用）"""
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self) -> None:
        """停止事件分发"""
        self._running = False
        if self._dispatch_task:
            self._dispatch_task.cancel()
            self._dispatch_task = None

    async def publish(self, event: Event) -> None:
        """发布事件到总线 (REQ_ECS_001 AC-001-2)
        
        队列满时丢弃 oldest 并记录 metric，不阻塞生产者。
        """
        # 背压控制：队列满时丢弃最旧事件
        while self._queue.full():
            try:
                discarded = self._queue.get_nowait()
                self._dropped_total += 1
                _LOG.warning("EventBus dropped event: %s", discarded.event_type)
            except asyncio.QueueEmpty:
                break
        await self._queue.put(event)

    def subscribe(self, event_type: str, handler: Callable[[Event], Coroutine]) -> None:
        """订阅指定事件类型 (REQ_ECS_001)"""
        self._subscribers[event_type].append(handler)

    def subscribe_wildcard(self, handler: Callable[[Event], Coroutine]) -> None:
        """通配订阅（接收所有事件）"""
        self._wildcard_subscribers.append(handler)

    async def _dispatch_loop(self) -> None:
        """事件分发循环 — 错误隔离 (REQ_ECS_001 AC-001-3)"""
        while self._running:
            try:
                event = await self._queue.get()
                handlers = list(self._subscribers.get(event.event_type, []))
                handlers.extend(self._wildcard_subscribers)
                for handler in handlers:
                    try:
                        await handler(event)
                    except Exception as e:
                        _LOG.error("EventBus subscriber error: %s", e, exc_info=True)
                        # 错误隔离：单个 subscriber 异常不影响其他 subscriber
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOG.error("EventBus dispatch error: %s", e, exc_info=True)

    @property
    def dropped_total(self) -> int:
        return self._dropped_total

# 全局单例
_event_bus: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        from core.config_fortify import get_fortify_config
        cfg = get_fortify_config()
        _event_bus = EventBus(queue_size=cfg.event_bus_queue_size)
    return _event_bus
```

**需求追溯**: [REQ_ECS_001] AC-001-1 ~ AC-001-4

#### 线程边界

**watchdog/polling 线程安全约束** (Fix #9):
- watchdog 和 polling 运行在 `threading` 线程，EventBus 运行在 asyncio event loop 中
- `publish()` 必须经 `asyncio.run_coroutine_threadsafe()` 进入主线程 asyncio.Queue
- subscriber 异常不影响其他 subscriber（已有 try/except 包裹）
- 队列满时 watchdog 线程**不阻塞**（丢弃 oldest + 记录 metric，不等 asyncio 确认）

**HeartbeatTickEvent** (阻塞 3 - polling 降级路径):
```python
@dataclass
class HeartbeatTickEvent:
    """心跳 tick 事件 - 由 polling 定时器每 5s 发布
    
    语义约束:
    - 禁止: invalidate cache / broadcast_full_state / 全 agent 重算
    - 允许: (1) 每 12 tick 尝试恢复 watchdog (_try_resume_watchdog)
    - 可选: (2) 轻量 mtime 扫描 StateStore 已跟踪文件，有变化才 publish FileChangeEvent
    """
    event_type: str = "HeartbeatTick"
    tick_count: int = 0
    timestamp: float = field(default_factory=time.time)
```

---

#### 2.1.2 FileChangeClassifier `[src/backend/events/file_change_classifier.py]`

**职责**: 将文件系统变更路径分类为语义化事件类型（[REQ_ECS_002]）。路径模式匹配 + FileChangeEvent 构建。

```python
import os
import re
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import time

@dataclass
class FileChangeEvent:
    """文件变更事件载荷 (REQ_ECS_002)"""
    event_type: str
    filepath: str
    agent_id: Optional[str]
    timestamp: float
    change_type: str  # "modified" | "created" | "deleted"

# 路径模式匹配规则
_AGENT_SESSION_PATTERN = re.compile(
    r'.*?/agents/([^/]+)/sessions/[^/]+\.jsonl$'
)
_AGENT_RUNS_PATTERN = re.compile(
    r'.*?/agents/([^/]+)/runs\.json$'
)
_SUBAGENT_RUNS_PATTERN = re.compile(
    r'.*?/subagents/runs\.json$'
)
_AGENT_CONFIG_PATTERN = re.compile(
    r'.*?/agents/([^/]+)/openclaw\.json$'
)
_ERROR_LOG_PATTERN = re.compile(
    r'.*?/model-failures\.log$'
)

def classify_file_change(filepath: str, change_type: str = "modified") -> FileChangeEvent:
    """将文件路径分类为语义事件类型 (REQ_ECS_002)
    
    分类规则:
    | 文件模式 | 事件类型 |
    |---------|---------|
    | agents/{id}/sessions/*.jsonl | agent_session_changed |
    | agents/{id}/runs.json | run_changed |
    | agents/{id}/openclaw.json | config_changed (C2+) |
    | subagents/runs.json | run_changed |
    | model-failures.log | error_log_changed (C2+) |
    | 其他 | unknown_file_changed |
    """
    abs_path = os.path.abspath(filepath)
    agent_id: Optional[str] = None
    event_type = "unknown_file_changed"

    m = _AGENT_SESSION_PATTERN.match(abs_path)
    if m:
        agent_id = m.group(1)
        event_type = "agent_session_changed"
    else:
        m = _AGENT_RUNS_PATTERN.match(abs_path)
        if m:
            agent_id = m.group(1)
            event_type = "run_changed"
        elif _SUBAGENT_RUNS_PATTERN.match(abs_path):
            event_type = "run_changed"
        elif _AGENT_CONFIG_PATTERN.match(abs_path):
            event_type = "config_changed"
            m2 = _AGENT_CONFIG_PATTERN.match(abs_path)
            agent_id = m2.group(1) if m2 else None
        elif _ERROR_LOG_PATTERN.match(abs_path):
            event_type = "error_log_changed"
        else:
            import logging
            _log = logging.getLogger("openclaw.ecs.classifier")
            _log.debug("Unmatched file change: %s", abs_path)

    return FileChangeEvent(
        event_type=event_type,
        filepath=abs_path,
        agent_id=agent_id,
        timestamp=time.time(),
        change_type=change_type,
    )
```

**需求追溯**: [REQ_ECS_002] AC-002-1 ~ AC-002-3

---

#### 2.1.3 StateStore `[src/backend/state/state_store.py]`

**职责**: 集中式内存状态存储，作为所有 agent 状态的 Single Source of Truth（[REQ_ECS_003]）。支持 diff-on-write、版本管理、快照查询。

```python
from __future__ import annotations

import asyncio
import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger("openclaw.ecs.statestore")

@dataclass
class FieldDiff:
    """字段级变更描述"""
    field: str
    old_value: Any
    new_value: Any

@dataclass
class AgentState:
    """单个 Agent 的完整状态"""
    agent_id: str = ""
    name: str = ""
    status: str = "idle"       # idle | working | down
    current_task: str = ""
    last_active_at: int = 0    # unix ms
    error: Optional[str] = None
    sub_status: Optional[str] = None  # thinking | tool_executing | waiting_child | waiting_llm
    current_action: Optional[str] = None
    tool_name: Optional[str] = None
    waiting_for: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.agent_id,
            "name": self.name,
            "status": self.status,
            "currentTask": self.current_task,
            "lastActiveAt": self.last_active_at,
            "error": self.error,
        }

# StateStore 监控的字段列表（用于 diff 计算）
_DIFF_FIELDS = ("status", "current_task", "last_active_at", "error")

class StateStore:
    """集中式内存状态存储 (REQ_ECS_003)
    
    特性:
    - 纯内存 dict[agent_id, AgentState]
    - 写入时自动字段级 diff
    - 全局单调递增版本号
    - 冷启动全量填充
    """

    def __init__(self):
        self._agents: Dict[str, AgentState] = {}
        self._version: int = 0
        self._lock = asyncio.Lock()  # asyncio.Lock，在 event loop 中安全

    async def get_agent(self, agent_id: str) -> Optional[AgentState]:
        return self._agents.get(agent_id)

    async def get_all_agents(self) -> Dict[str, AgentState]:
        return dict(self._agents)

    async def update_agent(self, agent_id: str, partial: Dict[str, Any]) -> List[FieldDiff]:
        """字段级合并更新，返回变更字段列表 (REQ_ECS_003 AC-003-2)
        
        Args:
            agent_id: Agent ID
            partial: 部分字段字典，key 使用 snake_case
            
        Returns:
            本次变更的 FieldDiff 列表
        """
        async with self._lock:
            existing = self._agents.get(agent_id)
            diffs: List[FieldDiff] = []

            if existing is None:
                # 新 Agent — 全部字段视为变更
                existing = AgentState(agent_id=agent_id)
                for key, val in partial.items():
                    old = getattr(existing, key, None)
                    if old != val:
                        diffs.append(FieldDiff(field=key, old_value=old, new_value=val))
                    setattr(existing, key, val)
            else:
                # 已有 Agent — 逐字段比较
                for key, val in partial.items():
                    old = getattr(existing, key, None)
                    if old != val:
                        diffs.append(FieldDiff(field=key, old_value=old, new_value=val))
                        setattr(existing, key, val)

            self._agents[agent_id] = existing
            self._version += 1
            return diffs

    def get_global_version(self) -> int:
        """单调递增版本号 (REQ_ECS_003 AC-003-3)"""
        return self._version

    async def get_snapshot(self) -> dict:
        """获取完整状态快照，用于 FullStateSnapshot 事件"""
        agents_list = [a.to_dict() for a in self._agents.values()]
        return {
            "agents": agents_list,
            "version": self._version,
            "timestamp": time.time(),
        }

    async def populate_from_full_state(self, agents_data: List[Dict[str, Any]]) -> None:
        """冷启动全量填充 (REQ_ECS_003 AC-003-1)"""
        async with self._lock:
            for agent_data in agents_data:
                aid = agent_data.get("id", "")
                state = AgentState(
                    agent_id=aid,
                    name=agent_data.get("name", ""),
                    status=agent_data.get("status", "idle"),
                    current_task=agent_data.get("currentTask", ""),
                    last_active_at=agent_data.get("lastActiveAt", 0),
                    error=agent_data.get("error"),
                )
                self._agents[aid] = state
            self._version += 1
            _LOG.info("StateStore populated with %d agents (version=%d)", len(agents_data), self._version)

# 全局单例
_state_store: Optional[StateStore] = None

def get_state_store() -> StateStore:
    global _state_store
    if _state_store is None:
        _state_store = StateStore()
    return _state_store
```

**需求追溯**: [REQ_ECS_003] AC-003-1 ~ AC-003-4

---

#### 2.1.4 AgentStateIngestor `[src/backend/ingest/agent_ingestor.py]`

**职责**: 消费 EventBus 的 `agent_session_changed` 和 `run_changed` 事件，对变更文件执行增量读取（tail-read），将结果写入 StateStore（[REQ_ECS_004]）。

```python
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from events.event_bus import Event, get_event_bus
from events.file_change_classifier import FileChangeEvent
from state.state_store import get_state_store

_LOG = logging.getLogger("openclaw.ecs.ingestor")

class AgentStateIngestor:
    """Agent 状态增量摄入器 (REQ_ECS_004)
    
    处理流程:
    1. 收到 agent_session_changed / run_changed 事件
    2. tail-read 变更文件最后 N 行 (C0: 固定 50 行)
    3. 解析状态字段: status, current_task, last_active_at, error
    4. StateStore.update_agent(agent_id, partial) → 得到 diffs
    5. publish(AgentStateChanged) 到 EventBus
    """

    def __init__(self, tail_lines: int = 50):
        self._tail_lines = tail_lines

    ### 状态投影规则 (Fix #5)

    Ingestor tail-read jsonl 行后，如何提取 agent 状态字段。以下规则物理验证自
    `status_calculator.py` + `session_reader.py` 的存量逻辑。

    **字段来源映射**:

    | 目标字段 | 提取来源 | 具体逻辑 | 对应源码函数 |
    |------------|----------|----------|---------------|
    | `status` | jsonl tail-read | 反向遍历 jsonl，最新 `assistant`/​`tool_use` 消息 = working；`stopReason=error` = down；其余 = idle | `calculate_agent_status()` 逻辑简化版，参考 `has_recent_errors()` + `is_agent_working()` |
    | `current_task` | runs.json 优先 | 未结束 run 的 `task` 字段，截断至 60 字符 | `get_current_task()` |
    | `last_active_at` | runs.json + sessions.json | `max(runs[0].startedAt, session.updatedAt)` | `get_last_active_time()` |
    | `error` | jsonl tail-read + runs.json | jsonl 最新 `stopReason=error` 的 `errorMessage`；runs.json 兆底 `outcome.status=error` | `get_last_error()` + `_get_last_run_error()` |

    **Fallback 条件** (tail-read 无法提取时):
    1. jsonl 为空或解析失败 → 从 runs.json 提取 current_task 和 last_active_at
    2. runs.json 也为空 → 返回空 partial，Ingestor 不 publish 事件
    3. 状态与当前 StateStore 完全一致 → diffs 为空，不 publish

    **与 calculate_agent_status() 的差异**:
    - status_calculator 还检查 `is_agent_working()`、`_main_agent_solo_processing()`、`_has_recent_error_run()`
    - Ingestor 的 tail-read 只看 jsonl 末尾 50 行，可能遗漏较早的 error 消息
    - C0 接受这种差异（最终一致）；C1 通过 offset 追踪确保不遗漏
        self._event_bus = None
        self._state_store = None

    async def start(self) -> None:
        """注册为 EventBus subscriber"""
        self._event_bus = get_event_bus()
        self._state_store = get_state_store()
        self._event_bus.subscribe("agent_session_changed", self._handle_agent_session)
        self._event_bus.subscribe("run_changed", self._handle_run_changed)
        _LOG.info("AgentStateIngestor started (tail_lines=%d)", self._tail_lines)

    async def _handle_agent_session(self, event: Event) -> None:
        """处理 agent session 文件变更 (REQ_ECS_004 AC-004-1, AC-004-2)"""
        payload: FileChangeEvent = event.payload
        if not payload.agent_id:
            return

        agent_id = payload.agent_id
        filepath = Path(payload.filepath)

        if not filepath.exists():
            return

        start_time = time.monotonic()
        try:
            # (1) tail-read 变更文件
            lines = self._read_tail(filepath, self._tail_lines)

            # (2) 解析状态字段
            partial = self._extract_state_from_jsonl(lines, agent_id)

            if not partial:
                return

            # (3) 写入 StateStore
            diffs = await self._state_store.update_agent(agent_id, partial)

            if diffs:
                # (4) 发布变更事件
                from events.event_bus import AgentStateChangedEvent
                change_event = AgentStateChangedEvent(
                    agent_id=agent_id,
                    diffs=[
                        {"field": d.field, "old_value": d.old_value, "new_value": d.new_value}
                        for d in diffs
                    ],
                    version=self._state_store.get_global_version(),
                )
                await self._event_bus.publish(change_event)

            # Metrics
            lag_ms = (time.monotonic() - start_time) * 1000
            self._record_ingest_lag(lag_ms, payload.timestamp)

        except Exception as e:
            _LOG.error("Ingestor error for %s: %s", agent_id, e, exc_info=True)
            from core.error_handler import record_error
            record_error("io-error", str(e), f"ingestor:{agent_id}", exc=e)

    async def _handle_run_changed(self, event: Event) -> None:
        """处理 runs.json 变更"""
        payload: FileChangeEvent = event.payload

        # 提取受影响的 agent_id
        agent_id = payload.agent_id  # 可能从路径提取，也可能为 None（subagents/runs.json）
        
        if not agent_id:
            # subagents/runs.json 变更 — 需要重新计算所有 agent 的 runs 相关状态
            # C0: 触发全量状态重新计算并填充 StateStore
            await self._full_resync_runs()
            return

        # 单 agent runs.json 变更 — tail-read
        filepath = Path(payload.filepath)
        if not filepath.exists():
            return

        try:
            partial = self._extract_state_from_runs(filepath, agent_id)
            if partial:
                diffs = await self._state_store.update_agent(agent_id, partial)
                if diffs:
                    from events.event_bus import AgentStateChangedEvent
                    change_event = AgentStateChangedEvent(
                        agent_id=agent_id,
                        diffs=[{"field": d.field, "old_value": d.old_value, "new_value": d.new_value} for d in diffs],
                        version=self._state_store.get_global_version(),
                    )
                    await self._event_bus.publish(change_event)
        except Exception as e:
            _LOG.error("Ingestor runs error for %s: %s", agent_id, e, exc_info=True)
            from core.error_handler import record_error
            record_error("io-error", str(e), f"ingestor:runs:{agent_id}", exc=e)

    async def _full_resync_runs(self) -> None:
        """subagents/runs.json 变更时，全量重新计算所有 agent 的 runs 相关状态"""
        from data.config_reader import get_agents_list
        agents = get_agents_list()
        for agent in agents:
            aid = agent.get("id")
            if not aid:
                continue
            try:
                from data.subagent_reader import get_agent_runs
                runs = get_agent_runs(aid, limit=5)
                if runs:
                    # 更新 current_task 和 last_active
                    partial = {}
                    for run in runs[:3]:
                        if run.get("endedAt") is None:
                            partial["current_task"] = (run.get("task", "") or "")[:60]
                            break
                    partial["last_active_at"] = runs[0].get("startedAt", 0) if runs else 0
                    diffs = await self._state_store.update_agent(aid, partial)
                    if diffs:
                        from events.event_bus import AgentStateChangedEvent
                        change_event = AgentStateChangedEvent(
                            agent_id=aid,
                            diffs=[{"field": d.field, "old_value": d.old_value, "new_value": d.new_value} for d in diffs],
                            version=self._state_store.get_global_version(),
                        )
                        await self._event_bus.publish(change_event)
            except Exception:
                pass  # 错误隔离

    **关于 subagents/runs.json → _full_resync_runs()** (Fix #6):
    - subagents/runs.json 变更触发 `_full_resync_runs()`，全量重算所有 agent 的 runs 相关状态
    - C0 阶段可接受：该文件变更频率低（仅在 subagent run 创建/结束时），影响范围有限
    - C1 需改造为增量（按 run_id diff，仅更新受影响的 agent）

    def _read_tail(self, filepath: Path, max_lines: int) -> List[str]:
        """tail-read 文件末尾 max_lines 行
        
        物理验证: 复用 session_reader._read_tail_lines 的逻辑 (byte-level seek)
        """
        try:
            with open(filepath, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return []
                to_read = min(512 * 1024, size)
                f.seek(size - to_read)
                buf = f.read(to_read)
                lines = buf.split(b"\n")
                if size > to_read and lines:
                    lines = lines[1:]
                return [ln.decode("utf-8", errors="replace") for ln in lines[-max_lines:] if ln]
        except (IOError, OSError):
            return []

    def _extract_state_from_jsonl(self, lines: List[str], agent_id: str) -> Dict[str, Any]:
        """从 jsonl 尾部行提取 agent 状态字段
        
        解析策略: 反向遍历，找到最新有效状态指示。
        """
        partial: Dict[str, Any] = {}
        
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            # 从最新行提取状态线索
            if msg_type in ("assistant", "tool_result", "thinking"):
                if "last_active_at" not in partial:
                    # 使用消息的 timestamp 或 createdAt 作为活跃时间
                    ts = msg.get("timestamp") or msg.get("createdAt", 0)
                    if isinstance(ts, (int, float)):
                        partial["last_active_at"] = int(ts)
                if not partial.get("status"):
                    partial["status"] = "working"
                break  # 最新消息即当前状态
            elif msg_type == "tool_use":
                if "current_task" not in partial:
                    partial["current_task"] = msg.get("name", "") or ""
                partial["status"] = "working"
                break
            elif msg_type == "error":
                partial["error"] = msg.get("error", "Tool execution failed")
                # 不 break — 继续找最新状态

        # 如果没有从 jsonl 中提取到有效状态，从 runs.json 补充
        if not partial:
            partial = self._extract_state_from_runs_fallback(agent_id)

        return partial

    def _extract_state_from_runs(self, filepath: Path, agent_id: str) -> Dict[str, Any]:
        """从 runs.json 提取状态字段"""
        try:
            from data.subagent_reader import get_agent_runs
            runs = get_agent_runs(agent_id, limit=5)
            partial: Dict[str, Any] = {}
            for run in runs:
                if run.get("endedAt") is None:
                    task = run.get("task", "") or ""
                    partial["current_task"] = task[:60] if len(task) > 60 else task
                    partial["status"] = "working"
                    break
                outcome = run.get("outcome")
                if isinstance(outcome, dict) and outcome.get("status") == "error":
                    partial["error"] = f"Run error: {outcome.get('message', 'Unknown')}"
            partial["last_active_at"] = runs[0].get("startedAt", 0) if runs else 0
            return partial
        except Exception:
            return {}

    def _extract_state_from_runs_fallback(self, agent_id: str) -> Dict[str, Any]:
        """无有效 jsonl 数据时的 runs 回退"""
        return self._extract_state_from_runs(
            Path(f"agents/{agent_id}/runs.json"), agent_id
        )

    def _record_ingest_lag(self, lag_ms: float, file_change_ts: float) -> None:
        """记录 ingest lag metric"""
        try:
            from metrics.metrics import get_metrics
            metrics = get_metrics()
            metrics.histogram("dashboard_ingest_lag_ms", lag_ms)
        except Exception:
            pass
```

**需求追溯**: [REQ_ECS_004] AC-004-1 ~ AC-004-4

---

#### 2.1.5 MetricsCollector `[src/backend/metrics/metrics.py]`

**职责**: 轻量级进程内指标收集（Counter / Histogram），通过 REST 端点暴露（[REQ_ECS_007]）。不引入 Prometheus SDK。

```python
import math
import time
import threading
from typing import Dict, List, Optional

class Counter:
    """进程内计数器"""
    def __init__(self):
        self._value: int = 0
        self._labels: Dict[str, Dict[str, int]] = {}
        self._lock = threading.Lock()

    def inc(self, value: int = 1, labels: Optional[Dict[str, str]] = None) -> None:
        with self._lock:
            if labels:
                key = "|".join(f"{k}={v}" for k, v in sorted(labels.items()))
                if key not in self._labels:
                    self._labels[key] = 0
                self._labels[key] += value
            self._value += value

    @property
    def value(self) -> int:
        return self._value

    def snapshot(self) -> dict:
        with self._lock:
            result = {"total": self._value}
            if self._labels:
                result["by_label"] = dict(self._labels)
            return result


class Histogram:
    """进程内直方图（分桶统计）"""
    DEFAULT_BUCKETS = (5, 10, 25, 50, 100, 200, 500, 1000, 2000, 5000)

    def __init__(self, buckets: Optional[List[float]] = None):
        self._buckets = list(buckets or self.DEFAULT_BUCKETS)
        self._bucket_counts: List[int] = [0] * (len(self._buckets) + 1)
        self._sum: float = 0.0
        self._count: int = 0
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._count += 1
            self._sum += value
            for i, b in enumerate(self._buckets):
                if value <= b:
                    self._bucket_counts[i] += 1
                    return
            self._bucket_counts[-1] += 1  # +Inf bucket

    @property
    def count(self) -> int:
        return self._count

    @property
    def sum(self) -> float:
        return self._sum

    def percentile(self, p: float) -> float:
        """计算 p 分位数 (0-100)"""
        with self._lock:
            if self._count == 0:
                return 0.0
            target = self._count * p / 100.0
            cumulative = 0
            for i, count in enumerate(self._bucket_counts):
                cumulative += count
                if cumulative >= target:
                    if i == 0:
                        return 0.0
                    # 线性插值
                    return self._buckets[i - 1]
            return self._buckets[-1] if self._buckets else 0.0

    def snapshot(self) -> dict:
        with self._lock:
            result = {
                "count": self._count,
                "sum": round(self._sum, 2),
                "p50": round(self.percentile(50), 2),
                "p95": round(self.percentile(95), 2),
                "p99": round(self.percentile(99), 2),
                "buckets": {
                    f"le_{b}": c for b, c in zip(
                        self._buckets + ["+Inf"], self._bucket_counts
                    )
                },
            }
            return result


class MetricsCollector:
    """进程内指标收集器 (REQ_ECS_007)"""

    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()

    def counter(self, name: str) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter()
            return self._counters[name]

    def histogram(self, name: str, value: float) -> None:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram()
            self._histograms[name].observe(value)

    def get_snapshot(self) -> dict:
        """获取所有指标快照（用于 /api/metrics 端点）"""
        with self._lock:
            result = {}
            for name, counter in self._counters.items():
                result[name] = counter.snapshot()
            for name, hist in self._histograms.items():
                result[name] = hist.snapshot()
            return result

# 全局单例
_metrics: Optional[MetricsCollector] = None

def get_metrics() -> MetricsCollector:
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
```

**需求追溯**: [REQ_ECS_007] AC-007-1 ~ AC-007-4

---

### 2.2 修改模块

#### 2.2.1 `watchers/file_watcher.py` — 重大改造

**修改内容**: `_on_file_changed()` 不再直接调用 `broadcast_full_state()`，改为通过 EventBus 发布分类后的文件变更事件（[REQ_ECS_001], [REQ_ECS_006]）。

**修改前** (`_on_file_changed`):
```python
def _on_file_changed(filepath: Optional[str] = None) -> None:
    global _last_error
    try:
        _touch_activity()
        from api.websocket import broadcast_full_state          # ← 直接依赖 websocket
        from status.status_cache import get_cache
        import asyncio

        cache = get_cache()
        if filepath:
            agent_id = _extract_agent_id_from_path(filepath)
            if agent_id:
                cache.invalidate(agent_id)
            else:
                cache.invalidate()
        else:
            cache.invalidate()

        loop = _event_loop
        if loop and broadcast_full_state:
            asyncio.run_coroutine_threadsafe(broadcast_full_state(), loop)  # ← fire-and-forget 全量推送
    except Exception as e:
        _last_error = str(e)
        record_error("unknown", str(e), "file_watcher_push")
```

**修改后**:
```python
def _on_file_changed(filepath: Optional[str] = None) -> None:
    global _last_error
    try:
        _touch_activity()
        from status.status_cache import get_cache
        import asyncio

        # 缓存失效（保留）
        cache = get_cache()
        if filepath:
            agent_id = _extract_agent_id_from_path(filepath)
            if agent_id:
                cache.invalidate(agent_id)
            else:
                cache.invalidate()
        else:
            cache.invalidate()

        # 改为发布事件到 EventBus (REQ_ECS_006 AC-006-1)
        loop = _event_loop
        if loop:
            from events.file_change_classifier import classify_file_change
            from events.event_bus import get_event_bus
            
            event_bus = get_event_bus()
            if filepath:
                file_event = classify_file_change(filepath)
            else:
                # filepath=None 表示全量同步（轮询恢复等）
                file_event = classify_file_change.__wrapped__("")  # 或特殊处理
                file_event.event_type = "unknown_file_changed"  # 触发全量 resync
            
            asyncio.run_coroutine_threadsafe(
                event_bus.publish(file_event), loop
            )
    except Exception as e:
        _last_error = str(e)
        record_error("unknown", str(e), "file_watcher_push")
```

**数据流变化**:
```
修改前: watchdog → DebouncedHandler → _on_file_changed → broadcast_full_state() [串行 7 数据源]
修改后: watchdog → DebouncedHandler → _on_file_changed → EventBus.publish(FileChangeEvent)
                                                              │
                                                              └→ Ingestor → StateStore → EventBus(AgentStateChanged) → WS
```

**需求追溯**: [REQ_ECS_001] AC-001-1, [REQ_ECS_006] AC-006-1

---

#### 2.2.2 `api/websocket.py` — 重大改造

**修改内容**: 
1. 新增 WS Broadcaster 作为 EventBus subscriber
2. `send_initial_state` 保留为 bootstrap 场景（推送 `type: "full_state"` 旧格式）
3. **移除** `_periodic_broadcast_loop` 和 `broadcast_state_update()`（PM 决策：C0 一并移除）
4. schemaVersion 协商延到 C1（C0 无 hello 处理）
5. `broadcast_full_state()` 添加审计日志

**WS Broadcaster 新增代码**:
```python
# === WS Broadcaster (EventBus subscriber) ===

async def _ws_broadcast_event(event) -> None:
    """WS Broadcaster: 将 EventBus 事件转化为 WS 协议帧推送给客户端"""
    if not active_connections:
        return

    from events.event_bus import AgentStateChangedEvent, FullStateSnapshotEvent
    from metrics.metrics import get_metrics
    
    metrics = get_metrics()
    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    if isinstance(event, AgentStateChangedEvent):
        payload = {
            "agent_id": event.agent_id,
            "diffs": event.diffs,
            "version": event.version,
            "timestamp": ts_iso,
        }
        message = {"type": "AgentStateChanged", "payload": payload}
        metrics.counter("dashboard_state_update_total").inc()
        
        # 记录 payload 大小
        import sys
        payload_bytes = len(json.dumps(message).encode("utf-8"))
        metrics.histogram("dashboard_ws_payload_bytes", payload_bytes)
        
        await broadcast_message(message)

    elif isinstance(event, FullStateSnapshotEvent):
        message = {
            "type": "FullStateSnapshot",
            "payload": event.data,
            "timestamp": ts_iso,
        }
        metrics.counter("dashboard_full_state_total").inc(
            labels={"trigger": event.trigger}
        )
        payload_bytes = len(json.dumps(message).encode("utf-8"))
        metrics.histogram("dashboard_ws_payload_bytes", payload_bytes)
        await broadcast_message(message)
```

**WebSocket 端点** (C0 简化):
```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点 (REQ_ECS_005)
    
    C0: 无 hello schemaVersion 协商，直接 bootstrap 推送 full_state
    C1+: 新增 schemaVersion 协商（见 §4.4 C1+ 阶段定义）
    """
    await websocket.accept()
    active_connections.add(websocket)
    _ensure_broadcast_task()
    
    try:
        # C0: 直接推送 bootstrap（无 hello 等待）
        await send_initial_state(websocket, trigger="bootstrap")
        
        # 保持连接循环
        while True:
            data = await websocket.receive_text()
            # ... ping/pong 处理保持不变 ...
    except WebSocketDisconnect:
        active_connections.discard(websocket)
        _cancel_broadcast_task()
```

**`broadcast_full_state()` 改造** — 添加审计日志:
```python
async def broadcast_full_state(trigger: str = "bootstrap"):
    """全量状态推送 — 仅限 bootstrap 场景 (REQ_ECS_006 AC-006-3)
    
    允许调用场景:
    1. WebSocket 首连 (trigger=bootstrap)
    2. 进程重启 (trigger=reconnect)
    """
    import traceback
    caller = traceback.extract_stack()[-2]
    _LOG.info(
        "broadcast_full_state called: trigger=%s, caller=%s:%d",
        trigger, caller.filename, caller.lineno,
    )
    # ... 原有逻辑保持不变，但限制调用场景 ...
    # (实际由 send_initial_state 封装调用)
```

**需求追溯**: [REQ_ECS_005] AC-005-1 ~ AC-005-4, [REQ_ECS_006] AC-006-2 ~ AC-006-3

---

#### 2.2.3 `status/change_tracker.py` — 轻度改造

**修改内容**: 修复 `MAX_SNAPSHOTS` 逻辑缺陷；diff 逻辑复用到 StateStore（StateStore 自行实现字段级 diff，ChangeTracker 的 diff 逻辑作为参考）。

**修复 MAX_SNAPSHOTS**:
```python
# 修改前:
MAX_SNAPSHOTS = 10  # 固定 10，Agent 数 > 10 时旧快照被错误清理

# 修改后:
MAX_SNAPSHOTS_DEFAULT = 50  # 提高默认值

class ChangeTracker:
    MAX_SNAPSHOTS = MAX_SNAPSHOTS_DEFAULT
    
    def __init__(self, max_snapshots: int = MAX_SNAPSHOTS_DEFAULT):
        self.MAX_SNAPSHOTS = max_snapshots
        self._last_states: Dict[str, Dict[str, Any]] = {}
        self._changed_agents: Set[str] = set()
        self._lock = threading.Lock()
    
    # ... 其余不变 ...
```

**需求追溯**: [REQ_ECS_003]（diff 逻辑复用），解剖报告 P2-1

**ChangeTracker 角色说明** (Fix #12):
- C0: StateStore 为 **authoritative diff 来源**，ChangeTracker 仅在冷启动时参考（不再周期性调用）
- C1: 移除 periodic loop 后 ChangeTracker 可退役或仅作为历史快照参考

---

#### 2.2.4 `status/status_cache.py` — 轻度改造

**修改内容**: 降级为冷启动辅助/降级回退。运行时主缓存职责由 StateStore 承担（[REQ_ECS_003]）。模块本身代码不变，仅改变其在架构中的角色。

**不改动代码**。status_cache 保留为:
1. StateStore 冷启动阶段的预热数据源
2. StateStore miss 时的 fallback（[REQ_ECS_003] AC-003-4）

---

#### 2.2.5 `status/status_calculator.py` — C1 改造（C0 不动）

**C0 阶段**: `_periodic_broadcast_loop` **已移除**（PM 决策）。`get_changed_agents()` 不再被周期性调用，但函数本身保留供冷启动等场景使用。`broadcast_state_update()` 一并移除。C1 阶段改造为真异步化 + 有界并行（[REQ_ECS_009]）。

**C1 阶段改造**（[REQ_ECS_009]）: 真异步化 + 有界并行。

```python
# C1 修改:
async def get_changed_agents() -> List[Dict[str, Any]]:
    """C1: 有界并行计算 (REQ_ECS_009)"""
    from core.config_fortify import get_fortify_config
    cfg = get_fortify_config()
    max_conc = min(len(agents), cfg.ingest_max_concurrency)

    async def compute_one(agent: Dict) -> Optional[Dict]:
        agent_id = agent.get("id")
        try:
            # 使用 asyncio.to_thread 包裹同步 I/O
            status = await asyncio.to_thread(calculate_agent_status, agent_id)
            current_task = await asyncio.to_thread(get_current_task, agent_id)
            last_active = await asyncio.to_thread(get_last_active_time, agent_id)
            last_error = await asyncio.to_thread(get_last_error, agent_id) if status == "down" else None
            # ... 组装 state_data，tracker.update ...
        except Exception as e:
            record_error(...)
            return None

    tasks = [compute_one(a) for a in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # ... 过滤 None/异常，返回 changed_agents ...
```

---

#### 2.2.6 `core/config_fortify.py` — 轻度改造

**修改内容**: 新增 8 个 ECS 配置项（[REQ_ECS_012]）。

```python
# 在 FortifyConfig frozen dataclass 中新增:
# (C0 必须新增，C1/C2 扩展)
event_bus_queue_size: int = 1024           # ECS_EVENT_BUS_QUEUE_SIZE
ingest_tail_lines: int = 50                 # ECS_INGEST_TAIL_LINES
ingest_max_concurrency: int = 8             # ECS_INGEST_MAX_CONCURRENCY (C1)
checkpoint_dir: str = "~/.openclaw-agent-dashboard/checkpoints/"  # ECS_CHECKPOINT_DIR (C1)
checkpoint_flush_interval_sec: float = 10.0 # ECS_CHECKPOINT_FLUSH_INTERVAL (C1)
performance_snapshot_interval_sec: float = 30.0  # ECS_PERF_SNAPSHOT_INTERVAL (C2)
full_state_schema_version: int = 2         # ECS_SCHEMA_VERSION
max_agent_parallel: int = 8                # ECS_MAX_AGENT_PARALLEL (C1)
```

**需求追溯**: [REQ_ECS_012] AC-012-1 ~ AC-012-2

---

## 3. 数据流设计

### 3.1 热路径: 文件变更 → 前端（C0 完整链路）

```
                    ┌─────────────────────────────────────────────────────────────────┐
步骤1               │  OpenClaw 运行时写入 JSONL                                      │
                    │  agents/agent-001/sessions/session-abc.jsonl ← append write    │
                    └──────────────────────┬──────────────────────────────────────────┘
                                           │
                    ┌──────────────────────▼──────────────────────────────────────────┐
步骤2               │  watchdog FileSystemEventHandler.on_modified                    │
                    │  → DebouncedHandler.trigger(filepath) [1.5s debounce]           │
                    └──────────────────────┬──────────────────────────────────────────┘
                                           │
                    ┌──────────────────────▼──────────────────────────────────────────┐
步骤3               │  _on_file_changed(filepath)                                    │
                    │  (1) status_cache.invalidate(agent_id)  [保留]                  │
                    │  (2) FileChangeClassifier.classify(path)                         │
                    │      → FileChangeEvent(                                          │
                    │          event_type="agent_session_changed",                     │
                    │          filepath=".../session-abc.jsonl",                      │
                    │          agent_id="agent-001",                                   │
                    │          timestamp=T, change_type="modified")                   │
                    │  (3) EventBus.publish(FileChangeEvent)                            │
                    └──────────────────────┬──────────────────────────────────────────┘
                                           │ asyncio.Queue
                    ┌──────────────────────▼──────────────────────────────────────────┐
步骤4               │  EventBus._dispatch_loop                                       │
                    │  → AgentStateIngestor._handle_agent_session(event)               │
                    │      (1) _read_tail(filepath, 50)  ← tail-read ≤50 lines       │
                    │      (2) _extract_state_from_jsonl(lines, agent_id)              │
                    │          → partial = {status: "working", last_active_at: 1716...} │
                    │      (3) StateStore.update_agent("agent-001", partial)          │
                    │          → diffs = [FieldDiff(status, "idle", "working")]        │
                    │          → version++                                             │
                    │      (4) EventBus.publish(AgentStateChangedEvent(                │
                    │              agent_id="agent-001",                                │
                    │              diffs=[{field:"status", old:"idle", new:"working"}],│
                    │              version=43))                                        │
                    └──────────────────────┬──────────────────────────────────────────┘
                                           │ asyncio.Queue
                    ┌──────────────────────▼──────────────────────────────────────────┐
步骤5               │  EventBus._dispatch_loop                                       │
                    │  → WS Broadcaster._ws_broadcast_event(event)                    │
                    │      → 序列化为 WS 协议帧:                                       │
                    │        {                                                        │
                    │          "type": "AgentStateChanged",                            │
                    │          "payload": {                                           │
                    │            "agent_id": "agent-001",                             │
                    │            "diffs": [{field:"status", old:"idle", new:"working"}]│
                    │            "version": 43,                                        │
                    │            "timestamp": "2026-05-28T14:56:00.000Z"              │
                    │          }                                                      │
                    │        }                                                        │
                    │      → broadcast_message → 所有 active_connections              │
                    └──────────────────────┬──────────────────────────────────────────┘
                                           │ WebSocket frame
                    ┌──────────────────────▼──────────────────────────────────────────┐
步骤6               │  前端 RealtimeDataManager.handleMessage()                        │
                    │  (C0: 新增 ~20 行 case 处理 AgentStateChanged → agents_update merge)  │
                    │  (C1+: 完整事件分发处理)                                           │
                    │  → StateManager.setState / merge                                  │
                    │  → Vue 3 响应式更新 UI                                             │
                    └─────────────────────────────────────────────────────────────────┘
```

**延迟分析 (C0 目标)**:

| 步骤 | 预计耗时 | 说明 |
|------|---------|------|
| 防抖 | ≤ 1.5s | DebouncedHandler 1.5s 窗口 |
| EventBus dispatch | < 1ms | 单进程内存队列 |
| tail-read (≤50 lines) | < 10ms | 512KB read + json parse |
| StateStore.update | < 1ms | 内存 dict 操作 |
| EventBus dispatch | < 1ms | 单进程内存队列 |
| WS 序列化 + 发送 | < 5ms | JSON 序列化 + 网络发送 |
| **端到端** | **~1.5-3s** | 受防抖窗口主导 |

> **注**: 端到端延迟主要由 DebouncedHandler 的 1.5s 防抖窗口主导。防抖窗口内是 EventBus 引入带来的核心收益：避免了串行 7 个数据源的全量计算。

### 3.2 冷启动流程

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. 进程启动                                                          │
│    FastAPI app lifespan → start_file_watcher(loop)                  │
│    EventBus.start() → 启动 dispatch loop                             │
│    AgentStateIngestor.start() → 注册 subscriber                       │
│    WS Broadcaster 注册为 EventBus subscriber                         │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│ 2. 全量读取 → StateStore 填充                                       │
│    (1) 调用 get_agents_with_status() 串行计算所有 agent 状态           │
│    (2) StateStore.populate_from_full_state(agents_data)               │
│    (3) _LOG.info("StateStore populated with N agents")                │
│    (等价于一次 full_state 计算，但结果保存在 StateStore 中)              │
│    ⚠️ C0 冷启动仍走 get_agents_with_status() 串行填充，首屏白屏是          │
│       C0 非目标，C1+ 通过 checkpoint 快速恢复优化（见 §10 R-10）       │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│ 3. 发布 FullStateSnapshot 事件                                       │
│    EventBus.publish(FullStateSnapshotEvent(trigger="bootstrap"))      │
│    → WS Broadcaster → 推送给所有已连接客户端                            │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.3 WebSocket 首连流程

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. 客户端连接 WS /ws                                                  │
│    websocket_endpoint → websocket.accept()                            │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│ 2. Bootstrap 推送 (C0)                                                │
│    C0: 无 hello schemaVersion 协商（延到 C1）                        │
│    → send_initial_state() → type: "full_state" (旧格式，7 子域完整)   │
│    → 前端零改动即可 bootstrap                                         │
└──────────────┬───────────────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────────────┐
│ 3. 进入消息接收循环                                                    │
│    后续所有更新通过 EventBus → WS Broadcaster → AgentStateChanged     │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.4 异常恢复流程（C1: [REQ_ECS_008]）

```
文件 truncate / rotate 检测:
    │
    ├── checkpoint 存在且有效 (inode + mtime 匹配):
    │       → seek(offset) → read → parse → 正常增量
    │
    ├── 文件截断 (file_size < checkpoint.offset):
    │       → 检测异常 → 重置 offset = 0
    │       → record checkpoint_reset_total metric
    │       → 从头 tail-read (等价于 C0 行为)
    │
    ├── 文件替换 (inode 变化):
    │       → 检测异常 → 丢弃旧 checkpoint
    │       → 从头 tail-read
    │
    └── checkpoint 损坏 (JSON 解析失败):
            → 丢弃损坏条目
            → fallback 到 C0 行为 (tail-read 固定行数)
```

---

## 4. 接口契约（IDL）

### 4.1 EventBus 接口

```python
class EventBus:
    async def start() -> None
        """启动事件分发循环"""
    
    async def stop() -> None
        """停止事件分发"""
    
    async def publish(event: Event) -> None
        """发布事件。队列满时丢弃 oldest。"""
    
    def subscribe(event_type: str, handler: Callable[[Event], Coroutine]) -> None
        """订阅指定事件类型"""
    
    def subscribe_wildcard(handler: Callable[[Event], Coroutine]) -> None
        """通配订阅（接收所有事件类型）"""
    
    @property
    def dropped_total: int
        """背压丢弃计数"""
```

### 4.2 StateStore 接口

```python
class StateStore:
    async def get_agent(agent_id: str) -> Optional[AgentState]
        """获取单个 Agent 状态"""
    
    async def get_all_agents() -> Dict[str, AgentState]
        """获取所有 Agent 状态"""
    
    async def update_agent(agent_id: str, partial: Dict[str, Any]) -> List[FieldDiff]
        """字段级合并更新，返回变更字段 diff 列表"""
    
    def get_global_version() -> int
        """单调递增全局版本号"""
    
    async def get_snapshot() -> dict
        """获取完整状态快照"""
    
    async def populate_from_full_state(agents_data: List[Dict]) -> None
        """冷启动全量填充"""
```

### 4.3 AgentStateIngestor 接口

```python
class AgentStateIngestor:
    async def start() -> None
        """注册为 EventBus subscriber"""
    
    async def _handle_agent_session(event: Event) -> None
        """处理 agent_session_changed 事件: tail-read → StateStore.update → publish(AgentStateChanged)"""
    
    async def _handle_run_changed(event: Event) -> None
        """处理 run_changed 事件"""
```

### 4.4 WebSocket 协议帧格式

#### C0 阶段（向后兼容）

```jsonc
// full_state — 保持与原 full_state 完全一致（C0 bootstrap 唯一推送格式）
// 注意: C0 bootstrap 仍推 type: "full_state"（旧格式），不使用 FullStateSnapshot
// FullStateSnapshot 延到 C1 引入，届时才需要 schemaVersion hello 协商
{
  "type": "full_state",
  "data": {
    "agents": [...],
    "subagents": [...],
    "collaboration": {...},
    "tasks": [...],
    "performance": {...},
    "workflows": [...],
    "apiStatus": [...]
  },
  "timestamp": "2026-05-28T14:56:00.000Z"
}

// AgentStateChanged — C0 新增事件类型（前端必须处理）
{
  "type": "AgentStateChanged",
  "payload": {
    "agent_id": "agent-001",
    "diffs": [
      {"field": "status", "old_value": "idle", "new_value": "working"}
    ],
    "version": 42,
    "timestamp": "2026-05-28T14:56:00.000Z"
  }
}
```

#### C1+ 阶段

```jsonc
// hello — 连接后发送（C1+ schemaVersion 协商）
{
  "type": "hello",
  "schemaVersion": 2
}

// FullStateSnapshot — C1 引入，替代 full_state
{
  "type": "FullStateSnapshot",
  "payload": {
    "agents": [...],
    ...
  },
  "timestamp": "2026-05-28T14:56:00.000Z"
}

// ready — schemaVersion 一致后的确认 (C1+)
{
  "type": "ready"
}
```

#### 客户端 → 服务端

```jsonc
// hello — 连接后发送（C1+ 才需要）
{
  "type": "hello",
  "schemaVersion": 2
}

// ping — 心跳
{
  "type": "ping",
  "timestamp": 1716898560000
}
```

**向后兼容保证**:
- C0 阶段 bootstrap 仍推送 `type: "full_state"`（与现有前端 `RealtimeDataManager.handleMessage()` 完全兼容），**无需双格式推送**
- C0 阶段 `AgentStateChanged` 为新增事件类型，前端**必须**处理（约 20 行改动）
- FullStateSnapshot 延到 C1 引入，届时才需要 `schemaVersion` hello 协商
- ~~[AMBIGUITY]~~ ~~C0 后端同时推送 `full_state` 和 `FullStateSnapshot`~~ → **已解决**: bootstrap 只推 full_state，FullStateSnapshot 延到 C1
- **已解决**: §13.2 待确认事项「C0 后端同时推送双格式」→ PM 决策选「bootstrap 只推 full_state」，无需双格式

---

## 5. 配置设计

### 5.1 新增配置项 ([REQ_ECS_012])

| 配置项 | 环境变量 | 类型 | 默认值 | 分期 | 说明 |
|-------|---------|------|--------|-----|------|
| `event_bus_queue_size` | `ECS_EVENT_BUS_QUEUE_SIZE` | int | 1024 | C0 | EventBus 事件队列容量 |
| `ingest_tail_lines` | `ECS_INGEST_TAIL_LINES` | int | 50 | C0 | C0 tail-read 行数 |
| `ingest_max_concurrency` | `ECS_INGEST_MAX_CONCURRENCY` | int | 8 | C1 | C1 有界并行上限 |
| `checkpoint_dir` | `ECS_CHECKPOINT_DIR` | str | `~/.openclaw-agent-dashboard/checkpoints/` | C1 | C1 checkpoint 存储目录 |
| `checkpoint_flush_interval_sec` | `ECS_CHECKPOINT_FLUSH_INTERVAL` | float | 10.0 | C1 | C1 checkpoint flush 间隔 |
| `performance_snapshot_interval_sec` | `ECS_PERF_SNAPSHOT_INTERVAL` | float | 30.0 | C2 | C2 performance 慢通道间隔 |
| `full_state_schema_version` | `ECS_SCHEMA_VERSION` | int | 2 | C0 | WS 协议 schema 版本 |
| `max_agent_parallel` | `ECS_MAX_AGENT_PARALLEL` | int | 8 | C1 | C1 状态计算并行上限 |

### 5.2 配置集成方式

在 `core/config_fortify.py` 的 `FortifyConfig` frozen dataclass 中新增上述 8 个字段，通过 `@cached_property` 支持环境变量覆盖，遵循现有 `lru_cache(maxsize=1)` 单例模式。

---

## 6. Metrics 设计 ([REQ_ECS_007])

### 6.1 指标定义

| Metric 名称 | 类型 | 标签 | 说明 |
|------------|------|------|------|
| `dashboard_full_state_total` | Counter | `trigger=bootstrap\|reconnect\|schema_mismatch` | FullStateSnapshot 推送次数 |
| `dashboard_state_update_total` | Counter | — | AgentStateChanged 推送次数 |
| `dashboard_ingest_lag_ms` | Histogram | — | 文件 mtime → Ingestor 完成延迟 (ms)，不含 debounce，C0 目标 p95 < 200ms |
| `dashboard_e2e_update_latency_ms` | Histogram | — | 文件变更 → 前端 UI 更新延迟 (ms)，含 debounce（C1+ 可选） |
| `dashboard_jsonl_bytes_read_total` | Counter | — | Ingestor 累计读取 jsonl 字节数 |
| `dashboard_ws_payload_bytes` | Histogram | — | WS 单帧 payload 字节数（使用 `len(json.dumps(msg).encode("utf-8"))` 计算） |
| `eventbus_dropped_total` | Counter | — | EventBus 背压丢弃事件次数 |

### 6.2 暴露端点

```
GET /api/metrics → JSON 响应

响应示例:
{
  "dashboard_full_state_total": {
    "total": 3,
    "by_label": {"trigger=bootstrap": 2, "trigger=schema_mismatch": 1}
  },
  "dashboard_state_update_total": {
    "total": 142
  },
  "dashboard_ingest_lag_ms": {
    "count": 142,
    "sum": 1256.5,
    "p50": 8.2,
    "p95": 45.3,
    "p99": 120.1
  },
  "dashboard_ws_payload_bytes": {
    "count": 145,
    "p50": 256,
    "p95": 1024
  }
}
```

### 6.3 实现位置

- 新增文件: `src/backend/metrics/metrics.py`（MetricsCollector 类）
- 新增路由: `src/backend/api/metrics.py`（`GET /api/metrics` 端点）

---

## 7. 前端适配设计

### 7.1 C0 阶段最小前端改动

**目标**: C0 前端约 20 行最小改动即可处理增量更新（[REQ_ECS_005] 双通道方案 A）。

**策略**: 后端 `send_initial_state()` 保持推送 `type: "full_state"` 格式（与现有前端完全兼容）。`AgentStateChanged` 为新增事件类型，前端**必须**处理。

**C0 前端必须改动** (~20 行):
1. `RealtimeDataManager.handleMessage()` 新增对 `AgentStateChanged` 事件类型的 case 处理
2. 将 `AgentStateChanged.payload` 中的 diffs 映射到现有 `agents_update` merge 逻辑（复用 `StateManager` 已有的 merge 能力）
3. 移除 `_periodic_broadcast_loop` 依赖（如果前端有任何对 `state_update` 消息类型的依赖，C0 后端不再推送该类型）

**具体改动示例** (`frontend/src/managers/RealtimeDataManager.ts`):
```typescript
// handleMessage() 新增 case (约 20 行)
handleMessage(message: any) {
  switch (message.type) {
    case 'full_state':
      // 原有逻辑不变
      this.stateManager.batchUpdate(message.data);
      break;
    case 'AgentStateChanged':  // ← 新增
      const payload = message.payload;
      if (payload && payload.agent_id) {
        // 映射到现有 agents_update merge 逻辑
        this.eventBus.emit('agents_update', {
          id: payload.agent_id,
          ...Object.fromEntries(
            payload.diffs.map(d => [d.field, d.new_value])
          )
        });
      }
      break;
    // ... 原有 ping/pong 等
  }
}
```

**WS 事件名说明** (§4.4 补充): C0 后端不再推送 `state_update` 消息类型（`_periodic_broadcast_loop` 已移除）。如果前端有其他地方依赖 `state_update`，无需处理，C0 仅推送 `full_state`（bootstrap）和 `AgentStateChanged`（增量）。

### 7.2 WebSocket 协议变更汇总

| 阶段 | 新增消息类型 | 方向 | 前端改动 |
|------|------------|------|----------|
| C0 | `AgentStateChanged` | S→C | **必须处理** (~20 行，映射到 agents_update merge) |
| C0 | `full_state` (bootstrap, 旧格式) | S→C | 无需改动（与现有完全兼容） |
| C1 | `FullStateSnapshot` (替代 `full_state`) + `hello` 协商 | S→C / C→S | 前端迁移到新格式 |
| C2 | `CollaborationChanged`, `TaskChanged`, `TimelineAppended`, `PerformanceSnapshot` | S→C | 前端适配新事件 |
| C3 | — | — | 统一 Patch 模型 + 虚拟滚动 |

### 7.3 StateManager 适配 (C3: [REQ_ECS_011])

C3 阶段前端从全量替换模型升级为统一 Patch 模型:

```typescript
// C3: Patch 模型
interface StatePatch {
  type: "AgentStateChanged" | "CollaborationChanged" | "TaskChanged" | ...
  payload: {
    agent_id?: string
    diffs?: FieldDiff[]
    version: number
    timestamp: string
  }
}

// 版本号防护 — 丢弃 version ≤ 本地 version 的事件
const localVersion = getStateManager().getState<number>("globalVersion") || 0
if (patch.payload.version <= localVersion) return

// merge 策略:
// agents: 按 agent_id merge，字段级 patch (复用现有 agents_update 逻辑)
// subagents: 按 run_id merge
// tasks: add → 追加, update → 替换, remove → 删除
// collaboration: 字段级 merge
// performance: 整包替换
```

---

## 8. 逐 REQ 设计方案映射

### 8.1 [REQ_ECS_001] 事件总线

| 维度 | 方案 |
|------|------|
| 实现 | `asyncio.Queue` + 分发循环 |
| 文件 | **新增** `src/backend/events/event_bus.py` |
| 核心类 | `EventBus`, `Event`, `FileChangeEvent`, `AgentStateChangedEvent`, `FullStateSnapshotEvent` |
| 集成点 | `file_watcher._on_file_changed()` 调用 `event_bus.publish()`; `websocket.py` 注册 WS Broadcaster subscriber |

### 8.2 [REQ_ECS_002] 文件变更事件分类器

| 维度 | 方案 |
|------|------|
| 实现 | 正则表达式路径匹配 |
| 文件 | **新增** `src/backend/events/file_change_classifier.py` |
| 核心函数 | `classify_file_change(filepath, change_type) → FileChangeEvent` |
| 集成点 | `file_watcher._on_file_changed()` 调用 `classify_file_change()` 后 publish |

### 8.3 [REQ_ECS_003] StateStore

| 维度 | 方案 |
|------|------|
| 实现 | `dict[agent_id, AgentState]` + `asyncio.Lock` |
| 文件 | **新增** `src/backend/state/state_store.py` |
| 核心类 | `StateStore`, `AgentState`, `FieldDiff` |
| 集成点 | Ingestor 写入；WS Broadcaster 读取；`send_initial_state` 冷启动填充 |
| 与 status_cache 关系 | StateStore 为运行时主缓存；status_cache 降级为冷启动/降级回退 |

### 8.4 [REQ_ECS_004] AgentStateIngestor

| 维度 | 方案 |
|------|------|
| 实现 | EventBus subscriber，消费 `agent_session_changed` / `run_changed` |
| 文件 | **新增** `src/backend/ingest/agent_ingestor.py` |
| 核心类 | `AgentStateIngestor` |
| tail-read | 复用 `session_reader._read_tail_lines()` 逻辑（byte-level seek） |
| 集成点 | EventBus → Ingestor → StateStore → EventBus(AgentStateChanged) |

### 8.5 [REQ_ECS_005] WS 协议升级

| 维度 | 方案 |
|------|------|
| 文件 | **修改** `src/backend/api/websocket.py` |
| 修改点 | 新增 WS Broadcaster subscriber; `send_initial_state` 保留为 bootstrap（推送 `type: "full_state"` 旧格式）；schemaVersion 协商延到 C1 |
| **移除** | `broadcast_state_update()` 和 `_periodic_broadcast_loop` 在 C0 **一并移除**（PM 决策） |
| C0 约束 | bootstrap 仍推 `type: "full_state"`（旧格式），增量推 `AgentStateChanged`；FullStateSnapshot 延到 C1 |

### 8.6 [REQ_ECS_006] broadcast_full_state 退役

| 维度 | 方案 |
|------|------|
| 文件 | **修改** `src/backend/watchers/file_watcher.py` |
| 修改点 | `_on_file_changed()` 移除 `broadcast_full_state` import 和调用，改为 `event_bus.publish()` |
| filepath=None 路径 | polling tick 走 EventBus.publish(HeartbeatTickEvent)，不触发全量重算（阻塞 3） |
| 保留调用 | `send_initial_state()` (bootstrap); 进程启动后一次性推送 |
| 审计 | `broadcast_full_state()` 入口添加调用来源日志 |

### 8.7 [REQ_ECS_007] Metrics

| 维度 | 方案 |
|------|------|
| 文件 | **新增** `src/backend/metrics/metrics.py`, `src/backend/api/metrics.py` |
| 实现 | 进程内 Counter / Histogram，`GET /api/metrics` 暴露 |
| 指标 | 6 个（见 §6.1） |

### 8.8 [REQ_ECS_008] JSONL Offset + Checkpoint

| 维度 | 方案 |
|------|------|
| 文件 | **新增** `src/backend/ingest/checkpoint_manager.py` |
| 实现 | 进程内 dict offset + JSON 文件持久化 |
| 集成 | `AgentStateIngestor._read_tail()` 改为 `_read_from_offset()` |
| 异常恢复 | inode/mtime 校验 → offset 重置 → fallback C0 行为 |

### 8.9 [REQ_ECS_009] 有界并行计算

| 维度 | 方案 |
|------|------|
| 文件 | **修改** `src/backend/status/status_calculator.py` |
| 修改点 | `get_changed_agents()` 改为 `asyncio.gather(*tasks, return_exceptions=True)` |
| 并发上限 | `min(len(agents), config.ingest_max_concurrency)` |
| 异步化 | `asyncio.to_thread()` 包裹同步 I/O |

### 8.10 [REQ_ECS_010] Collaboration/Performance 解耦

| 维度 | 方案 |
|------|------|
| 文件 | **修改** `api/collaboration.py`, `api/performance.py`, `api/subagents.py` |
| 实现 | 拆分为独立事件源; `FullStateSnapshot` 瘦身 |
| FullStateSnapshot 瘦身后 | 仅含 agents, subagents, apiStatus |

### 8.11 [REQ_ECS_011] 前端 Patch 模型 + 虚拟滚动

| 维度 | 方案 |
|------|------|
| 文件 | **修改** `frontend/src/managers/RealtimeDataManager.ts`, `StateManager.ts` |
| 实现 | 统一 Patch 模型; version 防重放; 虚拟滚动 |
| 虚拟滚动 | agent 数 > 20 时自动启用固定行高虚拟列表 |

### 8.12 [REQ_ECS_012] 配置项

| 维度 | 方案 |
|------|------|
| 文件 | **修改** `src/backend/core/config_fortify.py` |
| 实现 | FortifyConfig 新增 8 个字段，支持环境变量覆盖 |

---

## 9. 需求追溯表

### 9.1 需求 → 设计映射

| 需求 ID | 需求描述 | 设计章节 | 实现模块 | 变更类型 |
|---------|---------|---------|---------|---------|
| [REQ_ECS_001] | 事件总线 | §2.1.1, §8.1 | `events/event_bus.py` | 新增 |
| [REQ_ECS_002] | 文件变更分类器 | §2.1.2, §8.2 | `events/file_change_classifier.py` | 新增 |
| [REQ_ECS_003] | StateStore | §2.1.3, §8.3 | `state/state_store.py` | 新增 |
| [REQ_ECS_004] | AgentStateIngestor | §2.1.4, §8.4 | `ingest/agent_ingestor.py` | 新增 |
| [REQ_ECS_005] | WS 协议升级 | §2.2.2, §4.4, §8.5 | `api/websocket.py` | 修改 |
| [REQ_ECS_006] | broadcast_full_state 退役 | §2.2.1, §8.6 | `watchers/file_watcher.py` | 修改 |
| [REQ_ECS_007] | Metrics | §2.1.5, §6, §8.7 | `metrics/metrics.py`, `api/metrics.py` | 新增 |
| [REQ_ECS_008] | JSONL Offset (C1) | §8.8, §3.4 | `ingest/checkpoint_manager.py` | 新增 (C1) |
| [REQ_ECS_009] | 有界并行 (C1) | §2.2.5, §8.9 | `status/status_calculator.py` | 修改 (C1) |
| [REQ_ECS_010] | Collab/Perf 解耦 (C2) | §8.10 | `api/collaboration.py`, `api/performance.py` | 修改 (C2) |
| [REQ_ECS_011] | 前端 Patch 模型 (C3) | §7.3, §8.11 | `RealtimeDataManager.ts`, `StateManager.ts` | 修改 (C3) |
| [REQ_ECS_012] | 配置项 | §5, §8.12 | `core/config_fortify.py` | 修改 |

### 9.2 验收条件追溯

| 验收条件 | 对应设计 | 验证方法 |
|---------|---------|---------|
| AC-001-1: file_watcher 不再调 broadcast_full_state | §2.2.1 `_on_file_changed` 改造 | `grep broadcast_full_state watchers/` = 0 结果 |
| AC-001-2: 队列满丢弃 oldest | §2.1.1 `EventBus.publish()` 背压逻辑 | 压力测试 + `/api/metrics` eventbus_dropped_total |
| AC-001-3: subscriber 错误隔离 | §2.1.1 `_dispatch_loop` try/except | 注入异常 subscriber，验证其他正常 |
| AC-002-1 ~ AC-002-3: 分类正确 | §2.1.2 `classify_file_change()` | 单元测试各路径模式 |
| AC-003-1: 冷启动填充 | §3.2 冷启动流程 | 启动后 StateStore 非空 |
| AC-003-2: update_agent 返回 diffs | §2.1.3 `StateStore.update_agent()` | 单元测试 |
| AC-003-3: version 单调递增 | §2.1.3 `StateStore` | 多次 update 验证 version 递增 |
| AC-004-1: tail-read ≤50 行 | §2.1.4 `_read_tail()` | 检查读取行数 |
| AC-004-2: Ingestor 产出 AgentStateChanged | §2.1.4 `_handle_agent_session()` | WS 消息流验证 |
| AC-005-1: 正常运行 full_state = 0/min | §2.2.2 | `dashboard_full_state_total` 观察 5 分钟，增量 = 0 |
| AC-006-2: ingest lag p95 < 200ms | §6 | `dashboard_ingest_lag_ms` p95 < 200ms（不含 debounce） |
| AC-005-2: 首连仅 1 次 full_state | §3.3 首连流程 | WS 消息流记录 |
| AC-006-1: file_watcher 无 broadcast_full_state | §2.2.1 | 代码审计 |
| AC-007-1 ~ AC-007-4: Metrics 端点 | §6 | `curl /api/metrics` 验证 |

---

## 10. 风险与缓解

### 10.1 技术风险

| # | 风险 | 严重度 | 描述 | 缓解措施 | 关联 REQ |
|---|------|--------|------|---------|---------|
| R-01 | **jsonl tail-read 丢失上下文** | 🟡 中 | 50 行 tail-read 可能无法捕获完整状态变更（如 error 消息在更早位置） | C0: Ingestor 提取失败时，下次文件变更会重新触发摄入（最终一致）。C1: offset 追踪确保不遗漏 | REQ_ECS_004 |
| R-02 | **StateStore 并发写入** | 🟢 低 | asyncio.Lock 保护，单进程内无真正并发风险 | StateStore 使用 `asyncio.Lock`；单进程约束 | REQ_ECS_003 |
| R-03 | **EventBus 事件积压** | 🟡 中 | 高频文件变更导致队列积压，背压丢弃事件 | 队列大小 1024 足以缓冲 1-2 秒的突发；`eventbus_dropped_total` metric 监控 | REQ_ECS_001 |
| R-04 | **jsonl offset 飘移（C1）** | 🟡 中 | checkpoint offset 与实际文件位置不一致 | inode + mtime 双重校验；不一致时重置 offset；fallback C0 行为 | REQ_ECS_008 |
| R-05 | **schemaVersion 迁移** | 🟢 低 | 前端版本不一致导致不处理新事件 | C0: bootstrap 推送 `full_state` 旧格式，前端零改动即可 bootstrap；schemaVersion 协商延到 C1 | REQ_ECS_005 |
| R-10 | **冷启动首屏白屏** | 🟢 低 | C0 冷启动仍走 `get_agents_with_status()` 串行填充 StateStore，首屏可能出现短暂白屏 | C0 非目标（可接受短暂延迟）；C1+ 通过 checkpoint 快速恢复优化。在 design_manifest 中标注此已知限制 | - |
| R-06 | ~~**_periodic_broadcast_loop 与 EventBus 双通道**~~ | ✅ **已解决** | ~~C0 阶段两套推送路径可能产生重复推送~~ | **已解决**: C0 移除 `_periodic_broadcast_loop` 和 `broadcast_state_update()`，完全依赖 EventBus 事件驱动（PM 决策） | REQ_ECS_005 |

### 10.2 回滚策略

| 分期 | 回滚方式 | 影响范围 |
|------|---------|---------|
| C0 | revert 新增文件 + 修改文件，恢复 `_on_file_changed` 直接调用 `broadcast_full_state()` | 恢复到改造前双轨制 |
| C1 | revert checkpoint + 并行化改动，fallback 到 C0 tail-read + 串行计算 | 保留 C0 增量化 |
| C2 | revert collaboration/tasks/performance 拆分，恢复 FullStateSnapshot 全量推送 | 保留 C0/C1 增量化 |
| C3 | revert 前端 Patch 模型，恢复全量替换 | 保留 C0/C1/C2 |

每期改造在独立 git 分支/commit 集中，可独立 revert。

---

## 11. 实施建议

### 11.1 分期实施映射

#### C0: Agents 热路径增量化（P0 核心）

| 文件 | 变更类型 | 修改内容 | 精确到函数/类 |
|------|---------|---------|-------------|
| `src/backend/events/__init__.py` | **新增** | 模块初始化 | — |
| `src/backend/events/event_bus.py` | **新增** | EventBus 核心 | `Event`, `FileChangeEvent`, `AgentStateChangedEvent`, `FullStateSnapshotEvent`, `EventBus` |
| `src/backend/events/file_change_classifier.py` | **新增** | 文件分类器 | `classify_file_change()` |
| `src/backend/state/__init__.py` | **新增** | 模块初始化 | — |
| `src/backend/state/state_store.py` | **新增** | StateStore | `FieldDiff`, `AgentState`, `StateStore` |
| `src/backend/ingest/__init__.py` | **新增** | 模块初始化 | — |
| `src/backend/ingest/agent_ingestor.py` | **新增** | Ingestor | `AgentStateIngestor` |
| `src/backend/metrics/__init__.py` | **新增** | 模块初始化 | — |
| `src/backend/metrics/metrics.py` | **新增** | Metrics | `Counter`, `Histogram`, `MetricsCollector` |
| `src/backend/api/metrics.py` | **新增** | Metrics 端点 | `router.get("/metrics")` |
| | `src/backend/watchers/file_watcher.py` | **修改** | `_on_file_changed()` 改为 EventBus publish | `_on_file_changed()` — 移除 `from api.websocket import broadcast_full_state`，改为 `from events.file_change_classifier import classify_file_change; from events.event_bus import get_event_bus`；`filepath=None` 路径改为 publish HeartbeatTickEvent（不触发全量重算） |
| | `src/backend/api/websocket.py` | **修改** | 新增 WS Broadcaster；移除 periodic loop | `websocket_endpoint()` — C0 无 hello 处理，直接 bootstrap；新增 `_ws_broadcast_event()` 函数；`send_initial_state()` 保留（推送 `type: "full_state"` 旧格式）；**移除** `_periodic_broadcast_loop` 和 `broadcast_state_update()`；`broadcast_full_state()` 新增审计日志 |
| `src/backend/core/config_fortify.py` | **修改** | 新增 8 个配置项 | `FortifyConfig` dataclass — 新增 8 个字段 |
| `src/backend/main.py` (或等效入口) | **修改** | 启动时初始化 EventBus + Ingestor + StateStore | 应用生命周期 `lifespan` 中新增初始化代码 |
| `src/backend/status/change_tracker.py` | **修改** | 修复 MAX_SNAPSHOTS | `ChangeTracker.__init__()` — MAX_SNAPSHOTS 提升至 50 |
| `frontend/src/managers/RealtimeDataManager.ts` | **修改** | 新增 AgentStateChanged 处理 | `handleMessage()` — 新增 `case 'AgentStateChanged':` 约 20 行，映射到 agents_update merge 逻辑 |

**C0 集成测试验收点**:
1. 文件变更后 WS 消息流无 `full_state` 类型（排除首连）
2. WS 首连后收到 `full_state` 且仅 1 次（type 为 `full_state` 旧格式）
3. `send_initial_state()` 正常工作（7 子域完整）
4. `/api/metrics` 返回 7 个指标（含新增 `dashboard_e2e_update_latency_ms`）
5. `grep broadcast_full_state watchers/` = 0 结果
6. `grep _periodic_broadcast_loop` 在 websocket.py 中 = 0 结果
7. 前端 AgentStateChanged -> agent card 增量更新（约 20 行改动验证）
8. **强制 polling 模式跑 5 分钟，`dashboard_full_state_total` 增量 = 0**

#### C1: JSONL Offset + Checkpoint + 并行计算（P1）

| 文件 | 变更类型 | 修改内容 | 精确到函数/类 |
|------|---------|---------|-------------|
| `src/backend/ingest/checkpoint_manager.py` | **新增** | Checkpoint 管理 | `CheckpointManager` |
| `src/backend/ingest/agent_ingestor.py` | **修改** | 从 tail-read 升级为 offset-read | `_handle_agent_session()` — 使用 `_read_from_offset()` 替代 `_read_tail()` |
| `src/backend/status/status_calculator.py` | **修改** | 有界并行化 | `get_changed_agents()` — `asyncio.gather` + `asyncio.to_thread` |
| `src/backend/core/error_handler.py` | **修改** | 异步化 | `run_with_retry()` → `run_with_retry_async()` |

**C1 集成测试验收点**:
1. 进程重启后 checkpoint 正确加载
2. 文件截断后 offset 重置
3. 并行计算耗时 < 串行 50%

#### C2: Collaboration/Performance 解耦（P2）

| 文件 | 变更类型 | 修改内容 |
|------|---------|---------|
| `src/backend/api/collaboration.py` | **修改** | 拆分为独立事件源 |
| `src/backend/api/performance.py` | **修改** | 拆分为独立慢通道 |
| `src/backend/ingest/collaboration_ingestor.py` | **新增** | Collaboration 增量摄入 |
| `src/backend/api/websocket.py` | **修改** | `FullStateSnapshot` 瘦身 |

**C2 集成测试验收点**:
1. 文件变更后无包含 collaboration/tasks/performance 的 full_state
2. `CollaborationChanged` / `TaskChanged` 事件正常推送
3. `PerformanceSnapshot` 30s 周期推送

#### C3: 前端 Patch 模型 + 虚拟滚动（P3）

| 文件 | 变更类型 | 修改内容 |
|------|---------|---------|
| `frontend/src/managers/RealtimeDataManager.ts` | **修改** | 处理所有事件类型 |
| `frontend/src/managers/StateManager.ts` | **修改** | 统一 Patch 模型 |
| `frontend/src/components/AgentList.vue` (或等效) | **修改** | 虚拟滚动 (C3) |

---

## 11.5 修订后的 C0 验收标准

以下为评审后修订的 C0 完整验收标准，全部必须通过才可进入 C1。

| 验收项 | 标准 |
|--------|---------|
| 运行时 full_state | 0 次/分钟（bootstrap 除外） |
| 文件变更 → UI 更新 | p95 < 2s（含 1.5s debounce） |
| periodic loop | 代码中不存在 / 不运行 |
| polling 模式 5 分钟 | `dashboard_full_state_total` 增量 = 0 |
| 前端 | AgentStateChanged → agent card 增量更新 |
| ingest lag（不含 debounce） | p95 < 200ms |

---

## 12. 依赖变更

### 12.1 新增依赖

**无新增外部依赖**。所有新增组件基于 Python 标准库 (`asyncio.Queue`, `dataclass`, `threading`, `time`, `json`, `re`)。

### 12.2 版本兼容性

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.9+ | 维持不变 |
| FastAPI | 维持现有 | 不引入新依赖 |
| watchdog | 维持现有 | 不改变文件监听 |
| Vue 3 | 维持现有 | C0 前端约 20 行改动 |

---

## 13. 设计评审点

### 13.1 关键技术决策

| 决策点 | 选择 | 理由 | 风险 |
|-------|------|------|------|
| EventBus 实现 | asyncio.Queue | 单进程内足够，零新增依赖 | 进程崩溃后队列丢失 |
| Metrics 实现 | 进程内 Counter/Histogram | 避免 Prometheus SDK 依赖 | 功能有限（无 pull model、无 alert） |
| C0 移除 `_periodic_broadcast_loop` | 移除 (PM 决策) | 完全依赖 EventBus 事件驱动，避免双通道 | 无双通道风险 |
| StateStore 锁类型 | asyncio.Lock | asyncio 环境内最优；单进程无需线程锁 | 不可从同步线程直接调用 |
| tail-read 策略 | byte-level seek (512KB) | 复用 session_reader 已验证的实现 | 极端行长（>10KB/行）可能截断 |

### 13.2 待确认事项

| 事项 | 选项 | 建议 | 状态 |
|------|------|------|---------|
| ~~C0 后端同时推送 `full_state` 和 `FullStateSnapshot`~~ | ~~A) 同时推双格式 B) 仅推新格式~~ | — | **已解决**: bootstrap 只推 `full_state`（旧格式），FullStateSnapshot 延到 C1 |
| ~~C0 `_periodic_broadcast_loop` 保留还是移除~~ | ~~A) 保留为补强 B) 移除~~ | — | **已解决**: PM 决策选 B) 移除，C0 一并移除 |
| `AgentStateIngestor` 的 jsonl 状态提取策略 | A) 仅 tail-read 提取 B) tail-read + status_calculator 计算 | **A) 仅 tail-read 提取** — 轻量；见 §2.1.4 状态投影规则。**PM 决策**: 选 A，加轻量补充 — tail-read 无法提取 status/error 时，仅对该 agent 调 `calculate_agent_status()`，不作为 periodic 兜底 | **已解决**: PM 选 A + 轻量 fallback
---

## 14. 附录

### 14.1 物理签章验证记录

| 源文件 | 验证目的 | 验证结论 |
|-------|---------|---------|
| `watchers/file_watcher.py` | 确认 `_on_file_changed()` 确实直接调用 `broadcast_full_state()` | ✅ 确认：L158 `from api.websocket import broadcast_full_state`; L168 `asyncio.run_coroutine_threadsafe(broadcast_full_state(), loop)` |
| `status/change_tracker.py` | 确认 MAX_SNAPSHOTS=10 逻辑缺陷 | ✅ 确认：L21 `MAX_SNAPSHOTS = 10`; L51-57 按更新时间排序保留最近 10 个 |
| `status/status_cache.py` | 确认 TTL + mtime 双验证机制 | ✅ 确认：`get()` 中先检查 TTL，再检查 mtime 指纹 |
| `api/websocket.py` | 确认 `broadcast_full_state()` 串行调用 7 个数据源 | ✅ 确认：L207-234 串行 await 7 个函数 |
| `data/session_reader.py` | 确认 `_read_tail_lines()` 的 tail-read 实现 | ✅ 确认：L136-152 byte-level seek 512KB + 行分割 |
| `status/status_calculator.py` | 确认 `get_changed_agents()` 伪异步（无 await） | ✅ 确认：L390-467 声明 `async def` 但内部全部同步调用，无任何 `await` |
| `RealtimeDataManager.ts` | 确认前端 `handleMessage()` 处理 `full_state` 和 `state_update` | ✅ 确认：L126 `message.type === 'full_state'`; L138 `message.type === 'state_update'` emit `agents_update` |
| `StateManager.ts` | 确认前端 merge 逻辑 | ✅ 确认：`setState()` 直接替换值；`batchUpdate()` 逐 key setState。无字段级 patch merge |

### 14.2 文件变更清单

| 变更类型 | 文件路径 | 分期 | 说明 |
|---------|---------|-----|------|
| **新增** | `src/backend/events/__init__.py` | C0 | 模块初始化 |
| **新增** | `src/backend/events/event_bus.py` | C0 | EventBus 核心 |
| **新增** | `src/backend/events/file_change_classifier.py` | C0 | 文件分类器 |
| **新增** | `src/backend/state/__init__.py` | C0 | 模块初始化 |
| **新增** | `src/backend/state/state_store.py` | C0 | StateStore |
| **新增** | `src/backend/ingest/__init__.py` | C0 | 模块初始化 |
| **新增** | `src/backend/ingest/agent_ingestor.py` | C0 | AgentStateIngestor |
| **新增** | `src/backend/metrics/__init__.py` | C0 | 模块初始化 |
| **新增** | `src/backend/metrics/metrics.py` | C0 | MetricsCollector |
| **新增** | `src/backend/api/metrics.py` | C0 | GET /api/metrics 端点 |
| **新增** | `src/backend/ingest/checkpoint_manager.py` | C1 | Checkpoint 管理 |
| **新增** | `src/backend/ingest/collaboration_ingestor.py` | C2 | Collaboration 增量摄入 |
| **修改** | `src/backend/watchers/file_watcher.py` | C0 | `_on_file_changed()` 改为 EventBus publish |
| **修改** | `src/backend/api/websocket.py` | C0 | WS Broadcaster + schemaVersion 协商 |
| **修改** | `src/backend/core/config_fortify.py` | C0 | 新增 8 个 ECS 配置项 |
| **修改** | `src/backend/status/change_tracker.py` | C0 | MAX_SNAPSHOTS 修复 |
| **修改** | `src/backend/main.py` (或等效入口) | C0 | 启动初始化 EventBus/Ingestor/StateStore |
| **修改** | `frontend/src/managers/RealtimeDataManager.ts` | C0 | 新增 AgentStateChanged 处理（~20 行） |
| **修改** | `src/backend/ingest/agent_ingestor.py` | C1 | offset-read 升级 |
| **修改** | `src/backend/status/status_calculator.py` | C1 | 有界并行化 |
| **修改** | `src/backend/core/error_handler.py` | C1 | 异步化 |
| **修改** | `src/backend/api/collaboration.py` | C2 | 独立事件源 |
| **修改** | `src/backend/api/performance.py` | C2 | 独立慢通道 |
| **修改** | `src/backend/api/websocket.py` | C2 | FullStateSnapshot 瘦身 |
| **修改** | `frontend/src/managers/RealtimeDataManager.ts` | C3 | 统一事件处理 |
| **修改** | `frontend/src/managers/StateManager.ts` | C3 | Patch 模型 |
| **不动** | `src/backend/status/status_cache.py` | — | 降级为冷启动/降级回退，代码不变 |
| **不动** | `src/backend/data/session_reader.py` | — | C0 复用 `_read_tail_lines()` 逻辑，不修改原文件 |

---

**文档版本**: v1.1.0  
**最后更新**: 2026-05-28  
**审核状态**: 评审后修订 v1.1.0 — 全部 3 项待确认已由 PM 拍板解决。签章升级为 **[SA_APPROVED]**。

**[SA_APPROVED]** 评审后修订 v1.1.0 — 全部 3 个 AMBIGUITY 已由 PM 拍板解决（bootstrap 只推 full_state、periodic loop 移除、Ingestor 选 A + 轻量 fallback）。PRD 同步更新完成。
