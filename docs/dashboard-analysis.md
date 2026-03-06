# OpenClaw Agent Dashboard 工程分析报告

**分析日期**: 2026-03-06
**分析范围**: 状态刷新、工作状态优化、阻塞检测、子Agent LLM调用、卡片UI、时序视图

---

## 1. 任务结束后状态不准确问题

### 1.1 问题描述
执行任务后（老K给分析师派活），任务结束后老K和分析师仍显示"工作中"状态。

### 1.2 代码分析

**状态计算逻辑** (`src/backend/status/status_calculator.py:22-42`):

```python
def calculate_agent_status(agent_id: str) -> AgentStatus:
    # 检查异常
    if has_recent_errors(agent_id, minutes=5):
        return 'down'

    # 检查工作中：subagent run 未结束，或 session 最近有活动
    if is_agent_working(agent_id):
        return 'working'
    if has_recent_session_activity(agent_id, minutes=5):
        return 'working'

    # 默认空闲
    return 'idle'
```

**问题根源**:

1. **runs.json 刷新延迟**: `is_agent_working()` 检查 `runs.json` 中是否有 `endedAt == None` 的记录。文件可能未及时更新。

2. **session 活动检测窗口过长**: `has_recent_session_activity(agent_id, minutes=5)` 检查最近5分钟内是否有活动，即使任务已完成，只要5分钟内有活动就仍显示"工作中"。

3. **WebSocket 推送间隔**:
   - 文件监听防抖: `DEBOUNCE_SECONDS = 0.3` (`file_watcher.py:11`)
   - 周期性广播: `BROADCAST_INTERVAL_SEC = 8` (`websocket.py:19`)
   - 前端动态轮询: `DYNAMIC_POLL_INTERVAL_MS = 5000` (`CollaborationFlowSection.vue:178`)

### 1.3 优化建议

| 优化点 | 当前值 | 建议值 | 说明 |
|--------|--------|--------|------|
| session活动窗口 | 5分钟 | 2分钟 | 减少误判时间 |
| WebSocket广播间隔 | 8秒 | 3-5秒 | 提高状态更新频率 |
| 动态轮询间隔 | 5秒 | 3秒 | 更及时的UI更新 |
| 增加状态过渡态 | 无 | completing | 区分"正在完成"和"已完成" |

### 1.4 代码位置

- 状态计算: `src/backend/status/status_calculator.py:22-42`
- 子代理工作检测: `src/backend/data/subagent_reader.py:61-75`
- WebSocket广播: `src/backend/api/websocket.py:188-231`
- 文件监听: `src/backend/watchers/file_watcher.py`

---

## 2. 工作状态详细展示优化

### 2.1 当前状态展示

**AgentCard.vue 支持的状态**:
- `idle` - 空闲（绿色）
- `working` - 工作中（蓝色）
- `down` - 异常（红色）

**额外展示信息**:
- `stuckWarning` - 卡顿警告（超过60秒无响应）
- `error` - 错误信息

### 2.2 建议增加的详细状态

```
┌─────────────────────────────────────────────────────────────┐
│                    建议的状态细化方案                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  原状态        新增子状态              显示文本              │
│  ─────        ────────               ────────               │
│                                                              │
│  working  →   thinking              "思考中..."             │
│               tool_executing        "执行: {toolName}"      │
│               waiting_llm           "等待模型响应"          │
│               waiting_child         "等待子代理响应"        │
│               streaming             "接收响应中..."         │
│                                                              │
│  idle     →   idle_ready            "空闲，可接受任务"      │
│               idle_cooling          "冷却中(30s)"           │
│                                                              │
│  down     →   error_api             "API异常"               │
│               error_timeout         "响应超时"               │
│               error_rate_limit      "请求限流"               │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 实现建议

**后端数据结构** (`status_calculator.py`):

```python
@dataclass
class DetailedStatus:
    status: str  # idle/working/down
    sub_status: Optional[str] = None  # thinking/tool_executing/waiting_llm/...
    current_action: Optional[str] = None  # 动态显示，如 "执行: Read" / "执行: Edit" / "执行: Bash"
    tool_name: Optional[str] = None  # 当前执行的工具名（Read/Edit/Bash/Write等）
    progress: Optional[int] = None  # 0-100 进度条
    waiting_for: Optional[str] = None  # 等待的目标（agentId或模型名）
```

**前端展示** (`AgentCard.vue`):

```vue
<div class="status-detail">
  <span class="status-icon">{{ statusIcon }}</span>
  <!-- 动态显示当前动作，如 "执行: Read"、"执行: Bash" 等 -->
  <span class="status-action">{{ currentAction }}</span>
  <span v-if="waitingFor" class="waiting-info">等待: {{ waitingFor }}</span>
