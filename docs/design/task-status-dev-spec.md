# 任务状态模块 - 开发设计文档

> 版本：1.0  
> 创建日期：2026-03-07  
> 状态：待开发

---

## 一、需求概述

### 1.1 背景

任务状态模块是 OpenClaw Agent Dashboard 的核心模块之一，用于展示和管理多 Agent 系统中的任务执行记录。当前模块存在以下问题需要修复和增强：

1. **实时更新不生效**：WebSocket tasks 频道未正确实现
2. **进度百分比硬编码**：无法反映真实进度
3. **Agent 名称硬编码**：维护困难
4. **子任务功能未激活**：后端未填充数据
5. **缺少差异化功能**：时间线视图、快速筛选等

### 1.2 目标

- 修复现有问题，确保核心功能正常工作
- 增强差异化功能，与协作流程模块形成互补
- 提升用户体验，支持任务审计和失败分析场景

---

## 二、需求列表

### 2.1 P0 - 必须修复

| ID | 需求 | 描述 | 优先级 | 状态 |
|----|------|------|--------|------|
| TS-001 | 修复实时更新 | 实现 WebSocket tasks 频道，任务状态变化时实时推送 | P0 | 待开发 |
| TS-002 | 消除 Agent 名称硬编码 | 从 /api/agents 动态获取 Agent 名称映射 | P0 | 待开发 |
| TS-003 | 修复子任务数据 | 后端填充 subtasks 字段 | P0 | 待开发 |

### 2.2 P1 - 重要增强

| ID | 需求 | 描述 | 优先级 | 状态 |
|----|------|------|--------|------|
| TS-004 | 真实进度计算 | 基于 session 消息数计算真实进度 | P1 | 待开发 |
| TS-005 | 失败任务快速筛选 | 头部增加"仅失败"、"今日"快速筛选按钮 | P1 | 待开发 |
| TS-006 | 任务结果预览 | 列表项展示结果摘要（文件数、输出预览） | P1 | 待开发 |
| TS-007 | 任务时间线视图 | 详情弹窗展示执行时间线 | P1 | 待开发 |

### 2.3 P2 - 功能扩展

| ID | 需求 | 描述 | 优先级 | 状态 |
|----|------|------|--------|------|
| TS-008 | 任务对比功能 | 选择两个任务进行对比 | P2 | 待开发 |
| TS-009 | 任务导出 | 导出任务报告（Markdown/JSON） | P2 | 待开发 |

---

## 三、详细设计

### 3.1 TS-001：修复实时更新

#### 问题描述

当前前端订阅了 `tasks` 频道，但后端 WebSocket 未实现该频道的推送。

#### 后端修改

**文件**：`src/backend/api/websocket.py`

```python
# 新增 tasks 频道广播函数
async def broadcast_tasks_update():
    """广播任务状态更新"""
    from data.subagent_reader import load_subagent_runs
    from api.subagents import _run_to_task
    
    runs = load_subagent_runs()
    tasks = [_run_to_task(r) for r in runs[:50]]
    
    await broadcast_message({
        "type": "update",
        "channel": "tasks",
        "data": {"tasks": tasks},
        "timestamp": int(time.time() * 1000)
    })
```

**文件**：`src/backend/watchers/file_watcher.py`

```python
# 在 runs.json 变化时触发广播
def on_runs_change():
    """runs.json 变化时广播任务更新"""
    asyncio.create_task(broadcast_tasks_update())
```

#### 前端验证

**文件**：`frontend/src/components/tasks/TaskStatusSection.vue`

确认 `handleTasksUpdate` 函数正确处理数据：

```typescript
function handleTasksUpdate(data: unknown): void {
  const taskData = data as { tasks?: any[] }
  if (taskData.tasks) {
    tasks.value = taskData.tasks.map((t: any) => mapTaskFromApi(t))
  }
}
```

#### 测试用例

1. 启动 Dashboard，打开任务状态模块
2. 触发一个新任务（通过 openclaw 命令）
3. 验证任务列表自动更新，无需手动刷新

---

### 3.2 TS-002：消除 Agent 名称硬编码

#### 问题描述

前端组件中硬编码了 Agent 名称映射，当配置变化时需要修改代码。

#### 设计方案

**方案 A**：从 props 传入（推荐）

