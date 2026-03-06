# 协作流程状态刷新问题分析

## 问题概述

用户反馈的两个核心问题：

1. **各 Agent 显示的工作内容不够及时更新**：目前显示的都是"思考中"，不会实时反映当前动作
2. **任务完成后状态刷新不及时**：任务已完成，但各 Agent 仍显示"工作中"状态

---

## 问题一：Agent 工作内容更新不及时

### 现象分析

Agent 卡片显示 `currentAction`（如"思考中..."、"执行: Read"、"等待模型响应"），但往往停留在"思考中"状态，不能及时反映实际的工具执行或等待状态。

### 根因定位

#### 1. 状态计算逻辑的优先级问题

**文件**: `src/backend/status/status_calculator.py:136-197`

```python
def get_detailed_status(agent_id: str) -> dict:
    # 检查是否在执行工具（最近有 toolCall 且无对应 toolResult）
    tool_call = get_latest_tool_call(agent_id)
    if tool_call and not tool_call.get('hasResult'):
        return {...'subStatus': 'tool_executing'...}

    # 检查是否有 thinking 块
    if has_thinking_block(agent_id):
        return {...'subStatus': 'thinking'...}
```

**问题**：
- `has_thinking_block()` 只检查最近 5 条消息是否有 `type: 'thinking'` 的内容块
- 模型响应中 `thinking` 块会保留很长时间，即使已经执行完工具
- 只要历史消息中有 thinking 块，就会一直显示"思考中"

#### 2. Session 数据读取的延迟

**文件**: `src/backend/data/session_reader.py:276-330`

```python
def get_latest_tool_call(agent_id: str) -> Optional[Dict[str, Any]]:
    messages = get_recent_messages(agent_id, limit=30)
    # 遍历消息查找 toolCall 和 toolResult
```

**问题**：
- `get_recent_messages()` 只读取最近 30 条消息
- 对于长会话，可能无法正确匹配 toolCall 和 toolResult
- 依赖 JSONL 文件的尾部读取，可能有 I/O 延迟

#### 3. 前端轮询间隔

**文件**: `frontend/src/components/collaboration/CollaborationFlowSection.vue:182`

```typescript
const DYNAMIC_POLL_INTERVAL_MS = 3000  // 3秒轮询一次
```

**问题**：
- 3 秒的轮询间隔在快速变化的场景下显得太慢
- 用户可能在 3 秒内看到过时的状态

### 详细状态判断流程

```
get_detailed_status(agent_id)
    │
    ├─► 检查 has_recent_errors() ──► 是 ──► 返回 status='down'
    │
    ├─► 检查 is_agent_working() ──► 否 ──► 返回 status='idle'
    │
    ├─► 检查 has_recent_session_activity() ──► 否 ──► 返回 status='idle'
    │
    ├─► 检查 get_latest_tool_call() 是否有未完成的 ──► 是 ──► subStatus='tool_executing'
    │
    ├─► 检查 has_thinking_block() ──► 是 ──► subStatus='thinking'
    │
    ├─► 检查是否在等待子代理 ──► 是 ──► subStatus='waiting_child'
    │
    └─► 默认 ──► subStatus='waiting_llm'
```

### 问题总结

| 问题点 | 位置 | 影响 |
|--------|------|------|
| thinking 块判断过于宽松 | `session_reader.py:333-344` | 只要历史有 thinking 就显示思考中 |
| toolCall 匹配不完整 | `session_reader.py:276-330` | 长会话可能匹配失败 |
| 轮询间隔较长 | `CollaborationFlowSection.vue:182` | 3秒更新一次，状态滞后 |

---

## 问题二：任务完成后状态刷新不及时

### 现象分析

子 Agent 完成任务后，Dashboard 上仍显示"工作中"状态，需要较长时间才会变为"空闲"。

### 根因定位

#### 1. 状态判断依赖 runs.json 的 endedAt 字段

**文件**: `src/backend/data/subagent_reader.py:61-75`

```python
def is_agent_working(agent_id: str) -> bool:
    active_runs = get_active_runs()
    for run in active_runs:
        child_key = run.get('childSessionKey', '')
        requester_key = run.get('requesterSessionKey', '')
        if f'agent:{agent_id}:' in child_key:
            return True
        if f'agent:{agent_id}:' in requester_key:
            return True
    return False
```

**文件**: `src/backend/data/subagent_reader.py:40-43`

```python
def get_active_runs() -> List[Dict[str, Any]]:
    runs = load_subagent_runs()
    return [run for run in runs if run.get('endedAt') is None]
```

**问题**：
- `is_agent_working()` 完全依赖 `runs.json` 中 `endedAt` 是否为 `None`
- OpenClaw 框架在子 Agent 完成后写入 `endedAt` 可能有延迟
- 如果 OpenClaw 进程崩溃或异常退出，`endedAt` 可能永远不会被写入

#### 2. sessions.json 活跃检测的时间窗口

**文件**: `src/backend/status/status_calculator.py:38-39`