</div>
```

**常用工具类型**（动态填充 `{toolName}`）:

| 工具名 | 显示文本 | 说明 |
|--------|----------|------|
| Read | 执行: Read | 读取文件 |
| Edit | 执行: Edit | 编辑文件 |
| Write | 执行: Write | 写入文件 |
| Bash | 执行: Bash | 执行命令 |
| Glob | 执行: Glob | 文件匹配 |
| Grep | 执行: Grep | 内容搜索 |
| ToolSearch | 执行: ToolSearch | 工具搜索 |
| Agent | 执行: Agent | 调用子代理 |
| WebFetch | 执行: WebFetch | 获取网页 |
| WebSearch | 执行: WebSearch | 网页搜索 |

### 2.4 数据来源

| 子状态 | 数据来源 | 实现复杂度 |
|--------|----------|------------|
| thinking | session中最近assistant消息含thinking块 | 低 |
| tool_executing | session中最近toolCall的name字段（Read/Edit/Bash等） | 低 |
| waiting_llm | 最后活动时间>30秒且无响应 | 中 |
| waiting_child | runs.json中requesterSessionKey匹配 | 中 |
| streaming | WebSocket实时事件 | 高 |

**tool_executing 实现示例**:

```python
def get_current_tool_action(agent_id: str) -> Optional[str]:
    """获取Agent当前正在执行的工具"""
    messages = get_recent_messages(agent_id, limit=20)

    for msg in reversed(messages):
        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            for c in content:
                if c.get('type') == 'toolCall':
                    tool_name = c.get('name', 'unknown')
                    # 如果有对应的toolResult说明已执行完，继续查找
                    if not has_tool_result(msg, c.get('id')):
                        return f"执行: {tool_name}"
        elif msg.get('role') == 'toolResult':
            # 遇到toolResult说明最近的工具已执行完
            break

    return None  # 没有正在执行的工具
```

---

## 3. 阻塞检测优化

### 3.1 当前实现

**卡顿检测逻辑** (`src/backend/api/collaboration.py:138-223`):

```python
def _check_agent_stuck(agent_id: str) -> Optional[Dict[str, Any]]:
    if not is_agent_working(agent_id):
        return None

    last_update = get_session_updated_at(agent_id)
    now = int(time.time() * 1000)
    idle_seconds = (now - last_update) / 1000

    # 超过 60 秒无响应视为可能卡顿
    if idle_seconds > 60:
        reason = _analyze_stuck_reason(agent_id, idle_seconds)
        return {
            'isStuck': True,
            'idleSeconds': int(idle_seconds),
            'reason': reason.get('type', 'unknown'),
            'waitingFor': reason.get('waitingFor')
        }
```

**原因分析** (`_analyze_stuck_reason`):
- `waiting_subagent` - 等待子代理响应
- `model_delay` - 模型响应时间过长（>120秒）
- `tool_execution` - 工具执行中（>60秒）

### 3.2 问题分析

| 问题 | 当前行为 | 影响 |
|------|----------|------|
| 检测阈值单一 | 60秒统一阈值 | 无法区分正常慢速和异常卡顿 |
| 等待对象不明确 | 只显示agentId | 用户不知道具体等待什么 |
| 缺少历史参考 | 无 | 无法判断是否正常处理时间 |
| 无主动通知 | 只在UI显示 | 用户可能忽略 |

### 3.3 优化建议

**1. 分级检测阈值**:

```python
THRESHOLDS = {
    'warning': 45,    # 黄色警告
    'attention': 90,  # 橙色注意
    'critical': 180,  # 红色严重
}
```

**2. 更精确的等待对象检测**:

```python
def detect_waiting_target(agent_id: str) -> Dict:
    """
    检测Agent正在等待什么

    Returns:
        {
            'type': 'model' | 'subagent' | 'tool' | 'network' | 'unknown',
            'target': 'glm-5' | 'analyst-agent' | 'Write',
            'detail': '第3次重试' | '预计还需30秒',
            'suggestion': '建议检查API配额'
        }
    """