```typescript
// TaskStatusSection.vue
const props = defineProps<{
  agentNameMap?: Record<string, string>
}>()

function getAgentName(agentId: string): string {
  if (props.agentNameMap && props.agentNameMap[agentId]) {
    return props.agentNameMap[agentId]
  }
  return agentId
}
```

**方案 B**：组件内获取

```typescript
// TaskStatusSection.vue
const agentNameMap = ref<Record<string, string>>({})

async function loadAgentNames() {
  const res = await fetch('/api/agents')
  const agents = await res.json()
  for (const a of agents) {
    agentNameMap.value[a.id] = a.name
  }
}

onMounted(() => {
  loadAgentNames()
  // ...
})
```

#### 推荐方案

采用方案 A，由父组件 `App.vue` 统一获取并传入：

```vue
<!-- App.vue -->
<TaskStatusSection :agent-name-map="agentNameMap" />
```

#### 涉及文件

| 文件 | 修改内容 |
|------|----------|
| `frontend/src/App.vue` | 获取 agentNameMap 并传递给子组件 |
| `frontend/src/components/tasks/TaskStatusSection.vue` | 接收 props，使用动态映射 |
| `frontend/src/components/TokenAnalysisPanel.vue` | 同样需要修改（可后续处理） |
| `frontend/src/components/MechanismTrackingPanel.vue` | 同样需要修改（可后续处理） |

---

### 3.3 TS-003：修复子任务数据

#### 问题描述

后端 `_run_to_task()` 函数未填充 `subtasks` 字段，导致前端子任务展示功能不生效。

#### 后端修改

**文件**：`src/backend/api/subagents.py`

```python
def _run_to_task(run: Dict[str, Any]) -> Dict[str, Any]:
    """将 run 转为任务展示格式"""
    # ... 现有代码 ...
    
    result: Dict[str, Any] = {
        'id': run.get('runId', ''),
        'name': task_name,
        # ... 其他字段 ...
    }
    
    # 新增：填充 subtasks
    child_key = run.get('childSessionKey', '')
    if child_key:
        subtasks = _extract_subtasks_from_session(child_key)
        if subtasks:
            result['subtasks'] = subtasks
    
    return result


def _extract_subtasks_from_session(child_session_key: str) -> List[Dict[str, Any]]:
    """
    从 session 中提取子任务（嵌套的 sessions_spawn 调用）
    
    如果该任务又派发了子任务，则提取为 subtasks
    """
    if not child_session_key or ':' not in child_session_key:
        return []
    
    parts = child_session_key.split(':')
    if len(parts) < 2 or parts[0] != 'agent':
        return []
    
    agent_id = parts[1]
    openclaw_path = _openclaw_home()
    sessions_index = openclaw_path / "agents" / agent_id / "sessions" / "sessions.json"
    
    if not sessions_index.exists():
        return []
    
    try:
        with open(sessions_index, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        
        entry = index_data.get(child_session_key)
        if not entry:
            return []
        
        session_file = entry.get('sessionFile')
        if not session_file:
            return []
        
        session_path = Path(session_file)
        if not session_path.exists():
            return []
        
        subtasks = []
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get('type') != 'message':
                        continue
                    msg = data.get('message', {})
                    if msg.get('role') != 'assistant':
                        continue
                    content = msg.get('content', [])
                    for c in content:
                        if not isinstance(c, dict) or c.get('type') != 'toolCall':
                            continue
                        if c.get('name') == 'sessions_spawn':
                            args = c.get('arguments', {})
                            if isinstance(args, str):
                                args = json.loads(args)
                            sub_agent_id = args.get('agentId', '')
                            sub_task = args.get('task', '')
                            if sub_agent_id and sub_task:
                                subtasks.append({
                                    'id': f"sub-{len(subtasks)}",
                                    'name': sub_task[:50] + ('...' if len(sub_task) > 50 else ''),
                                    'task': sub_task,
                                    'status': 'pending',  # 无法获取真实状态
                                    'agentId': sub_agent_id,
                                    'agentName': _get_agent_name(sub_agent_id)
                                })
                except (json.JSONDecodeError, KeyError):
                    continue
        
        return subtasks
    except Exception as e:
        print(f"提取子任务失败: {e}")
        return []
```

---

### 3.4 TS-004：真实进度计算

#### 问题描述

当前进度硬编码为 50%（执行中）或 100%（已完成），不反映真实进度。