```python
if has_recent_session_activity(agent_id, minutes=2):
    return 'working'
```

**文件**: `src/backend/data/session_reader.py:163-170`

```python
def has_recent_session_activity(agent_id: str, minutes: int = 5) -> bool:
    updated_at = get_session_updated_at(agent_id)
    cutoff = int(time.time() * 1000) - (minutes * 60 * 1000)
    return updated_at > cutoff
```

**问题**：
- 使用 2 分钟的时间窗口判断是否活跃
- 即使 run 已结束，只要 2 分钟内有 session 更新，仍显示"工作中"
- 这是合理的安全机制，但会导致状态延迟 2 分钟才变为空闲

#### 3. WebSocket 推送间隔

**文件**: `src/backend/api/websocket.py:19`

```python
BROADCAST_INTERVAL_SEC = 3  # 周期性推送间隔
```

**文件**: `src/backend/api/websocket.py:188-231`

```python
async def broadcast_full_state():
    # 获取所有数据并广播
    agents = await get_agents_list()
    subagents = await get_subagents()
    ...
```

**问题**：
- 即使数据源（runs.json）已更新，也需要等待下一个 3 秒周期才会推送
- 没有文件变更监听机制，无法在 runs.json 更新时立即推送

#### 4. collaboration API 不返回详细状态

**文件**: `src/backend/api/collaboration.py:268-547`

`/api/collaboration` 接口返回的 `CollaborationNode` 不包含 `subStatus`、`currentAction` 等详细状态字段。

**文件**: `src/backend/api/collaboration.py:561-672`

`/api/collaboration/dynamic` 接口也没有返回 `agentDynamicStatuses`。

**前端**: `frontend/src/components/collaboration/CollaborationFlowSection.vue:462-468`

```typescript
// 更新详细状态 (TR5)
if (node.id && dyn.agentDynamicStatuses && dyn.agentDynamicStatuses[node.id]) {
    const dynStatus = dyn.agentDynamicStatuses[node.id]
    node.subStatus = dynStatus.subStatus
    ...
}
```

**问题**：
- 后端 `CollaborationDynamic` 模型定义了 `agentDynamicStatuses` 字段
- 但实际 `/api/collaboration/dynamic` 接口没有填充这个字段
- 前端虽然写了处理逻辑，但永远收不到数据

### 状态判断流程

```
calculate_agent_status(agent_id)
    │
    ├─► has_recent_errors(agent_id, minutes=5) ──► 是 ──► 'down'
    │
    ├─► is_agent_working(agent_id) ──► 是 ──► 'working'
    │       └─► 检查 runs.json 中是否有未结束的 run
    │
    ├─► has_recent_session_activity(agent_id, minutes=2) ──► 是 ──► 'working'
    │       └─► 检查 sessions.json 的 updatedAt 是否在 2 分钟内
    │
    └─► 默认 ──► 'idle'
```

### 问题总结

| 问题点 | 位置 | 影响 |
|--------|------|------|
| runs.json 更新延迟 | OpenClaw 框架 | endedAt 写入延迟导致状态不准 |
| 2分钟活跃窗口 | `status_calculator.py:38` | 即使任务完成，2分钟内仍显示工作中 |
| 无文件监听 | `websocket.py` | 被动轮询而非主动推送 |
| dynamic API 未填充详细状态 | `collaboration.py:561-672` | 前端无法获取 subStatus |

---

## 数据流图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         OpenClaw 框架                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │ Agent 执行   │───►│ runs.json    │    │ sessions/*.jsonl     │  │
│  │              │    │ (endedAt)    │    │ sessions.json        │  │
│  └──────────────┘    └──────┬───────┘    └──────────┬───────────┘  │
└─────────────────────────────┼───────────────────────┼──────────────┘
                              │                       │
                              ▼                       ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Dashboard 后端                                  │
│  ┌──────────────────┐    ┌──────────────────┐                      │
│  │ subagent_reader  │    │ session_reader   │                      │
│  │ is_agent_working │    │ has_recent_*     │                      │
│  └────────┬─────────┘    └────────┬─────────┘                      │
│           │                       │                                 │
│           └───────────┬───────────┘                                 │
│                       ▼                                             │
│           ┌───────────────────────┐                                │
│           │ status_calculator     │                                │
│           │ calculate_agent_status│                                │
│           │ get_detailed_status   │                                │
│           └───────────┬───────────┘                                │
│                       │                                             │
│                       ▼                                             │
│           ┌───────────────────────┐    ┌───────────────────────┐   │
│           │ collaboration.py      │    │ websocket.py          │   │
│           │ /api/collaboration    │    │ 3秒周期广播           │   │
│           │ /api/collab/dynamic   │    │ broadcast_full_state  │   │
│           └───────────┬───────────┘    └───────────┬───────────┘   │
└───────────────────────┼────────────────────────────┼───────────────┘
                        │                            │
                        │     WebSocket + HTTP       │
                        └────────────┬───────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Dashboard 前端                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ CollaborationFlowSection.vue                                  │  │
