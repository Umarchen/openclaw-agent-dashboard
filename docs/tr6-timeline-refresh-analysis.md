# 时序视图刷新按钮问题分析

## 问题描述

在协作流程界面中，点击 Agent 卡片打开详情面板后，时序视图中的「刷新」按钮点击后没有效果，无法及时获取子 Agent 的执行时序。

## 问题分析

### 1. 刷新功能链路分析

时序视图的刷新按钮位于 `TimelineView.vue`:

```vue
<!-- frontend/src/components/timeline/TimelineView.vue:16-18 -->
<button class="refresh-btn" @click="refresh" :disabled="loading">
  {{ loading ? '加载中...' : '🔄 刷新' }}
</button>
```

`refresh()` 函数的实现：

```typescript
// frontend/src/components/timeline/TimelineView.vue:231-253
async function refresh() {
  if (!props.agentId) return
  loading.value = true
  error.value = null

  try {
    let url = `/api/timeline/${props.agentId}?limit=100`
    if (props.sessionKey) {
      url += `&session_key=${encodeURIComponent(props.sessionKey)}`
    }

    const res = await fetch(url)
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }
    data.value = await res.json()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
    console.error('Timeline load error:', e)
  } finally {
    loading.value = false
  }
}
```

**结论**：前端刷新逻辑是正确的，会发送 HTTP 请求获取最新数据。

### 2. 后端数据读取机制

后端 Timeline API 路由在 `src/backend/api/timeline.py`，核心调用 `get_timeline_steps()` 函数（位于 `src/backend/data/timeline_reader.py`）。

关键问题在于 **数据读取方式**：

```python
# src/backend/data/timeline_reader.py:529-558
def get_timeline_steps(agent_id, session_key=None, limit=100, round_mode=True):
    sessions_path = OPENCLAW_DIR / f"agents/{agent_id}/sessions"

    # 问题1: 如果没有 sessions 目录，直接返回子代理简化数据
    if not sessions_path.exists() or not list(sessions_path.glob("*.jsonl")):
        return _get_subagent_timeline(agent_id, limit)

    # 问题2: session 文件选择逻辑
    if session_key:
        # 从 sessions.json 索引查找指定 session
        ...
    else:
        # 默认取最新的 session 文件
        jsonl_files = list(sessions_path.glob("*.jsonl"))
        jsonl_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        session_file = jsonl_files[0]
```

### 3. 核心问题定位

#### 问题 A：子 Agent 无独立 Session 文件

**子 Agent 的会话数据不在自己的 `sessions/` 目录下**。

OpenClaw 的子代理机制：
- 子 Agent 由主 Agent 通过 `Task` 工具调用创建
- 子 Agent 的会话活动记录在 **主 Agent 的 session 文件** 中
- 子 Agent 自己的 `~/.openclaw/agents/{agent_id}/sessions/` 目录可能为空或不存在

当后端检测到子 Agent 没有独立 session 时，会调用 `_get_subagent_timeline()`：

```python
# src/backend/data/timeline_reader.py:569-628
def _get_subagent_timeline(agent_id, limit):
    runs_by_agent = get_subagent_runs()
    runs = runs_by_agent.get(agent_id, [])

    if not runs:
        return {
            "status": "no_sessions",
            "steps": [],
            "message": "该 Agent 尚无独立会话记录。子 Agent 的活动记录在 Main Agent 的会话中。"
        }
    # ...返回简化的运行记录
```

**问题**：`get_subagent_runs()` 只读取 `~/.openclaw/subagents/runs.json`，这个文件不会实时更新。

#### 问题 B：Session 文件缓存

即使 Agent 有独立 session 文件，后端每次都 **重新读取整个文件**：

```python
# src/backend/data/timeline_reader.py:652-653
with open(session_file, 'r', encoding='utf-8') as f:
    for line in f:
        # 逐行解析...
```

这部分是正确的，应该能获取最新数据。

#### 问题 C：自动刷新被禁用

在 `AgentDetailPanel.vue` 中，时序视图的 `autoRefresh` 被设置为 `false`：

```vue
<!-- frontend/src/components/AgentDetailPanel.vue:118-123 -->
<div v-if="activeView === 'timeline'" class="timeline-container">
  <TimelineView
    :agentId="agent.id"
    :autoRefresh="false"  <!-- 禁用了自动刷新 -->
  />
</div>
```

