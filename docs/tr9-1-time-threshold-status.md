# TR9-1: 基于时间阈值的状态显示

> 需求文档：优化 Agent 状态显示策略

## 1. 需求背景

### 1.1 当前问题

1. **一直显示"思考中"**：thinking 块判断过于宽松，无时间判断
2. **状态闪烁**：追求精确显示快速动作（<1s），导致 UI 频繁变化
3. **任务完成仍显示工作中**：2 分钟活跃窗口导致状态延迟

### 1.2 技术现实

Agent 的思考、工具执行通常非常快（几百毫秒到几秒），Dashboard 通过读取文件获取状态存在延迟：

```
Agent 执行动作 ──► 写入 JSONL 文件 ──► Dashboard 读取 ──► 前端显示
    │                  │                    │               │
   <1s              I/O 延迟            轮询间隔          渲染延迟
                    (10-100ms)          (3s)             (ms)
```

**结论**：等 Dashboard 读取到文件时，Agent 可能已经完成了思考/执行动作。

## 2. 解决方案

### 2.1 核心原则

1. **不追求精确**：快速动作无法精确捕获，不如不显示
2. **关注异常**：只显示超过阈值的"卡顿"状态
3. **提供上下文**：显示等待对象、持续时间
4. **减少闪烁**：用"处理中..."作为过渡状态

### 2.2 时间阈值设计

| 状态类型 | 阈值 | 显示内容 | 警告阈值 |
|----------|------|----------|----------|
| 等待模型响应 | 5s | "等待响应 ⏱Xs" | 15s |
| 等待模型（可能限流） | 15s | "等待响应 (可能限流) ⏱Xs ⚠️" | - |
| 等待子代理 | 3s | "等待 [agent名] ⏱Xs" | 60s |
| Bash 命令 | 2s | "执行命令 ⏱Xs" | 30s |
| 文件操作 | 2s | "读写文件 ⏱Xs" | - |
| 其他工具 | 3s | "执行工具 ⏱Xs" | - |
| 快速执行中 | - | "处理中..." | - |

### 2.3 状态显示流程

```
                    时间轴
    ─────────────────────────────────────────────►

    工具开始      阈值(2s)       工具结束
       │            │              │
       ▼            ▼              ▼
    ┌──────┐    ┌──────┐      ┌──────┐
    │ 处理中│───►│ 显示  │─────►│ 完成 │
    │ ...  │    │ 具体状态│      │      │
    └──────┘    └──────┘      └──────┘
```

## 3. 技术设计

### 3.1 后端修改

#### 3.1.1 新增：带时间戳的消息接口

**文件**: `src/backend/data/session_reader.py`

```python
def get_recent_messages_with_timestamp(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    获取最近的会话消息（包含时间戳）

    Returns:
        [{'message': {...}, 'timestamp': int, 'data_timestamp': int}, ...]
    """
    session_file = get_latest_session_file(agent_id)
    if not session_file:
        return []
    raw_lines = _read_tail_lines(session_file, max(limit * 5, 500))
    messages = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if data.get('type') == 'message':
                messages.append({
                    'message': data.get('message', {}),
                    'timestamp': data.get('message', {}).get('timestamp', 0),
                    'data_timestamp': data.get('timestamp', ''),
                })
                if len(messages) >= limit:
                    break
        except json.JSONDecodeError:
            continue
    return messages[-limit:]
```

#### 3.1.2 新增：带时间戳的工具调用检测

**文件**: `src/backend/data/session_reader.py`

```python
def get_pending_tool_call_with_timestamp(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    获取待处理的工具调用（包含时间戳）

    Returns:
        {'id': str, 'name': str, 'hasResult': bool, 'timestamp': int} or None
    """
    messages = get_recent_messages_with_timestamp(agent_id, limit=30)

    tool_calls = {}
    tool_results = set()

    for item in messages:
        msg = item.get('message', {})
        ts = item.get('timestamp', 0)

        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            if isinstance(content, str):
                continue
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'toolCall':
                    tool_id = c.get('id')
                    if tool_id:
                        tool_calls[tool_id] = {
                            'id': tool_id,
                            'name': c.get('name', 'unknown'),
                            'timestamp': ts,
                            'hasResult': False
                        }

        elif msg.get('role') == 'toolResult':
            tool_call_id = msg.get('toolCallId') or msg.get('tool_call_id')
            if tool_call_id:
                tool_results.add(tool_call_id)

    # 标记已有结果的 toolCall
    for tool_id in tool_calls:
        if tool_id in tool_results:
            tool_calls[tool_id]['hasResult'] = True

    # 返回最后一个未完成的 toolCall
    for tool_id in reversed(list(tool_calls.keys())):
        info = tool_calls[tool_id]
        if not info['hasResult']:
            return info

    return None
```

