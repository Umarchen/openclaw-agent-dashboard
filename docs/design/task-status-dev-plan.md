# 任务状态模块开发计划

> 文档版本：1.0  
> 创建日期：2026-03-07  
> 基于：task-status-module-analysis.md

---

## 一、开发任务概览

| ID | 任务 | 优先级 | 预计工时 | 依赖 | 状态 |
|----|------|--------|----------|------|------|
| TS-001 | 修复实时更新 | P0 | 2h | - | ✅ 已验证可用 |
| TS-002 | 消除 Agent 名称硬编码 | P0 | 1h | - | ✅ 已使用 API 返回值 |
| TS-003 | 修复子任务数据 | P0 | 2h | TS-002 | ✅ 已完成 |
| TS-004 | 真实进度计算 | P1 | 1.5h | - | ✅ 已完成 |
| TS-005 | 失败任务快速筛选 | P1 | 1h | - | ✅ 已完成 |
| TS-006 | 任务结果预览 | P1 | 0.5h | - | ✅ 已实现 |
| TS-007 | 任务时间线视图 | P2 | 3h | - | ✅ 已完成 |

> **备注**: 时间线功能需要 session 文件存在，历史任务的 session 可能已被清理。

---

## 二、P0 任务详细设计

### 2.1 TS-001：修复实时更新

#### 问题描述

任务状态模块订阅了 WebSocket `tasks` 频道，但后端 `file_watcher.py` 未在 runs.json 变化时广播更新。

#### 后端修改

**文件**：`src/backend/watchers/file_watcher.py`

新增广播函数：

```python
async def broadcast_tasks_update():
    """广播任务列表更新"""
    from api.subagents import get_tasks
    from api.websocket import broadcast
    
    tasks_data = await get_tasks()
    await broadcast('tasks', tasks_data)
```

修改文件监听，在 runs.json 变化时触发：

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

### 2.2 TS-002：消除 Agent 名称硬编码

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

采用方案 B，组件内获取，保持组件独立性：

```typescript
// TaskStatusSection.vue
const agentNameMap = ref<Record<string, string>>({})

async function loadAgentNames(): Promise<void> {
  try {
    const res = await fetch('/api/agents')
    if (res.ok) {
      const agents = await res.json()
      for (const a of agents) {
        agentNameMap.value[a.id] = a.name
      }
    }
  } catch (e) {
    // 静默失败，使用 fallback
  }
}

function getAgentName(agentId: string): string {
  return agentNameMap.value[agentId] || agentId
}

onMounted(() => {
  loadAgentNames()
  fetchData()
  unsubscribe = subscribe('tasks', handleTasksUpdate)
})
```

#### 涉及文件

| 文件 | 修改内容 |
|------|----------|
| `frontend/src/components/tasks/TaskStatusSection.vue` | 移除硬编码，添加动态获取 |

---

### 2.3 TS-003：修复子任务数据

#### 问题描述

后端 `_run_to_task()` 函数未填充 `subtasks` 字段，导致前端子任务展示功能不生效。

#### 后端修改

**文件**：`src/backend/api/subagents.py`

新增子任务提取函数：

```python
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
                                try:
                                    args = json.loads(args)
                                except json.JSONDecodeError:
                                    continue
                            sub_agent_id = args.get('agentId', '')
                            sub_task = args.get('task', '')
                            if sub_agent_id and sub_task:
                                # 截断任务名
                                task_name = sub_task[:50] + ('...' if len(sub_task) > 50 else '')
                                subtasks.append({
                                    'id': f"sub-{len(subtasks)}",
                                    'name': task_name,
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

修改 `_run_to_task` 函数：

```python
def _run_to_task(run: Dict[str, Any]) -> Dict[str, Any]:
    """将 run 转为任务展示格式"""
    # ... 现有代码 ...
    
    result: Dict[str, Any] = {
        'id': run.get('runId', ''),
        'name': task_name,
        'task': task_display,
        'status': status,
        'progress': progress,
        'startTime': run.get('startedAt'),
        'endTime': run.get('endedAt'),
        'agentId': agent_id,
        'agentName': _get_agent_name(agent_id),
        'agentWorkspace': _get_agent_workspace(agent_id),
        'error': error_msg,
        'childSessionKey': run.get('childSessionKey')
    }
    
    # 新增：填充 subtasks
    child_key = run.get('childSessionKey', '')
    if child_key:
        subtasks = _extract_subtasks_from_session(child_key)
        if subtasks:
            result['subtasks'] = subtasks
    
    # ... 原有的 output 和 generatedFiles 逻辑 ...
    
    return result