这意味着用户必须 **手动点击刷新按钮** 才能更新数据。

### 4. 子 Agent 时序数据延迟的真正原因

综合分析，子 Agent 执行时序不及时的原因：

1. **架构限制**：子 Agent 的会话记录在主 Agent 的 session 中，Dashboard 无法直接访问
2. **数据源依赖**：`_get_subagent_timeline()` 依赖 `runs.json`，该文件由 OpenClaw 在任务完成后才更新
3. **无实时推送**：Dashboard 没有订阅子 Agent 状态变化的 WebSocket 事件

---

## 方案 3 详解：WebSocket 实时推送子 Agent 状态

### 现有 WebSocket 架构

Dashboard 已有完整的 WebSocket 基础设施：

```
┌─────────────────┐                    ┌─────────────────┐
│   Frontend      │                    │    Backend      │
│                 │    WebSocket       │                 │
│ RealtimeData    │◄──────────────────►│  websocket.py   │
│    Manager      │    ws://host/ws    │                 │
└─────────────────┘                    └────────┬────────┘
                                                │
                                                ▼
                                       ┌────────────────┐
                                       │  OpenClaw      │
                                       │  数据文件       │
                                       │  (sessions/,   │
                                       │   runs.json)   │
                                       └────────────────┘
```

### 当前数据流

1. **后端定时推送**（每 3 秒）：
```python
# src/backend/api/websocket.py:23-28
async def _periodic_broadcast_loop():
    while True:
        await asyncio.sleep(BROADCAST_INTERVAL_SEC)  # 3秒
        if active_connections:
            await broadcast_full_state()
```

2. **推送内容**（`broadcast_full_state`）：
```python
# src/backend/api/websocket.py:188-229
await broadcast_message({
    "type": "full_state",
    "data": {
        "agents": agents,
        "subagents": subagents,
        "apiStatus": api_status,
        "collaboration": collaboration,  # ← 包含 CollaborationFlow
        "tasks": tasks,
        "performance": performance,
        "workflows": workflows,
    },
})
```

3. **前端订阅处理**：
```typescript
// frontend/src/managers/RealtimeDataManager.ts:177-186
if (message.type === 'full_state' && message.data) {
    if (data.collaboration) this.emit('collaboration', data.collaboration)
    // ...
}

// frontend/src/components/collaboration/CollaborationFlowSection.vue:514
unsubscribe = subscribe('collaboration', handleCollaborationUpdate)
```

### 问题：为什么子 Agent 时序不实时？

当前 `collaboration` 数据只包含：
- Agent 状态（idle/working/error）
- 任务节点
- 模型调用记录（recentCalls）

**缺少**：子 Agent 的执行步骤（thinking、toolCall、toolResult）

### 实现方案：扩展 WebSocket 推送子 Agent 步骤

#### 方案 3.1：在 CollaborationDynamic 中增加步骤数据

**1. 扩展后端数据模型**

```python
# src/backend/api/collaboration.py

class AgentTimelineStep(BaseModel):
    """单个 Agent 的最新执行步骤"""
    agentId: str
    steps: List[Dict[str, Any]]  # 最近 N 条步骤
    lastUpdate: int

class CollaborationDynamic(BaseModel):
    """动态数据 + 子 Agent 步骤"""
    # ... 现有字段 ...

    # 新增：每个 Agent 的最新步骤
    agentSteps: Optional[Dict[str, List[Dict]]] = None  # agentId -> steps
```

**2. 实现步骤读取函数**