#### 设计方案

基于 session 消息数估算进度：

```python
# api/subagents.py

def _calculate_progress(child_session_key: str) -> int:
    """
    基于 session 消息数计算进度
    
    估算逻辑：
    - 统计 assistant 消息数
    - 每条消息贡献 10%，最高 90%
    - 完成后显示 100%
    """
    if not child_session_key or ':' not in child_session_key:
        return 0
    
    parts = child_session_key.split(':')
    if len(parts) < 2 or parts[0] != 'agent':
        return 0
    
    agent_id = parts[1]
    openclaw_path = _openclaw_home()
    sessions_index = openclaw_path / "agents" / agent_id / "sessions" / "sessions.json"
    
    if not sessions_index.exists():
        return 0
    
    try:
        with open(sessions_index, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        
        entry = index_data.get(child_session_key)
        if not entry:
            return 0
        
        session_file = entry.get('sessionFile')
        if not session_file:
            return 0
        
        session_path = Path(session_file)
        if not session_path.exists():
            return 0
        
        assistant_count = 0
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if data.get('type') == 'message':
                        msg = data.get('message', {})
                        if msg.get('role') == 'assistant':
                            assistant_count += 1
                except json.JSONDecodeError:
                    continue
        
        # 每条 assistant 消息贡献 10%，最高 90%
        progress = min(90, assistant_count * 10)
        return progress
    except Exception as e:
        print(f"计算进度失败: {e}")
        return 0


def _run_to_task(run: Dict[str, Any]) -> Dict[str, Any]:
    # ... 现有代码 ...
    
    # 修改进度计算
    if run.get('endedAt'):
        progress = 100
    else:
        child_key = run.get('childSessionKey', '')
        progress = _calculate_progress(child_key)
    
    # ...
```

---

### 3.5 TS-005：失败任务快速筛选

#### UI 设计

```
┌─────────────────────────────────────────────────────────────────┐
│ 任务状态                                                         │
│                                                                  │
│ 执行中: 2  已完成: 15  失败: 3  总计: 20                         │
│                                                                  │
│ [搜索框...]  [仅失败] [今日] [重置]                              │
├─────────────────────────────────────────────────────────────────┤
│ 任务列表...                                                      │
└─────────────────────────────────────────────────────────────────┘
```

#### 前端实现

**文件**：`frontend/src/components/tasks/TaskStatusSection.vue`

```typescript
// 新增快速筛选状态
const quickFilters = ref({
  failedOnly: false,
  todayOnly: false
})

// 修改 filteredTasks
const filteredTasks = computed(() => {
  let result = tasks.value
  
  // 状态过滤（原有逻辑）
  if (activeFilters.value.length > 0) {
    result = result.filter(t => activeFilters.value.includes(t.status))
  }
  
  // 快速筛选：仅失败
  if (quickFilters.value.failedOnly) {
    result = result.filter(t => t.status === 'failed')
  }
  
  // 快速筛选：今日
  if (quickFilters.value.todayOnly) {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const todayStart = today.getTime()
    result = result.filter(t => (t.startTime || 0) >= todayStart)
  }
  
  // 搜索过滤（原有逻辑）
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(t => 
      t.name.toLowerCase().includes(query) ||
      t.agentName?.toLowerCase().includes(query)
    )
  }
  
  return result
})

// 切换快速筛选
function toggleQuickFilter(filter: 'failedOnly' | 'todayOnly'): void {
  quickFilters.value[filter] = !quickFilters.value[filter]
}

// 重置筛选
function resetFilters(): void {
  activeFilters.value = []
  searchQuery.value = ''
  quickFilters.value = { failedOnly: false, todayOnly: false }
}
```

#### 模板修改

```vue
<div class="filters-row">
  <div class="search-box">
    <input v-model="searchQuery" type="text" placeholder="搜索任务..." class="search-input" />
  </div>
  <div class="filter-buttons">
    <!-- 原有状态过滤按钮 -->
    <button
      v-for="status in statusFilters"
      :key="status.value"
      :class="['filter-btn', { active: activeFilters.includes(status.value) }]"
      @click="toggleFilter(status.value)"
    >
      {{ status.label }} ({{ getStatusCount(status.value) }})
    </button>
  </div>
  <!-- 新增快速筛选 -->
  <div class="quick-filters">
    <button
      :class="['quick-filter-btn', { active: quickFilters.failedOnly }]"
      @click="toggleQuickFilter('failedOnly')"
    >
      仅失败
    </button>
    <button
      :class="['quick-filter-btn', { active: quickFilters.todayOnly }]"
      @click="toggleQuickFilter('todayOnly')"
    >
      今日
    </button>
    <button class="reset-btn" @click="resetFilters">重置</button>
  </div>
</div>
```