```

---

## 三、P1 任务详细设计

### 3.1 TS-004：真实进度计算

#### 后端修改

**文件**：`src/backend/api/subagents.py`

```python
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
```

修改 `_run_to_task`：

```python
def _run_to_task(run: Dict[str, Any]) -> Dict[str, Any]:
    # ... 
    # 修改进度计算
    if run.get('endedAt'):
        progress = 100
    else:
        child_key = run.get('childSessionKey', '')
        progress = _calculate_progress(child_key)
    # ...
```

---

### 3.2 TS-005：失败任务快速筛选

#### UI 设计

在筛选行增加快速筛选按钮：[仅失败] [今日] [重置]

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

---

### 3.3 TS-006：任务结果预览

#### 后端修改

在 `_run_to_task` 中添加摘要：

```python
# 新增：生成结果摘要
if status == 'completed':
    child_key = run.get('childSessionKey', '')
    if child_key:
        files = get_agent_files_for_run(child_key)
        if files:
            result['summary'] = f"生成 {len(files)} 个文件"
            result['fileCount'] = len(files)
```

#### 前端修改

在任务列表项中显示摘要：

```vue
<div class="task-main">
  <div class="task-name-short">{{ getShortTaskName(task) }}</div>
  <div v-if="task.summary" class="task-summary">
    📁 {{ task.summary }}
  </div>
</div>
```

---

### 3.4 TS-007：任务时间线视图

#### 后端新增 API

**文件**：`src/backend/api/subagents.py`

```python
@router.get("/tasks/{run_id}/timeline")
async def get_task_timeline(run_id: str):
    """获取任务执行时间线"""
    # 详细实现见完整文档...
```

#### 前端实现

在详情弹窗中展示时间线：

```vue
<div v-if="taskTimeline.length > 0" class="detail-row">
  <span class="detail-label">执行时间线</span>
  <div class="timeline-container">
    <div class="timeline">
      <div v-for="(item, i) in taskTimeline" :key="i" class="timeline-item">
        <span class="timeline-time">{{ item.time }}</span>
        <span class="timeline-dot"></span>
        <span class="timeline-desc">{{ item.description }}</span>
      </div>
    </div>
  </div>
</div>
```

---

## 四、测试清单

### 4.1 功能测试

| ID | 测试项 | 预期结果 |
|----|--------|----------|
| T-001 | 实时更新 | 新任务自动出现，状态变化自动更新 |
| T-002 | Agent 名称 | 显示配置中的名称，非硬编码值 |
| T-003 | 子任务展示 | 有嵌套任务时显示子任务列表 |
| T-004 | 进度显示 | 执行中任务进度随消息数增长 |
| T-005 | 快速筛选 | 仅失败/今日按钮正确过滤 |
| T-006 | 结果预览 | 已完成任务显示文件摘要 |
| T-007 | 时间线 | 详情弹窗显示执行时间线 |

### 4.2 边界测试

| ID | 测试项 | 预期结果 |
|----|--------|----------|
| B-001 | 无任务数据 | 显示空状态 |
| B-002 | Agent 配置缺失 | 显示 agentId |
| B-003 | Session 文件不存在 | 不崩溃，返回空数据 |
| B-004 | WebSocket 断开 | 显示断开状态，手动刷新可用 |

---

## 五、部署检查清单

- [ ] 后端代码已更新
- [ ] 前端代码已更新
- [ ] WebSocket 频道已验证
- [ ] 功能测试通过
- [ ] 边界测试通过