```python
# src/backend/data/timeline_reader.py

def get_latest_steps_for_agent(agent_id: str, limit: int = 10) -> List[Dict]:
    """
    获取 Agent 的最新执行步骤（轻量版，用于 WebSocket 推送）

    优先级：
    1. Agent 自己的 session 文件
    2. 主 Agent session 中与该 Agent 相关的内容
    """
    # 尝试读取 Agent 自己的 session
    sessions_path = OPENCLAW_DIR / f"agents/{agent_id}/sessions"
    if sessions_path.exists():
        session_file = get_latest_session_file(agent_id)
        if session_file:
            return _read_recent_steps(session_file, limit)

    # 回退：从主 Agent session 中过滤相关内容
    return _get_subagent_steps_from_main(agent_id, limit)

def _read_recent_steps(session_file: Path, limit: int) -> List[Dict]:
    """读取 session 文件最后 N 条消息，转换为步骤"""
    steps = []
    lines = _read_tail_lines(session_file, limit * 3)  # 多读一些行

    for line in reversed(lines):
        data = json.loads(line)
        if data.get('type') != 'message':
            continue
        step = _parse_message_to_step(data.get('message', {}))
        if step:
            steps.append(step)
        if len(steps) >= limit:
            break

    return list(reversed(steps))

def _get_subagent_steps_from_main(subagent_id: str, limit: int) -> List[Dict]:
    """从主 Agent session 中提取子 Agent 相关步骤"""
    main_session = get_latest_session_file('main')
    if not main_session:
        return []

    # 标记：子 Agent 回传消息的特征
    subagent_markers = [
        f"agent:{subagent_id}:",
        f"Result from {subagent_id}",
    ]

    steps = []
    with open(main_session, 'r') as f:
        for line in f:
            data = json.loads(line)
            msg = data.get('message', {})
            content = str(msg.get('content', ''))

            # 检查是否与该子 Agent 相关
            if any(marker in content for marker in subagent_markers):
                step = _parse_message_to_step(msg)
                if step:
                    steps.append(step)

    return steps[-limit:]
```

**3. 修改 WebSocket 推送逻辑**

```python
# src/backend/api/websocket.py

async def broadcast_full_state():
    # ... 现有逻辑 ...

    # 新增：获取各 Agent 的最新步骤
    agent_steps = {}
    for agent in agents:
        agent_id = agent.get('id')
        if agent_id:
            try:
                agent_steps[agent_id] = get_latest_steps_for_agent(agent_id, limit=5)
            except Exception:
                agent_steps[agent_id] = []

    await broadcast_message({
        "type": "full_state",
        "data": {
            # ... 现有字段 ...
            "agentSteps": agent_steps,  # 新增
        },
    })
```

**4. 前端处理新增数据**

```typescript
// frontend/src/managers/RealtimeDataManager.ts

private handleMessage(message: WebSocketMessage): void {
    if (message.type === 'full_state' && message.data) {
        const data = message.data as Record<string, unknown>
        // ... 现有处理 ...

        // 新增：处理 agentSteps
        if (data.agentSteps) {
            this.emit('agent-steps', data.agentSteps)
        }
    }
}
```

**5. TimelineView 订阅实时步骤**

```typescript
// frontend/src/components/timeline/TimelineView.vue

import { useRealtime } from '../../composables'

const { subscribe } = useRealtime()

// 订阅实时步骤更新
onMounted(() => {
    unsubscribeSteps = subscribe('agent-steps', (data: Record<string, any[]>) => {
        if (data[props.agentId]) {
            // 合并新步骤到现有数据
            mergeNewSteps(data[props.agentId])
        }
    })
})

function mergeNewSteps(newSteps: any[]) {
    if (!data.value) return

    // 去重合并
    const existingIds = new Set(data.value.steps.map(s => s.id))
    const uniqueNew = newSteps.filter(s => !existingIds.has(s.id))

    if (uniqueNew.length > 0) {
        data.value.steps.push(...uniqueNew)
        // 重新计算统计
        recalculateStats()
    }
}
```

#### 方案 3.2：独立的事件驱动推送（更实时）

如果 OpenClaw 支持 Hook，可以实现更实时的推送：

```
┌──────────────┐     Hook/Event      ┌──────────────┐
│   OpenClaw   │ ──────────────────► │   Backend    │
│   Agent 执行  │   session 写入事件   │  WebSocket   │
└──────────────┘                     └──────┬───────┘
                                            │
                                            ▼ 立即推送
                                     ┌──────────────┐
                                     │   Frontend   │
                                     │  实时更新 UI  │
                                     └──────────────┘
```

**实现步骤**：

1. **OpenClaw 侧添加事件 Hook**（需要 OpenClaw 支持）：
```typescript
// OpenClaw 中触发事件
onSessionMessage((agentId, message) => {
    // 发送到 Dashboard 的 HTTP endpoint 或共享队列
    fetch('http://localhost:8765/internal/session-event', {
        method: 'POST',
        body: JSON.stringify({ agentId, message })
    })
})
```