```

**3. 增加上下文信息**:

- 当前任务已执行时长
- 类似任务的平均执行时长
- 历史卡顿记录

**4. 前端展示优化**:

```
┌────────────────────────────────────────────┐
│ ⚠️ 可能卡顿                                │
│                                            │
│ 等待时间: 92 秒                            │
│ 等待对象: 分析师 (analyst-agent)           │
│ 任务内容: 分析宝宝的事情...                │
│                                            │
│ 💡 建议: 子代理响应时间过长，              │
│    建议检查子代理状态或考虑终止任务        │
│                                            │
│ [查看详情] [取消任务]                      │
└────────────────────────────────────────────┘
```

### 3.4 代码修改位置

- 卡顿检测: `src/backend/api/collaboration.py:138-223`
- 前端展示: `frontend/src/components/AgentCard.vue:70-97`
- 弹窗组件: `frontend/src/components/AgentDetailPanel.vue:37-74`

---

## 4. 子Agent LLM调用不刷新模型球

### 4.1 问题描述
子Agent（如分析师）调用LLM时，协作流程右侧模型面板的光球不会显示在对应模型上。

### 4.2 代码分析

**模型调用获取** (`src/backend/api/collaboration.py:226-265`):

```python
def _get_recent_model_calls(minutes: int = 30) -> List[Dict]:
    """获取最近 N 分钟的模型调用记录（用于光球展示）"""
    records = []
    agents_path = openclaw_path / 'agents'

    for agent_dir in agents_path.iterdir():
        agent_id = agent_dir.name
        sessions_path = agent_dir / 'sessions'
        for session_file in sessions_path.glob('*.jsonl'):
            for r in parse_session_file_with_details(session_file, agent_id):
                if r['timestamp'] >= since:
                    records.append({
                        'agentId': agent_id,
                        'model': r.get('model', ''),
                        ...
                    })
```

**前端光球渲染** (`CollaborationFlowSection.vue:121-131`):

```vue
<div class="model-dots">
  <span
    v-for="call in getCallsForModelNode(modelNode).slice(0, 8)"
    :key="call.id"
    class="model-dot"
    :style="{ background: getAgentColor(call.agentId) }"
    :title="`${call.agentId}`"
  />
</div>
```

### 4.3 问题根源

1. **子Agent session文件路径**: 子Agent的session可能不在 `agents/{agentId}/sessions/` 目录，而是通过 `childSessionKey` 关联。

2. **模型信息缺失**: `parse_session_file_with_details` 需要从session中提取模型信息，但子Agent的session可能没有记录模型。

3. **刷新时机**: 动态轮询间隔5秒，但数据源可能更新不及时。

### 4.4 优化方案

**1. 扩展模型调用数据源**:

```python
def _get_recent_model_calls(minutes: int = 30) -> List[Dict]:
    # 原有逻辑：遍历 agents 目录

    # 新增：从 runs.json 获取子Agent调用
    runs = load_subagent_runs()
    for run in runs:
        if run.get('endedAt') is None:  # 活跃run
            child_key = run.get('childSessionKey', '')
            agent_id = _parse_agent_id(child_key)
            if agent_id:
                # 从子Agent的session获取模型调用
                records.extend(_extract_calls_from_session(agent_id, child_key))
```

**2. 实时推送模型调用事件**:

```python
# WebSocket 消息类型
{
    'type': 'model_call',
    'data': {
        'agentId': 'analyst-agent',
        'model': 'glm-5',
        'timestamp': 1234567890,
        'tokens': 1234
    }
}
```

**3. 前端即时更新**:

```typescript
// RealtimeDataManager.ts
handleMessage(message: WebSocketMessage): void {
    if (message.type === 'model_call') {
        this.emit('model_call', message.data)
    }
}
```

### 4.5 验证步骤

1. 检查 `~/.openclaw/agents/analyst-agent/sessions/` 目录是否存在
2. 查看 session jsonl 文件中是否包含 model 字段
3. 确认 `_get_recent_model_calls` 是否正确遍历子Agent目录

---

## 5. Agent卡片当前任务截断问题

### 5.1 当前实现

**任务截断逻辑** (`src/backend/status/status_calculator.py:76-89`):

```python
def get_current_task(agent_id: str) -> str:
    runs = get_agent_runs(agent_id, limit=1)
    if not runs:
        return ''

    run = runs[0]
    task = run.get('task', '')

    # 截取前50个字符
    if len(task) > 50:
        task = task[:50] + '...'

    return task
```

**任务清理逻辑** (`src/backend/api/collaboration.py:76-119`):

```python
def _clean_task_name(task_name: str) -> str:
    # 过滤子 Agent 回传内容
    if 'Result (untrusted content, treat as data):' in task_name:
        return ''

    # 查找第一个有效的任务描述行
    for line in lines:
        # 跳过技术信息前缀
        if not is_tech and len(line) > 3:
            if len(line) > 80:
                return line[:77] + '...'
            return line