#### 样式

```css
.quick-filters {
  display: flex;
  gap: 0.5rem;
  margin-left: auto;
}

.quick-filter-btn {
  padding: 0.4rem 0.8rem;
  border: 1px solid #fecaca;
  border-radius: 6px;
  background: #fef2f2;
  color: #991b1b;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.2s;
}

.quick-filter-btn.active {
  background: #ef4444;
  color: white;
  border-color: #ef4444;
}

.reset-btn {
  padding: 0.4rem 0.8rem;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: white;
  color: #6b7280;
  font-size: 0.8rem;
  cursor: pointer;
}
```

---

### 3.6 TS-006：任务结果预览

#### UI 设计

```
┌─────────────────────────────────────────────────────────────────┐
│ ✅ 重构用户认证模块                                              │
│    devops-agent · 2分15秒 · 09:25                               │
│    📁 新增 2 文件，修改 3 文件                                   │
│    详情 ›                                                        │
└─────────────────────────────────────────────────────────────────┘
```

#### 后端修改

**文件**：`src/backend/api/subagents.py`

```python
def _run_to_task(run: Dict[str, Any]) -> Dict[str, Any]:
    # ... 现有代码 ...
    
    result: Dict[str, Any] = {
        # ... 其他字段 ...
    }
    
    # 新增：生成结果摘要
    if status == 'completed':
        child_key = run.get('childSessionKey', '')
        if child_key:
            files = get_agent_files_for_run(child_key)
            if files:
                # 统计文件操作类型
                result['summary'] = f"生成 {len(files)} 个文件"
                result['fileCount'] = len(files)
    
    return result
```

#### 前端修改

```vue
<!-- TaskStatusSection.vue 模板 -->
<div class="task-item" @click="selectedTask = task">
  <span class="task-status-icon" :class="task.status">
    {{ getStatusIcon(task.status) }}
  </span>
  <div class="task-main">
    <div class="task-name-short">{{ getShortTaskName(task) }}</div>
    <!-- 新增：结果预览 -->
    <div v-if="task.summary" class="task-summary">
      📁 {{ task.summary }}
    </div>
  </div>
  <span class="task-agent" v-if="task.agentName">{{ task.agentName }}</span>
  <span class="task-time" v-if="task.startTime">{{ formatDuration(task) }}</span>
  <span class="task-detail-hint">详情 ›</span>
</div>
```

```css
.task-summary {
  font-size: 0.75rem;
  color: #6b7280;
  margin-top: 0.25rem;
}
```

---

### 3.7 TS-007：任务时间线视图

#### UI 设计

在任务详情弹窗底部新增时间线区域：

```
┌─────────────────────────────────────────────────────────────────┐
│ 任务详情                                               [×]      │
├─────────────────────────────────────────────────────────────────┤
│ 任务：重构用户认证模块                                           │
│ 状态：✅ 已完成                                                  │
│ 执行者：devops-agent                                             │
│ 耗时：2分15秒                                                    │
│                                                                  │
│ ┌─ 执行时间线 ─────────────────────────────────────────────────┐│
│ │ 09:23:15  ──● 任务开始                                       ││
│ │ 09:23:18    ● 分析代码结构                                    ││
│ │ 09:24:02    ● 生成重构方案                                    ││
│ │ 09:24:45    ● 执行代码修改                                    ││
│ │ 09:25:30  ──● 任务完成                                       ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│ 生成的文件：                                                     │
│ - src/auth/login.py                                             │
│ - src/auth/session.py                                           │
└─────────────────────────────────────────────────────────────────┘
```

#### 后端实现

**文件**：`src/backend/api/subagents.py`

新增 API 端点：