│  │ - fetchData() 初始加载                                        │  │
│  │ - fetchDynamicData() 3秒轮询                                  │  │
│  │ - subscribe('collaboration') WebSocket 更新                   │  │
│  └────────────────────────────┬─────────────────────────────────┘  │
│                               │                                     │
│                               ▼                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ AgentCard.vue                                                 │  │
│  │ - 显示 status (idle/working/down)                             │  │
│  │ - 显示 subStatus (thinking/tool_executing/waiting_*)          │  │
│  │ - 显示 currentAction (思考中.../执行: Read/等待模型响应)       │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 解决方案建议

### 问题一：工作内容更新不及时

#### 方案 A：优化 thinking 块判断逻辑

```python
# session_reader.py
def has_active_thinking_block(agent_id: str) -> bool:
    """检查最近一条 assistant 消息是否有活跃的 thinking 块"""
    messages = get_recent_messages(agent_id, limit=10)
    for msg in reversed(messages):
        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'thinking':
                    # 检查是否是最近的消息（5秒内）
                    ts = msg.get('timestamp', 0)
                    now = int(time.time() * 1000)
                    if now - ts < 5000:  # 5秒内的 thinking 才算活跃
                        return True
    return False
```

#### 方案 B：引入状态超时机制

```python
# status_calculator.py
def get_detailed_status(agent_id: str) -> dict:
    # ... 现有逻辑 ...

    # 如果 thinking 状态持续超过 30 秒，降级为 waiting_llm
    if sub_status == 'thinking':
        last_activity = get_last_assistant_message_time(agent_id)
        if time.time() * 1000 - last_activity > 30000:
            return {'status': 'working', 'subStatus': 'waiting_llm', ...}
```

#### 方案 C：缩短前端轮询间隔

```typescript
// CollaborationFlowSection.vue
const DYNAMIC_POLL_INTERVAL_MS = 1000  // 改为 1 秒
```

### 问题二：任务完成后状态刷新不及时

#### 方案 A：实现文件监听机制

```python
# websocket.py
import watchdog
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class RunFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('runs.json'):
            asyncio.run(broadcast_full_state())

observer = Observer()
observer.schedule(RunFileHandler(), path=str(SUBAGENTS_RUNS_PATH.parent))
observer.start()
```

#### 方案 B：填充 dynamic API 的详细状态

```python
# collaboration.py
@router.get("/collaboration/dynamic", response_model=CollaborationDynamic)
async def get_collaboration_dynamic():
    # ... 现有逻辑 ...

    # 添加详细状态
    from status.status_calculator import get_detailed_status
    agent_dynamic_statuses = {}
    for agent in agents_list:
        aid = agent.get('id', '')
        if aid:
            agent_dynamic_statuses[aid] = get_detailed_status(aid)

    return CollaborationDynamic(
        ...
        agentDynamicStatuses=agent_dynamic_statuses,  # 新增
        ...
    )
```

#### 方案 C：缩短活跃检测时间窗口

```python
# status_calculator.py
if has_recent_session_activity(agent_id, minutes=1):  # 从 2 分钟改为 1 分钟
    return 'working'
```

#### 方案 D：添加 endedAt 超时检测

```python
# subagent_reader.py
def is_agent_working(agent_id: str) -> bool:
    active_runs = get_active_runs()
    for run in active_runs:
        # 检查是否超时（超过 5 分钟无活动视为已结束）
        started = run.get('startedAt', 0)
        if time.time() * 1000 - started > 5 * 60 * 1000:
            continue  # 跳过超时的 run

        if f'agent:{agent_id}:' in child_key:
            return True
    return False
```

---

## 推荐实施优先级

| 优先级 | 方案 | 复杂度 | 效果 |
|--------|------|--------|------|
| P0 | 填充 dynamic API 详细状态 | 低 | 解决前端无法获取 subStatus 问题 |
| P0 | 优化 thinking 块判断 | 低 | 解决一直显示思考中的问题 |
| P1 | 缩短轮询间隔到 1 秒 | 低 | 提升状态更新速度 |
| P1 | 添加 endedAt 超时检测 | 中 | 防止僵尸 run 导致状态卡死 |
| P2 | 实现文件监听机制 | 高 | 实现真正的实时更新 |
| P2 | 缩短活跃检测窗口 | 低 | 减少状态延迟 |

---

## 相关文件

- `src/backend/status/status_calculator.py` - 状态计算核心逻辑
- `src/backend/data/session_reader.py` - Session 数据读取
- `src/backend/data/subagent_reader.py` - Subagent Run 数据读取
- `src/backend/api/collaboration.py` - 协作流程 API
- `src/backend/api/websocket.py` - WebSocket 推送
- `frontend/src/components/collaboration/CollaborationFlowSection.vue` - 协作流程前端组件
- `frontend/src/components/AgentCard.vue` - Agent 卡片组件