#### 3.1.3 新增：获取等待的子代理

**文件**: `src/backend/data/subagent_reader.py`

```python
def get_waiting_child_agent(agent_id: str) -> Optional[str]:
    """
    获取正在等待的子代理名称

    Returns:
        子代理名称，如果没有则返回 None
    """
    active_runs = get_active_runs()
    for run in active_runs:
        requester_key = run.get('requesterSessionKey', '')
        if f'agent:{agent_id}:' in requester_key:
            child_key = run.get('childSessionKey', '')
            if child_key and ':' in child_key:
                parts = child_key.split(':')
                if len(parts) >= 2 and parts[0] == 'agent':
                    return parts[1]
    return None
```

#### 3.1.4 新增：显示状态计算

**文件**: `src/backend/status/status_calculator.py`

```python
def get_display_status(agent_id: str) -> Dict[str, Any]:
    """
    获取用于前端显示的状态（基于时间阈值）

    Returns:
        {
            'status': 'idle' | 'working',
            'display': str,      # 显示文本
            'duration': int,     # 持续时间（秒）
            'alert': bool,       # 是否需要警告
        }
    """
    from data.session_reader import get_session_updated_at, get_pending_tool_call_with_timestamp
    from data.subagent_reader import is_agent_working, get_waiting_child_agent

    # 无任务
    if not is_agent_working(agent_id):
        return {'status': 'idle', 'display': '空闲', 'duration': 0, 'alert': False}

    # 计算空闲时间
    last_activity = get_session_updated_at(agent_id)
    now = int(time.time() * 1000)
    idle_seconds = int((now - last_activity) / 1000) if last_activity else 0

    # 检查等待子代理
    waiting_for = get_waiting_child_agent(agent_id)
    if waiting_for and idle_seconds > 3:
        return {
            'status': 'working',
            'display': f'等待 {waiting_for}',
            'duration': idle_seconds,
            'alert': idle_seconds > 60
        }

    # 检查工具执行
    tool_call = get_pending_tool_call_with_timestamp(agent_id)
    if tool_call:
        tool_timestamp = tool_call.get('timestamp', 0)
        tool_duration = int((now - tool_timestamp) / 1000) if tool_timestamp else 0
        tool_name = tool_call.get('name', '')

        if not tool_call.get('hasResult') and tool_duration > 2:
            if tool_name == 'Bash':
                return {'status': 'working', 'display': '执行命令', 'duration': tool_duration, 'alert': tool_duration > 30}
            elif tool_name in ('Write', 'Edit'):
                return {'status': 'working', 'display': '读写文件', 'duration': tool_duration, 'alert': False}
            elif tool_duration > 3:
                return {'status': 'working', 'display': '执行工具', 'duration': tool_duration, 'alert': False}

    # 检查等待模型
    if idle_seconds > 5:
        alert = idle_seconds > 15
        display = '等待响应' + (' (可能限流)' if alert else '')
        return {'status': 'working', 'display': display, 'duration': idle_seconds, 'alert': alert}

    # 快速执行中
    return {'status': 'working', 'display': '处理中...', 'duration': 0, 'alert': False}
```

### 3.2 API 修改

#### 3.2.1 新增返回字段

**文件**: `src/backend/api/collaboration.py`

在 `CollaborationDynamic` 模型中新增：

```python
class AgentDisplayStatus(BaseModel):
    """Agent 显示状态"""
    status: str  # 'idle' | 'working'
    display: str
    duration: int
    alert: bool


class CollaborationDynamic(BaseModel):
    """动态数据模型"""
    activePath: list
    recentCalls: list
    agentStatuses: Dict[str, str]
    agentDynamicStatuses: Optional[Dict[str, AgentDisplayStatus]] = None  # 新增
    taskNodes: list
    taskEdges: list
    mainAgentId: str
    lastUpdate: int
```

#### 3.2.2 填充 agentDynamicStatuses