```python
@router.get("/tasks/{run_id}/timeline")
async def get_task_timeline(run_id: str):
    """
    获取任务执行时间线
    
    返回任务执行过程中的关键节点
    """
    from data.subagent_reader import load_subagent_runs, _openclaw_home
    
    runs = load_subagent_runs()
    run = next((r for r in runs if r.get('runId') == run_id), None)
    if not run:
        return {'timeline': [], 'error': 'Task not found'}
    
    child_key = run.get('childSessionKey', '')
    if not child_key:
        return {'timeline': [], 'error': 'No session key'}
    
    parts = child_key.split(':')
    if len(parts) < 2 or parts[0] != 'agent':
        return {'timeline': [], 'error': 'Invalid session key'}
    
    agent_id = parts[1]
    openclaw_path = _openclaw_home()
    sessions_index = openclaw_path / "agents" / agent_id / "sessions" / "sessions.json"
    
    if not sessions_index.exists():
        return {'timeline': [], 'error': 'Session index not found'}
    
    try:
        with open(sessions_index, 'r', encoding='utf-8') as f:
            index_data = json.load(f)
        
        entry = index_data.get(child_key)
        if not entry:
            return {'timeline': [], 'error': 'Session not found'}
        
        session_file = entry.get('sessionFile')
        if not session_file:
            return {'timeline': [], 'error': 'Session file not found'}
        
        session_path = Path(session_file)
        if not session_path.exists():
            return {'timeline': [], 'error': 'Session file not exists'}
        
        timeline = []
        with open(session_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                try:
                    data = json.loads(line)
                    if data.get('type') != 'message':
                        continue
                    
                    msg = data.get('message', {})
                    timestamp = data.get('timestamp', '')
                    
                    # 解析时间戳
                    try:
                        ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        ts_str = ts.strftime('%H:%M:%S')
                        ts_ms = int(ts.timestamp() * 1000)
                    except:
                        continue
                    
                    role = msg.get('role', '')
                    
                    if role == 'user':
                        # 任务开始
                        if i == 0:
                            timeline.append({
                                'time': ts_str,
                                'timestamp': ts_ms,
                                'type': 'start',
                                'description': '任务开始'
                            })
                    
                    elif role == 'assistant':
                        # 提取操作摘要
                        content = msg.get('content', [])
                        action = None
                        
                        for c in content:
                            if isinstance(c, dict):
                                if c.get('type') == 'text':
                                    text = c.get('text', '')[:50]
                                    if text.strip():
                                        action = text.strip().split('\n')[0][:30]
                                elif c.get('type') == 'toolCall':
                                    tool_name = c.get('name', '')
                                    action = f"调用工具: {tool_name}"
                                    break
                        
                        if action:
                            timeline.append({
                                'time': ts_str,
                                'timestamp': ts_ms,
                                'type': 'action',
                                'description': action
                            })
                    
                    elif role == 'toolResult':
                        # 工具执行结果
                        tool_name = msg.get('toolName', 'unknown')
                        timeline.append({
                            'time': ts_str,
                            'timestamp': ts_ms,
                            'type': 'tool_result',
                            'description': f"{tool_name} 完成"
                        })
                
                except (json.JSONDecodeError, KeyError):
                    continue
        
        # 添加结束节点
        if run.get('endedAt'):
            end_ts = run.get('endedAt')
            dt = datetime.fromtimestamp(end_ts / 1000)
            timeline.append({
                'time': dt.strftime('%H:%M:%S'),
                'timestamp': end_ts,
                'type': 'end',
                'description': '任务完成' if run.get('outcome') == 'ok' else '任务失败'
            })
        
        return {'timeline': timeline}
    
    except Exception as e:
        return {'timeline': [], 'error': str(e)}
```

#### 前端实现

```typescript
// TaskStatusSection.vue

interface TimelineItem {
  time: string
  timestamp: number
  type: 'start' | 'action' | 'tool_result' | 'end'
  description: string
}

const taskTimeline = ref<TimelineItem[]>([])
const timelineLoading = ref(false)

async function loadTaskTimeline(taskId: string): Promise<void> {
  timelineLoading.value = true
  try {
    const res = await fetch(`/api/tasks/${taskId}/timeline`)
    const data = await res.json()
    taskTimeline.value = data.timeline || []
  } catch (e) {
    taskTimeline.value = []
  } finally {
    timelineLoading.value = false
  }
}

// 当选中任务时加载时间线
watch(selectedTask, (task) => {
  if (task) {
    loadTaskTimeline(task.id)
  } else {
    taskTimeline.value = []
  }
})
```