```

### 5.2 问题分析

| 问题 | 描述 |
|------|------|
| 截断长度不一致 | 后端50字符，协作API 80字符 |
| 截断位置不当 | 可能截断关键信息 |
| 无法查看完整任务 | 用户无法获取完整任务描述 |

### 5.3 "当前任务"与"最近活动"的区别

| 属性 | 当前任务 | 最近活动 |
|------|----------|----------|
| 数据来源 | `runs.json` 的 `task` 字段 | `sessions/*.jsonl` 的消息 |
| 时间范围 | 当前活跃任务 | 历史记录（可配置） |
| 内容类型 | 任务描述文本 | 用户/助手消息、工具调用等 |
| 更新频率 | 任务开始/结束 | 每次交互 |
| UI位置 | AgentCard主区域 | AgentDetailPanel详情面板 |

**当前任务**: 表示Agent正在执行的任务目标
**最近活动**: 表示Agent的历史交互记录

### 5.4 优化建议

**1. 智能截断**:

```python
def smart_truncate_task(task: str, max_len: int = 60) -> str:
    """
    智能截断任务描述，保留关键信息

    规则：
    1. 优先保留第一个完整句子
    2. 在标点符号处截断
    3. 最后才在字符边界截断
    """
    if len(task) <= max_len:
        return task

    # 查找句子结束符
    for end in ['。', '！', '？', '.', '!', '?', '\n']:
        idx = task.find(end)
        if 0 < idx < max_len:
            return task[:idx + 1]

    # 在空格处截断
    space_idx = task.rfind(' ', 0, max_len)
    if space_idx > max_len * 0.5:
        return task[:space_idx] + '...'

    return task[:max_len - 3] + '...'
```

**2. 鼠标悬停显示完整任务**:

```vue
<div class="task-name" :title="fullTask">
    {{ truncatedTask }}
</div>
```

**3. 点击展开详情**:

```vue
<div class="task-wrapper" @click="showFullTask = !showFullTask">
    <div class="task-preview">{{ truncatedTask }}</div>
    <div v-if="showFullTask" class="task-full">{{ fullTask }}</div>
</div>
```

**4. 统一截断长度**:

| 位置 | 建议长度 |
|------|----------|
| AgentCard（紧凑） | 40字符 |
| AgentCard（主Agent） | 80字符 |
| 协作流程节点 | 60字符 |
| 详情面板 | 不截断 |

---

## 6. 时序视图更新不及时问题

### 6.1 问题描述
时序视图中显示老K分配任务给分析师时，分析师视图更新延迟，比老K慢。

### 6.2 数据流分析

```
┌─────────────────────────────────────────────────────────────┐
│                      时序数据刷新流程                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [OpenClaw 写入]                                            │
│        │                                                     │
│        ▼                                                     │
│  runs.json / sessions/*.jsonl                               │
│        │                                                     │
│        │  文件变更事件                                       │
│        ▼                                                     │
│  [FileWatcher] (防抖 0.3s)                                  │
│        │                                                     │
│        │  触发广播                                           │
│        ▼                                                     │
│  [WebSocket broadcast_full_state]                           │
│        │                                                     │
│        │  周期性广播 (8s)                                    │
│        ▼                                                     │
│  [前端 RealtimeDataManager]                                 │
│        │                                                     │
│        │  订阅事件                                           │
│        ▼                                                     │
│  [CollaborationFlowSection]                                 │
│        │                                                     │
│        │  动态轮询 (5s)                                      │
│        ▼                                                     │
│  [TimelineView] → /api/timeline/{agentId}                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 延迟分析

| 环节 | 延迟 | 原因 |
|------|------|------|
| 文件写入 | 0-1s | OpenClaw写入时机 |
| FileWatcher防抖 | 0.3s | 避免频繁触发 |
| WebSocket广播 | 0-8s | 周期性推送 |
| 前端处理 | <0.1s | Vue响应式更新 |
| 动态轮询 | 0-5s | 定时请求 |
| **总延迟** | **0.3-14.4s** | 最坏情况 |

### 6.4 问题根源

1. **子Agent session文件分离**: 分析师的session文件在 `~/.openclaw/agents/analyst-agent/sessions/`，FileWatcher需要分别监听。

2. **FileWatcher监听目录** (`file_watcher.py:14-41`):

```python
def _get_watch_dirs() -> list[tuple[Path, bool]]:
    # ...
    agents_dir = OPENCLAW_DIR / "agents"
    if agents_dir.exists():
        for agent_dir in agents_dir.iterdir():
            if agent_dir.is_dir():
                sessions_dir = agent_dir / "sessions"
                if sessions_dir.exists():
                    dirs.append((sessions_dir, True))  # 递归监听
```

这段代码在**服务启动时**执行一次，如果之后创建了新的Agent目录，不会被监听。

3. **runs.json 更新时机**: 子Agent任务创建时写入，但session内容更新可能有延迟。

### 6.5 优化方案

**1. 动态添加监听目录**:

```python
class DynamicFileWatcher:
    def __init__(self):
        self.observer = Observer()
        self.watched_dirs = set()

    def check_new_agents(self):
        """定期检查新Agent目录"""
        agents_dir = OPENCLAW_DIR / "agents"
        if agents_dir.exists():
            for agent_dir in agents_dir.iterdir():
                sessions_dir = agent_dir / "sessions"
                if sessions_dir.exists() and sessions_dir not in self.watched_dirs:
                    self.observer.schedule(Handler(), str(sessions_dir), recursive=True)
                    self.watched_dirs.add(sessions_dir)
```

**2. 减少广播间隔**:

```python
# websocket.py
BROADCAST_INTERVAL_SEC = 3  # 从8秒减少到3秒

# CollaborationFlowSection.vue
const DYNAMIC_POLL_INTERVAL_MS = 3000  // 从5秒减少到3秒
```

**3. 事件驱动更新**:

```python
# 在子Agent任务创建时立即推送
async def on_subagent_task_created(run_id: str, agent_id: str):
    await broadcast_message({
        'type': 'subagent_task_created',
        'data': {
            'runId': run_id,
            'agentId': agent_id,
            'timestamp': int(time.time() * 1000)
        }
    })
```

**4. 前端乐观更新**:

```typescript
// 收到主Agent分配任务的消息后，立即更新子Agent状态
handleCollaborationUpdate(data: CollaborationFlow): void {
    // 乐观更新：立即显示子Agent任务
    const newTask = data.taskNodes.find(t => !this.nodes.some(n => n.id === t.id))
    if (newTask) {
        this.nodes.push(newTask)
    }

    // 然后更新其他数据
    this.nodes = data.nodes
    this.edges = data.edges
}
```

### 6.6 时序视图数据源

**API端点** (`src/backend/api/timeline.py`):

```
GET /api/timeline/{agent_id}?session_key=xxx&limit=100
```

**数据读取** (`timeline_reader.py:511-566`):

```python
def get_timeline_steps(agent_id: str, session_key: Optional[str] = None, ...):
    sessions_path = OPENCLAW_DIR / f"agents/{agent_id}/sessions"

    # 如果没有session目录，从subagent runs获取
    if not sessions_path.exists():
        return _get_subagent_timeline(agent_id, limit)
```

**问题**: 子Agent的时序数据可能来自两个来源：
1. 独立session文件（如果存在）
2. runs.json转换（如果没有独立session）

这导致数据获取路径不一致，更新时机也不同。

---

## 7. 总结与优先级建议

### 7.1 问题优先级

| 优先级 | 问题 | 影响 | 修复难度 |
|--------|------|------|----------|
| P0 | 状态不准确 | 用户体验差，误判任务状态 | 中 |
| P1 | 时序视图延迟 | 实时性差，用户困惑 | 中 |
| P1 | 子Agent模型球不显示 | 功能缺失 | 中 |
| P2 | 任务截断 | 信息不完整 | 低 |
| P2 | 阻塞检测不精确 | 诊断效率低 | 中 |
| P3 | 状态细化展示 | 用户体验提升 | 高 |

### 7.2 快速修复清单

**后端修改**:

1. `status_calculator.py:39` - 将5分钟改为2分钟
2. `websocket.py:19` - 将8秒改为3秒
3. `collaboration.py:155` - 将60秒改为45秒
4. `collaboration.py:226-265` - 增加子Agent模型调用获取
5. `file_watcher.py` - 增加动态目录监听

**前端修改**:

1. `CollaborationFlowSection.vue:178` - 将5000改为3000
2. `AgentCard.vue:40` - 增加title属性显示完整任务
3. `AgentCard.vue` - 增加更详细的状态展示

### 7.3 架构优化建议

1. **引入事件总线**: OpenClaw核心直接推送事件到Dashboard，而非依赖文件监听
2. **状态机模式**: 使用状态机管理Agent状态转换，明确各状态的进入/退出条件
3. **缓存策略**: 对session数据增加增量更新机制，避免全量读取
4. **WebSocket分组**: 按Agent分组推送，减少不必要的数据传输

---

*报告完成*