```python
@router.get("/collaboration/dynamic", response_model=CollaborationDynamic)
async def get_collaboration_dynamic():
    # ... 现有逻辑 ...

    # 添加显示状态
    agent_dynamic_statuses = {}
    for agent in agents_list:
        aid = agent.get('id', '')
        if aid:
            try:
                agent_dynamic_statuses[aid] = get_display_status(aid)
            except Exception as e:
                logger.warning(f"Failed to get display status for {aid}: {e}")

    return CollaborationDynamic(
        # ...
        agentDynamicStatuses=agent_dynamic_statuses,
        # ...
    )
```

### 3.3 前端修改

#### 3.3.1 类型定义更新

**文件**: `frontend/src/types/collaboration.ts`

```typescript
export interface AgentDisplayStatus {
  status: 'idle' | 'working'
  display: string        // 显示文本
  duration: number       // 持续时间（秒）
  alert: boolean         // 是否需要警告
}

export interface CollaborationDynamic {
  activePath: string[]
  recentCalls: ModelCall[]
  agentStatuses: Record<string, string>
  agentDynamicStatuses?: Record<string, AgentDisplayStatus>  // 新增
  taskNodes: CollaborationNode[]
  taskEdges: CollaborationEdge[]
  mainAgentId: string
  lastUpdate: number
}
```

#### 3.3.2 组件更新

**文件**: `frontend/src/components/collaboration/CollaborationFlowSection.vue`

```typescript
function handleCollaborationDynamicUpdate(dyn: CollaborationDynamic): void {
  // 更新详细状态
  if (dyn.agentDynamicStatuses) {
    for (const node of agentNodesLocal) {
      if (node.id && dyn.agentDynamicStatuses[node.id]) {
        const dynStatus = dyn.agentDynamicStatuses[node.id]
        node.currentAction = dynStatus.display
        node.metadata = {
          ...node.metadata,
          duration: dynStatus.duration,
          alert: dynStatus.alert
        }
      }
    }
  }
}
```

## 4. 测试用例

### 4.1 单元测试

```python
def test_get_display_status_idle():
    """空闲状态"""
    with mock.patch('is_agent_working', return_value=False):
        result = get_display_status('test-agent')
        assert result['status'] == 'idle'
        assert result['display'] == '空闲'

def test_get_display_status_waiting_child():
    """等待子代理"""
    with mock.patch('is_agent_working', return_value=True):
    with mock.patch('get_waiting_child_agent', return_value='dev-agent'):
    with mock.patch('get_session_updated_at', return_value=now - 5000):
        result = get_display_status('main')
        assert result['status'] == 'working'
        assert '等待 dev-agent' in result['display']
        assert result['duration'] == 5

def test_get_display_status_bash_command():
    """执行 Bash 命令"""
    with mock.patch('is_agent_working', return_value=True):
    with mock.patch('get_waiting_child_agent', return_value=None):
    with mock.patch('get_pending_tool_call_with_timestamp', return_value={
        'name': 'Bash',
        'hasResult': False,
        'timestamp': now - 3000
    }):
        result = get_display_status('main')
        assert result['display'] == '执行命令'
        assert result['duration'] == 3
```

### 4.2 集成测试

1. **测试等待子代理**：
   - 主 Agent 派发任务给子 Agent
   - 检查主 Agent 显示 "等待 xxx"
   - 检查 duration 正确计算

2. **测试执行命令**：
   - 触发长时间运行的 Bash 命令
   - 检查显示 "执行命令" + duration

3. **测试限流警告**：
   - 模拟模型响应超过 15 秒
   - 检查显示 "等待响应 (可能限流)"

## 5. 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `session_reader.py` | 新增 `get_recent_messages_with_timestamp()`, `get_pending_tool_call_with_timestamp()` |
| `subagent_reader.py` | 新增 `get_waiting_child_agent()` |
| `status_calculator.py` | 新增 `get_display_status()` |
| `collaboration.py` | 新增 `AgentDisplayStatus` 模型，填充 `agentDynamicStatuses` |
| `collaboration.ts` | 更新类型定义 |
| `CollaborationFlowSection.vue` | 更新动态数据处理逻辑 |

## 6. 注意事项

1. **向后兼容**：`agentDynamicStatuses` 为可选字段，旧版前端可忽略
2. **性能考虑**：避免频繁调用 `get_pending_tool_call_with_timestamp()`，可考虑缓存
3. **时区处理**：确保所有时间戳使用 UTC