```vue
<!-- 详情弹窗中新增时间线区域 -->
<div v-if="selectedTask" class="task-detail-modal">
  <!-- ... 现有内容 ... -->
  
  <!-- 时间线 -->
  <div v-if="taskTimeline.length > 0" class="detail-row">
    <span class="detail-label">执行时间线</span>
    <div class="timeline-container">
      <div v-if="timelineLoading" class="timeline-loading">加载中...</div>
      <div v-else class="timeline">
        <div
          v-for="(item, i) in taskTimeline"
          :key="i"
          :class="['timeline-item', item.type]"
        >
          <span class="timeline-time">{{ item.time }}</span>
          <span class="timeline-dot"></span>
          <span class="timeline-desc">{{ item.description }}</span>
        </div>
      </div>
    </div>
  </div>
</div>
```

```css
.timeline-container {
  margin-top: 0.5rem;
}

.timeline {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding-left: 0.5rem;
  border-left: 2px solid #e5e7eb;
  margin-left: 0.5rem;
}

.timeline-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.85rem;
}

.timeline-time {
  color: #6b7280;
  font-family: ui-monospace, monospace;
  font-size: 0.8rem;
  min-width: 60px;
}

.timeline-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
}

.timeline-item.start .timeline-dot,
.timeline-item.end .timeline-dot {
  background: #4a9eff;
}

.timeline-item.end .timeline-dot {
  background: #22c55e;
}

.timeline-desc {
  color: #334155;
}
```

---

## 四、开发计划

### 4.1 阶段一：P0 修复（预计 2 天）

| 任务 | 预计时间 | 负责人 |
|------|----------|--------|
| TS-001 实时更新 | 4h | - |
| TS-002 Agent 名称 | 2h | - |
| TS-003 子任务数据 | 2h | - |

### 4.2 阶段二：P1 增强（预计 3 天）

| 任务 | 预计时间 | 负责人 |
|------|----------|--------|
| TS-004 真实进度 | 3h | - |
| TS-005 快速筛选 | 2h | - |
| TS-006 结果预览 | 2h | - |
| TS-007 时间线 | 4h | - |

### 4.3 阶段三：P2 扩展（预计 2 天）

| 任务 | 预计时间 | 负责人 |
|------|----------|--------|
| TS-008 任务对比 | 4h | - |
| TS-009 任务导出 | 3h | - |

---

## 五、测试清单

### 5.1 功能测试

| ID | 测试项 | 预期结果 | 状态 |
|----|--------|----------|------|
| T-001 | 实时更新 | 新任务自动出现，状态变化自动更新 | 待测试 |
| T-002 | Agent 名称 | 显示配置中的名称，非硬编码 | 待测试 |
| T-003 | 子任务展示 | 有嵌套任务时正确展示 | 待测试 |
| T-004 | 进度显示 | 执行中任务显示 0-90%，完成显示 100% | 待测试 |
| T-005 | 快速筛选 | "仅失败"只显示失败任务，"今日"只显示今天的 | 待测试 |
| T-006 | 结果预览 | 列表显示文件数量摘要 | 待测试 |
| T-007 | 时间线 | 详情弹窗显示执行时间线 | 待测试 |

### 5.2 边界测试

| ID | 测试项 | 预期结果 |
|----|--------|----------|
| B-001 | 无任务数据 | 显示空状态提示 |
| B-002 | 任务无 session 文件 | 不崩溃，显示基本信息 |
| B-003 | 超长任务名称 | 正确截断显示 |
| B-004 | 大量任务（100+） | 列表滚动流畅 |

### 5.3 集成测试

| ID | 测试项 | 预期结果 |
|----|--------|----------|
| I-001 | 与协作流程联动 | 点击任务跳转到协作流程 |
| I-002 | WebSocket 断开重连 | 任务列表继续更新 |
| I-003 | 页面刷新 | 数据重新加载 |

---

## 六、发布检查

### 6.1 代码检查

- [ ] 无 console.log 调试代码
- [ ] 无硬编码的 Agent 名称
- [ ] 无硬编码的进度值
- [ ] 类型定义完整

### 6.2 文档更新

- [ ] 更新 README.md 功能列表
- [ ] 更新 API 文档

### 6.3 测试验证

- [ ] 所有功能测试通过
- [ ] 边界测试通过
- [ ] 集成测试通过
