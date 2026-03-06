# TR5: 工作状态详细展示优化

## 状态: ✅ 已完成

## 背景
基于 `docs/dashboard-analysis.md` 分析报告第2节，当前 Agent 状态只有 `idle/working/down` 三种，无法体现 Agent 正在执行的具体动作。

用户期望看到：
- Agent 正在思考还是执行工具
- 执行的是哪个工具（Read/Edit/Bash等）
- 等待的是模型响应还是子代理

## 需求详情

### REQ-1: 后端增加详细状态计算

**新增数据结构**:

```python
@dataclass
class DetailedStatus:
    status: str  # idle/working/down (主状态)
    sub_status: Optional[str] = None  # thinking/tool_executing/waiting_llm/waiting_child/streaming
    current_action: Optional[str] = None  # 动态显示，如 "执行: Read"
    tool_name: Optional[str] = None  # 当前执行的工具名
    waiting_for: Optional[str] = None  # 等待目标（agentId或模型名）
```

**子状态类型**:

| 子状态 | 触发条件 | 显示文本 |
|--------|----------|----------|
| thinking | 最近消息含 thinking 块 | "思考中..." |
| tool_executing | 最近有 toolCall 且无对应 toolResult | "执行: {toolName}" |
| waiting_llm | 最后活动>30秒且无新响应 | "等待模型响应" |
| waiting_child | 等待子代理完成 | "等待子代理" |
| streaming | 正在接收流式响应 | "接收响应中..." |

**涉及文件**:
- `src/backend/status/status_calculator.py` - 增加 `get_detailed_status()` 函数
- `src/backend/data/session_reader.py` - 增加 `get_latest_tool_call()` 函数

### REQ-2: API 返回详细状态

**修改 CollaborationNode**:

```python
class CollaborationNode(BaseModel):
    # ... 现有字段
    subStatus: Optional[str] = None  # 子状态
    currentAction: Optional[str] = None  # 当前动作
    toolName: Optional[str] = None  # 工具名
    waitingFor: Optional[str] = None  # 等待目标
```

**涉及文件**:
- `src/backend/api/collaboration.py` - 在构建节点时填充详细状态

### REQ-3: 前端展示详细状态

**AgentCard.vue 增强**:

```vue
<div class="status-detail" v-if="subStatus">
  <span class="sub-status-icon">{{ subStatusIcon }}</span>
  <span class="sub-status-text">{{ currentAction || subStatusText }}</span>
</div>
```

**涉及文件**:
- `frontend/src/components/AgentCard.vue` - 增加详细状态展示
- `frontend/src/types/collaboration.ts` - 更新类型定义

## 实现步骤

### Step 1: 后端详细状态计算

```python
# status_calculator.py

def get_detailed_status(agent_id: str) -> Dict[str, Any]:
    """获取 Agent 详细状态"""
    from data.session_reader import get_latest_tool_call, has_thinking_block

    base_status = calculate_agent_status(agent_id)

    if base_status != 'working':
        return {
            'status': base_status,
            'subStatus': None,
            'currentAction': None,
            'toolName': None,
            'waitingFor': None
        }

    # 检查是否在执行工具
    tool_call = get_latest_tool_call(agent_id)
    if tool_call and not tool_call.get('hasResult'):
        return {
            'status': 'working',
            'subStatus': 'tool_executing',
            'currentAction': f"执行: {tool_call.get('name', 'unknown')}",
            'toolName': tool_call.get('name'),
            'waitingFor': None
        }

    # 检查是否有 thinking 块
    if has_thinking_block(agent_id):
        return {
            'status': 'working',
            'subStatus': 'thinking',
            'currentAction': '思考中...',
            'toolName': None,
            'waitingFor': None
        }

    # 检查是否在等待子代理
    from data.subagent_reader import get_active_runs
    for run in get_active_runs():
        if f'agent:{agent_id}:' in run.get('requesterSessionKey', ''):
            child_key = run.get('childSessionKey', '')
            child_agent = _parse_agent_id(child_key)
            return {
                'status': 'working',
                'subStatus': 'waiting_child',
                'currentAction': f'等待: {child_agent}',
                'toolName': None,
                'waitingFor': child_agent
            }

    # 默认：等待模型响应
    return {
        'status': 'working',
        'subStatus': 'waiting_llm',
        'currentAction': '等待模型响应',
        'toolName': None,
        'waitingFor': None
    }
```

### Step 2: session_reader 增加辅助函数

```python
# session_reader.py

def get_latest_tool_call(agent_id: str) -> Optional[Dict[str, Any]]:
    """获取最近的工具调用（未完成的）"""
    messages = get_recent_messages(agent_id, limit=20)

    for msg in reversed(messages):
        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            for c in content:
                if c.get('type') == 'toolCall':
                    tool_id = c.get('id')
                    tool_name = c.get('name')
                    # 检查是否有对应的 toolResult
                    has_result = _has_tool_result(messages, tool_id)
                    return {
                        'id': tool_id,
                        'name': tool_name,
                        'hasResult': has_result
                    }
    return None

def _has_tool_result(messages: List[Dict], tool_id: str) -> bool:
    """检查是否有对应工具的结果"""
    for msg in messages:
        if msg.get('role') == 'toolResult':
            # toolResult 通常通过 toolCallId 关联
            if msg.get('toolCallId') == tool_id:
                return True
    return False

def has_thinking_block(agent_id: str) -> bool:
    """检查最近消息是否有 thinking 块"""
    messages = get_recent_messages(agent_id, limit=5)
    for msg in reversed(messages):
        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            for c in content:
                if c.get('type') == 'thinking':
                    return True
    return False
```

### Step 3: API 集成

```python
# collaboration.py - 在构建节点时调用

from status.status_calculator import get_detailed_status

# 在构建每个 agent 节点时
detailed = get_detailed_status(agent_id)
sub_node = CollaborationNode(
    # ... 现有字段
    subStatus=detailed.get('subStatus'),
    currentAction=detailed.get('currentAction'),
    toolName=detailed.get('toolName'),
    waitingFor=detailed.get('waitingFor'),
)
```

### Step 4: 前端展示

```vue
<!-- AgentCard.vue -->
<div class="status-detail" v-if="agent.subStatus" :class="`sub-status-${agent.subStatus}`">
  <span class="sub-status-icon">{{ subStatusIcon }}</span>
  <span class="sub-status-text">{{ agent.currentAction }}</span>
</div>
```

## 验收标准

1. Agent 卡片显示详细子状态（思考中/执行工具/等待子代理）
2. 工具执行时显示具体工具名（执行: Read / 执行: Edit / 执行: Bash 等）
3. 等待子代理时显示目标 Agent 名称
4. 不影响原有状态显示逻辑

## 测试用例

### TC-1: 工具执行状态
- 操作: Agent 执行 Read 工具
- 期望: 显示 "执行: Read"

### TC-2: 思考状态
- 操作: Agent 收到任务开始思考
- 期望: 显示 "思考中..."

### TC-3: 等待子代理
- 操作: 主 Agent 派发任务给子 Agent
- 期望: 主 Agent 显示 "等待: analyst-agent"

## 时间估算
- 实现时间: 60 分钟
- 测试验证: 20 分钟

## 依赖
- TR4 已完成 ✅