2. **Backend 添加事件接收端点**：
```python
# src/backend/api/internal.py

from fastapi import APIRouter
from api.websocket import broadcast_message

router = APIRouter()

@router.post("/internal/session-event")
async def handle_session_event(event: dict):
    """接收 OpenClaw 的 session 事件，立即广播"""
    agent_id = event.get('agentId')
    message = event.get('message')

    # 转换为步骤格式
    step = parse_message_to_step(message)

    # 立即推送到所有连接的客户端
    await broadcast_message({
        "type": "agent_step",
        "data": {
            "agentId": agent_id,
            "step": step,
            "timestamp": int(time.time() * 1000)
        }
    })

    return {"status": "ok"}
```

3. **前端处理实时步骤事件**：
```typescript
// frontend/src/managers/RealtimeDataManager.ts

private handleMessage(message: WebSocketMessage): void {
    // 新增：处理单个步骤事件
    if (message.type === 'agent_step') {
        this.emit('agent-step', message.data)
        return
    }
    // ...
}
```

### 方案对比

| 特性 | 方案 3.1（定时推送） | 方案 3.2（事件驱动） |
|------|---------------------|---------------------|
| 实时性 | 3 秒延迟 | 毫秒级 |
| 实现复杂度 | 低（仅改 Dashboard） | 中（需 OpenClaw 配合） |
| 资源消耗 | 固定轮询开销 | 按需触发 |
| 可靠性 | 高（定时全量同步） | 依赖事件不丢失 |

### 推荐实现路径

1. **短期**：实现方案 3.1，在现有定时推送中增加 `agentSteps` 字段
2. **中期**：优化步骤读取性能，使用增量读取而非全量解析
3. **长期**：与 OpenClaw 团队协作，实现方案 3.2 的事件驱动推送

---

## 其他解决方案

### 方案 1：实时从主 Agent Session 读取子 Agent 活动

修改 `_get_subagent_timeline()` 或新增逻辑：

```python
def get_timeline_steps(agent_id, session_key=None, limit=100, round_mode=True):
    # 1. 先检查子 Agent 自己的 sessions
    # 2. 如果为空，查找主 Agent 的 session，过滤与该子 Agent 相关的消息
    # 3. 通过 session_key 或 runs.json 建立关联
```

需要 OpenClaw 提供：
- 子 Agent 对应的主 Agent session 文件路径
- 或者子 Agent 活动的独立 session 记录

### 方案 2：启用自动刷新 + 优化轮询

修改 `AgentDetailPanel.vue`：

```vue
<TimelineView
  :agentId="agent.id"
  :autoRefresh="true"
  :refreshInterval="5"  <!-- 5秒刷新一次 -->
/>
```

### 方案 4：读取主 Agent Session 中的子 Agent 相关内容

在 `timeline_reader.py` 中增加逻辑：

```python
def get_subagent_timeline_from_main_session(subagent_id, limit=50):
    """从主 Agent 的 session 中提取子 Agent 相关活动"""
    main_session = get_latest_session_file('main')
    if not main_session:
        return empty_result()

    steps = []
    with open(main_session, 'r') as f:
        for line in f:
            data = json.loads(line)
            # 过滤包含子 Agent ID 的消息
            if contains_subagent_reference(data, subagent_id):
                steps.append(parse_step(data))
    return steps[-limit:]
```

---

## 总结

| 问题 | 原因 | 影响 |
|------|------|------|
| 刷新按钮无响应 | 按钮功能正常，但数据源不更新 | 子 Agent 时序无法实时显示 |
| 子 Agent 无独立 session | OpenClaw 架构设计，子 Agent 活动记录在主 Agent session | Dashboard 只能读取简化数据 |
| 数据源依赖 runs.json | 该文件仅在任务完成时更新 | 无法获取进行中的执行状态 |

**根本原因**：Dashboard 的时序视图设计基于每个 Agent 有独立 session 文件的假设，但 OpenClaw 的子 Agent 实现将活动记录在主 Agent session 中，导致数据源不匹配。

**最快解决方案**：启用自动刷新（方案 2），但这只是缓解，不能解决数据源问题。

**最佳解决方案**：
- 数据层面：方案 1 或 方案 4，从主 Agent session 中提取子 Agent 相关内容
- 实时性：方案 3.1（短期）+ 方案 3.2（长期），通过 WebSocket 推送实时步骤
