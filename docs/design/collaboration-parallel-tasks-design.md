# 协作流程多任务并行展示 - 详细设计文档

> 文档版本：1.0  
> 创建日期：2026-03-07  
> 目标场景：场景2 - 多需求并行开发  
> 关联分析：`openclaw-multi-agent-usage-scenarios.md`

---

## 一、场景描述

### 1.1 用户故事

> 作为 OpenClaw 用户，当我同时推进多个功能需求时，我希望在 Dashboard 中能同时看到所有并行任务的状态，而不是只能看到一个任务的进度。

### 1.2 当前问题

```
用户操作：向 PM 下发 3 个并行需求
  - Feature-A: 用户认证模块
  - Feature-B: 数据导出功能  
  - Feature-C: 性能优化

实际显示：
┌─────────────────────────────────┐
│  PM: 工作中                      │
│  当前任务: Feature-A PRD编写...  │  ← 只显示第一个
│                                  │
│  analyst-agent: 工作中           │  ← 看不到 B/C
│  architect-agent: 空闲           │
│  devops-agent: 空闲              │
└─────────────────────────────────┘

期望显示：
┌─────────────────────────────────┐
│  PM: 工作中                      │
│  📋 并行任务 (3 active)          │
│  ├─ Feature-A → analyst-agent   │
│  ├─ Feature-B → architect-agent │
│  └─ Feature-C → devops-agent    │
│                                  │
│  analyst-agent: 工作中 (1任务)   │
│  architect-agent: 工作中 (1任务) │
│  devops-agent: 工作中 (1任务)    │
└─────────────────────────────────┘
```

### 1.3 问题根因分析

| 问题 | 代码位置 | 原因 |
|------|----------|------|
| 主 Agent 只显示一个任务 | `collaboration.py:560-578` | `main_agent_task_created` 标志限制 |
| 子 Agent 只显示一个任务 | `collaboration.py:457-463` | `currentTask` 只取第一个匹配 |
| 任务数量限制 | `collaboration.py:522` | `active_runs[:10]` 截断 |
| 前端无多任务组件 | `AgentCard.vue` | 只有 `currentTask: string` |

---

## 二、设计方案

### 2.1 设计原则

1. **最小侵入**：复用现有 nodes/edges 模型，新增可选字段
2. **向后兼容**：旧前端忽略新字段仍可工作
3. **渐进增强**：先支持显示，后续再做交互
4. **性能优先**：避免大改动影响 API 响应时间

### 2.2 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                            │
├─────────────────────────────────────────────────────────────┤
│  CollaborationFlowSection.vue                               │
│  ├─ AgentCard.vue (增强: 多任务列表)                         │
│  └─ 多任务连线渲染                                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         Backend                             │
├─────────────────────────────────────────────────────────────┤
│  /api/collaboration                                         │
│  ├─ 新增: agentActiveTasks: Dict<agentId, Task[]>           │
│  └─ 移除: main_agent_task_created 限制                      │
│                                                             │
│  /api/collaboration/dynamic                                 │
│  └─ 同步: agentActiveTasks 字段                             │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        Data Source                          │
├─────────────────────────────────────────────────────────────┤
│  ~/.openclaw/subagents/runs.json                            │
│  └─ active_runs: 所有未结束的任务                            │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、后端设计

### 3.1 数据模型扩展

#### 3.1.1 新增 ActiveTask 模型

```python
# src/backend/api/collaboration.py

class ActiveTask(BaseModel):
    """单个活跃任务"""
    id: str                      # task-{runId}
    name: str                    # 任务名称（清理后）
    status: str = "working"      # working | retrying | failed
    timestamp: Optional[int]     # 开始时间
    childAgentId: Optional[str]  # 主 Agent 任务时，指向被派发的子 Agent
    featureId: Optional[str]     # FEATURE_ID（如果有）
```

#### 3.1.2 扩展 CollaborationFlow

```python
class CollaborationFlow(BaseModel):
    # 现有字段...
    nodes: List[CollaborationNode]
    edges: List[CollaborationEdge]
    activePath: List[str]
    lastUpdate: int
    mainAgentId: Optional[str] = None
    agentModels: Optional[Dict[str, Dict[str, Any]]] = None
    models: Optional[List[str]] = None
    recentCalls: Optional[List[ModelCall]] = None
    hierarchy: Optional[Dict[str, List[str]]] = None
    depths: Optional[Dict[str, int]] = None
    
    # 新增字段
    agentActiveTasks: Optional[Dict[str, List[ActiveTask]]] = None
    # agentId -> [ActiveTask, ...]
```

#### 3.1.3 扩展 CollaborationDynamic

```python
class CollaborationDynamic(BaseModel):
    # 现有字段...
    activePath: List[str]
    recentCalls: List[ModelCall]
    agentStatuses: Dict[str, str]
    agentDynamicStatuses: Optional[Dict[str, AgentDisplayStatus]] = None
    taskNodes: List[CollaborationNode]
    taskEdges: List[CollaborationEdge]
    mainAgentId: str
    lastUpdate: int
    
    # 新增字段
    agentActiveTasks: Optional[Dict[str, List[ActiveTask]]] = None
```

### 3.2 核心逻辑改动

#### 3.2.1 构建 agentActiveTasks

```python
def _build_agent_active_tasks(
    active_runs: List[Dict[str, Any]], 
    main_agent_id: str
) -> Dict[str, List[Dict[str, Any]]]:
    """
    构建每个 Agent 的活跃任务列表
    
    Args:
        active_runs: 从 runs.json 读取的活跃任务
        main_agent_id: 主 Agent ID
        
    Returns:
        {
            "main": [task1, task2, ...],           # PM 派发的任务
            "analyst-agent": [task3, ...],          # 分析师执行的任务
            "architect-agent": [task4, ...],        # 架构师执行的任务
        }
    """
    agent_active_tasks: Dict[str, List[Dict[str, Any]]] = {}
    
    for run in active_runs:
        child_key = run.get('childSessionKey', '')
        requester_key = run.get('requesterSessionKey', '')
        
        # 解析执行者 Agent
        child_agent_id = _parse_agent_id(child_key)
        # 解析派发者 Agent  
        requester_agent_id = _parse_agent_id(requester_key)
        
        if not child_agent_id:
            continue
            
        # 清理任务名称
        task_name = _clean_task_name(run.get('task', ''))
        if not task_name:
            task_name = '未命名任务'
        
        run_id = run.get('runId', child_agent_id)
        
        # 构建任务对象
        task_item = {
            'id': f"task-{run_id}",
            'name': task_name,
            'status': 'working',
            'timestamp': run.get('startedAt'),
            'childAgentId': child_agent_id if requester_agent_id == main_agent_id else None,
            'featureId': _extract_feature_id(task_name)
        }
        
        # 1. 添加到派发者（如果是主 Agent 派发的）
        if requester_agent_id == main_agent_id:
            if main_agent_id not in agent_active_tasks:
                agent_active_tasks[main_agent_id] = []
            agent_active_tasks[main_agent_id].append(task_item)
        
        # 2. 添加到执行者
        if child_agent_id not in agent_active_tasks:
            agent_active_tasks[child_agent_id] = []
        # 子 Agent 的任务不需要 childAgentId 字段
        child_task = {k: v for k, v in task_item.items() if k != 'childAgentId'}
        agent_active_tasks[child_agent_id].append(child_task)
    
    return agent_active_tasks


def _extract_feature_id(task_name: str) -> Optional[str]:
    """从任务名称中提取 FEATURE_ID"""
    import re
    # 匹配 [FEATURE_ID] xxx 或类似格式
    match = re.search(r'\[FEATURE_ID\]\s*(\S+)', task_name)
    if match:
        return match.group(1)
    return None
```

#### 3.2.2 移除 main_agent_task_created 限制

**位置**：`src/backend/api/collaboration.py` 第 520-578 行

```python
# === 原代码 ===
main_agent_task_created = False
for run in active_runs[:10]:
    ...
    if requester_id == main_agent_id and not main_agent_task_created:
        # 只创建第一个主 Agent 任务节点
        main_task_id = f"task-main-{run.get('runId', 'current')}"
        ...
        main_agent_task_created = True

# === 新代码 ===
for run in active_runs[:20]:  # 放宽限制
    ...
    if requester_id == main_agent_id:
        # 为每个主 Agent 派发的任务都创建节点
        main_task_id = f"task-main-{run.get('runId', 'current')}"
        main_task_node = CollaborationNode(
            id=main_task_id,
            type="task",
            name=task_name,
            status="working",
            timestamp=run.get('startedAt')
        )
        nodes.append(main_task_node)
        edges.append(CollaborationEdge(
            id=f"edge-{main_agent_id}-{main_task_id}",
            source=main_agent_id,
            target=main_task_id,
            type="calls",
            label="执行"
        ))
        # 不再设置 main_agent_task_created 标志
```

#### 3.2.3 子 Agent 多任务显示策略

当子 Agent 有多个任务时，`currentTask` 字段的显示策略：

```python
def _get_display_task(tasks: List[Dict[str, Any]]) -> str:
    """
    获取用于显示的任务摘要
    
    策略：
    - 1 个任务：显示任务名称
    - 2-3 个任务：显示 "N 个任务进行中"
    - >3 个任务：显示 "N 个任务进行中（点击查看）"
    """
    count = len(tasks)
    if count == 0:
        return ''
    elif count == 1:
        # 截断过长任务名
        name = tasks[0].get('name', '')
        return name[:50] + '...' if len(name) > 50 else name
    else:
        return f"{count} 个任务进行中"
```

### 3.3 API 响应示例

#### GET /api/collaboration

```json
{
  "nodes": [...],
  "edges": [...],
  "activePath": [...],
  "mainAgentId": "main",
  "agentActiveTasks": {
    "main": [
      {
        "id": "task-run-001",
        "name": "用户认证模块 PRD 编写",
        "status": "working",
        "timestamp": 1709800000000,
        "childAgentId": "analyst-agent",
        "featureId": "user-auth"
      },
      {
        "id": "task-run-002", 
        "name": "数据导出功能设计",
        "status": "working",
        "timestamp": 1709800100000,
        "childAgentId": "architect-agent",
        "featureId": "data-export"
      },
      {
        "id": "task-run-003",
        "name": "性能优化实现",
        "status": "working", 
        "timestamp": 1709800200000,
        "childAgentId": "devops-agent",
        "featureId": "perf-optimization"
      }
    ],
    "analyst-agent": [
      {
        "id": "task-run-001",
        "name": "用户认证模块 PRD 编写",
        "status": "working",
        "timestamp": 1709800000000,
        "featureId": "user-auth"
      }
    ],
    "architect-agent": [
      {
        "id": "task-run-002",
        "name": "数据导出功能设计", 
        "status": "working",
        "timestamp": 1709800100000,
        "featureId": "data-export"
      }
    ],
    "devops-agent": [
      {
        "id": "task-run-003",
        "name": "性能优化实现",
        "status": "working",
        "timestamp": 1709800200000,
        "featureId": "perf-optimization"
      }
    ]
  },
  "lastUpdate": 1709800300000
}
```

---

## 四、前端设计

### 4.1 类型定义扩展

```typescript
// frontend/src/types/collaboration.ts

/**
 * 单个活跃任务
 */
export interface ActiveTask {
  id: string
  name: string
  status: 'working' | 'retrying' | 'failed'
  timestamp?: number
  childAgentId?: string    // 主 Agent 任务时，指向被派发的子 Agent
  featureId?: string       // FEATURE_ID（如果有）
}

/**
 * 扩展 CollaborationFlow
 */
export interface CollaborationFlow {
  // 现有字段...
  nodes: CollaborationNode[]
  edges: CollaborationEdge[]
  activePath: string[]
  lastUpdate: number
  mainAgentId?: string
  agentModels?: Record<string, { primary?: string; fallbacks?: string[] }>
  models?: string[]
  recentCalls?: ModelCall[]
  hierarchy?: Record<string, string[]>
  depths?: Record<string, number>
  
  // 新增字段
  agentActiveTasks?: Record<string, ActiveTask[]>
}

/**
 * 扩展 CollaborationDynamic  
 */
export interface CollaborationDynamic {
  // 现有字段...
  activePath: string[]
  recentCalls: ModelCall[]
  agentStatuses: Record<string, string>
  agentDynamicStatuses?: Record<string, AgentDynamicStatus>
  agentDisplayStatuses?: Record<string, AgentDisplayStatus>
  taskNodes: CollaborationNode[]
  taskEdges: CollaborationEdge[]
  mainAgentId: string
  lastUpdate: number
  
  // 新增字段
  agentActiveTasks?: Record<string, ActiveTask[]>
}
```

### 4.2 AgentCard 组件增强

#### 4.2.1 Props 扩展

```typescript
// AgentCard.vue

interface Props {
  agent: {
    name: string
    status: 'idle' | 'working' | 'down'
    lastActiveFormatted?: string
  }
  modelInfo?: { primary?: string; fallbacks?: string[] }
  isMain?: boolean
  currentTask?: string           // 保留：单任务时的显示文本
  agentTasks?: ActiveTask[]      // 新增：多任务列表
  error?: AgentError
  stuckWarning?: StuckWarning
  hierarchyDepth?: number
  agentColor?: string
  subStatus?: SubStatus
  currentAction?: string
  toolName?: string
  waitingFor?: string
}
```

#### 4.2.2 模板设计

```vue
<template>
  <div class="agent-card" :class="[...]">
    <!-- 警告指示器 -->
    <div v-if="error || stuckWarning" class="warning-indicator">...</div>
    
    <!-- 头部 -->
    <div class="card-header">...</div>
    
    <!-- 内容区 -->
    <div class="card-body">
      <!-- 模型信息 -->
      <div v-if="modelInfo?.primary" class="model-row">...</div>
      
      <!-- 单任务显示（原有逻辑，无 agentTasks 时使用） -->
      <div v-if="!agentTasks?.length && currentTask" class="current-task">
        <div class="task-header">
          <span class="task-icon">▶</span>
          <span class="task-label">当前任务</span>
        </div>
        <div class="task-name">{{ currentTask }}</div>
      </div>
      
      <!-- 多任务显示（新增） -->
      <div v-else-if="agentTasks && agentTasks.length > 0" class="task-list-container">
        <!-- 任务列表头部 -->
        <div class="task-list-header" @click="taskListExpanded = !taskListExpanded">
          <span class="task-icon">📋</span>
          <span class="task-count">{{ agentTasks.length }} 个任务</span>
          <span class="expand-icon">{{ taskListExpanded ? '▼' : '▶' }}</span>
        </div>
        
        <!-- 任务列表（可折叠） -->
        <Transition name="slide">
          <div v-show="taskListExpanded" class="task-list">
            <div 
              v-for="task in displayedTasks" 
              :key="task.id" 
              class="task-item"
              @click.stop="$emit('task-click', task)"
            >
              <span class="task-name" :title="task.name">{{ task.name }}</span>
              <span v-if="task.childAgentId" class="task-target">
                → {{ getAgentShortName(task.childAgentId) }}
              </span>
              <span v-if="task.featureId" class="task-feature">{{ task.featureId }}</span>
            </div>
            <div v-if="agentTasks.length > maxDisplayedTasks" class="task-more">
              还有 {{ agentTasks.length - maxDisplayedTasks }} 个任务...
            </div>
          </div>
        </Transition>
      </div>
      
      <!-- 空闲状态 -->
      <div v-else-if="agent.status === 'idle'" class="idle-hint">
        空闲中，等待任务...
      </div>
    </div>
  </div>
</template>
```

#### 4.2.3 脚本逻辑

```typescript
<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ActiveTask } from '../../types/collaboration'

// Props
const props = defineProps<{
  agent: Agent
  modelInfo?: ModelInfo
  isMain?: boolean
  currentTask?: string
  agentTasks?: ActiveTask[]    // 新增
  // ...其他 props
}>()

const emit = defineEmits<{
  click: []
  'navigate-agent': [agentId: string]
  'task-click': [task: ActiveTask]   // 新增
}>()

// 多任务列表折叠状态
const taskListExpanded = ref(false)
const maxDisplayedTasks = 5

// 显示的任务（限制数量）
const displayedTasks = computed(() => {
  if (!props.agentTasks) return []
  return props.agentTasks.slice(0, maxDisplayedTasks)
})

// Agent 简称映射
const AGENT_SHORT_NAMES: Record<string, string> = {
  'analyst-agent': 'BA',
  'architect-agent': 'SA', 
  'devops-agent': 'Dev',
}

function getAgentShortName(agentId: string): string {
  return AGENT_SHORT_NAMES[agentId] || agentId
}
</script>
```

### 4.3 CollaborationFlowSection 改动

#### 4.3.1 数据接收

```typescript
// CollaborationFlowSection.vue

const agentActiveTasks = ref<Record<string, ActiveTask[]>>({})

// 处理全量数据更新
function handleCollaborationUpdate(data: unknown): void {
  const flow = data as CollaborationFlow
  nodes.value = flow.nodes || []
  edges.value = flow.edges || []
  // ...其他字段
  
  // 新增：接收 agentActiveTasks
  if (flow.agentActiveTasks) {
    agentActiveTasks.value = flow.agentActiveTasks
  }
  
  nextTick(updateEdges)
}

// 处理动态数据更新
function handleCollaborationDynamicUpdate(dyn: CollaborationDynamic): void {
  // ...现有逻辑
  
  // 新增：合并 agentActiveTasks
  if (dyn.agentActiveTasks) {
    agentActiveTasks.value = dyn.agentActiveTasks
  }
}
```

#### 4.3.2 传递数据给 AgentCard

```vue
<template>
  <div class="collaboration-flow-section">
    <!-- ... -->
    <AgentCard
      :agent="getAgentForNode(node)"
      :model-info="getModelInfoForNode(node)"
      :is-main="node.id === computedMainAgentId"
      :current-task="node.currentTask"
      :agent-tasks="getAgentTasksForNode(node)"
      :error="node.error"
      :stuck-warning="node.stuckWarning"
      :agent-color="getAgentColor(node.id)"
      @task-click="handleTaskClick"
    />
  </div>
</template>

<script setup lang="ts">
function getAgentTasksForNode(node: CollaborationNode): ActiveTask[] {
  return agentActiveTasks.value[node.id] || []
}

function handleTaskClick(task: ActiveTask): void {
  // 可选：点击任务时的行为
  // 例如：高亮相关连线、显示任务详情等
  console.log('Task clicked:', task)
}
</script>
```

### 4.4 样式设计

```css
/* AgentCard.vue 新增样式 */

/* 多任务列表容器 */
.task-list-container {
  margin-top: 0.5rem;
}

/* 任务列表头部 */
.task-list-header {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 0.6rem;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #93c5fd;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.task-list-header:hover {
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
}

.task-list-header .task-icon {
  font-size: 0.85rem;
}

.task-list-header .task-count {
  flex: 1;
  font-size: 0.75rem;
  font-weight: 600;
  color: #1e40af;
}

.task-list-header .expand-icon {
  font-size: 0.6rem;
  color: #3b82f6;
  transition: transform 0.2s;
}

/* 任务列表 */
.task-list {
  margin-top: 0.4rem;
  padding: 0.4rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
}

/* 单个任务项 */
.task-item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.5rem;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}

.task-item:hover {
  background: #e0e7ff;
}

.task-item .task-name {
  flex: 1;
  font-size: 0.7rem;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-item .task-target {
  font-size: 0.65rem;
  color: #3b82f6;
  font-weight: 500;
}

.task-item .task-feature {
  font-size: 0.6rem;
  color: #8b5cf6;
  background: #ede9fe;
  padding: 1px 4px;
  border-radius: 3px;
}

/* 更多任务提示 */
.task-more {
  font-size: 0.65rem;
  color: #64748b;
  text-align: center;
  padding: 0.3rem;
  border-top: 1px dashed #e2e8f0;
  margin-top: 0.3rem;
}

/* 折叠动画 */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.2s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
}

.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 200px;
}
```

---

## 五、连线渲染增强（可选）

### 5.1 多连线策略

当主 Agent 同时派发多个任务时，需要渲染多条连线：

```
     ┌──────────────┐
     │     PM       │
     │ 3 个任务     │
     └──────┬───────┘
            │
    ┌───────┼───────┐
    │       │       │
    ▼       ▼       ▼
┌──────┐ ┌──────┐ ┌──────┐
│  BA  │ │  SA  │ │ Dev  │
└──────┘ └──────┘ └──────┘
```

### 5.2 实现方式

当前连线基于 `delegateEdges`（type='delegates'），需要扩展为动态连线：

```typescript
// CollaborationFlowSection.vue

// 计算活跃连线（主 Agent → 正在工作的子 Agent）
const activeDelegateEdges = computed(() => {
  const mainTasks = agentActiveTasks.value[computedMainAgentId.value] || []
  const edges: CollaborationEdge[] = []
  
  for (const task of mainTasks) {
    if (task.childAgentId) {
      edges.push({
        id: `edge-active-${task.childAgentId}`,
        source: computedMainAgentId.value,
        target: task.childAgentId,
        type: 'delegates',
        label: task.featureId || task.name.slice(0, 10),
        animated: true  // 活跃连线动画
      })
    }
  }
  
  return edges
})

// 合并到渲染连线
const renderEdges = computed(() => {
  return [...delegateEdges.value, ...activeDelegateEdges.value]
})
```

---

## 六、实施清单

### 6.1 后端改动

| 序号 | 文件 | 改动内容 | 工作量 |
|------|------|----------|--------|
| 1 | `collaboration.py` | 新增 `ActiveTask` 模型 | 小 |
| 2 | `collaboration.py` | 扩展 `CollaborationFlow` 模型 | 小 |
| 3 | `collaboration.py` | 扩展 `CollaborationDynamic` 模型 | 小 |
| 4 | `collaboration.py` | 实现 `_build_agent_active_tasks()` | 中 |
| 5 | `collaboration.py` | 移除 `main_agent_task_created` 限制 | 小 |
| 6 | `collaboration.py` | 放宽 `active_runs[:10]` → `[:20]` | 小 |
| 7 | `collaboration.py` | 子 Agent `currentTask` 多任务策略 | 小 |
| 8 | `collaboration.py` | `get_collaboration()` 返回 `agentActiveTasks` | 小 |
| 9 | `collaboration.py` | `get_collaboration_dynamic()` 返回 `agentActiveTasks` | 小 |

### 6.2 前端改动

| 序号 | 文件 | 改动内容 | 工作量 |
|------|------|----------|--------|
| 1 | `collaboration.ts` | 新增 `ActiveTask` 接口 | 小 |
| 2 | `collaboration.ts` | 扩展 `CollaborationFlow` 接口 | 小 |
| 3 | `collaboration.ts` | 扩展 `CollaborationDynamic` 接口 | 小 |
| 4 | `AgentCard.vue` | 新增 `agentTasks` prop | 小 |
| 5 | `AgentCard.vue` | 多任务列表模板 | 中 |
| 6 | `AgentCard.vue` | 折叠/展开逻辑 | 小 |
| 7 | `AgentCard.vue` | 样式 | 小 |
| 8 | `CollaborationFlowSection.vue` | 接收 `agentActiveTasks` | 小 |
| 9 | `CollaborationFlowSection.vue` | 传递 `agentTasks` 给 AgentCard | 小 |
| 10 | `CollaborationFlowSection.vue` | 动态更新处理 | 小 |

### 6.3 测试要点

| 测试项 | 验证内容 |
|--------|----------|
| 单任务显示 | 原有逻辑不受影响 |
| 双任务显示 | PM 同时派发 2 个任务，卡片显示 "2 个任务" |
| 多任务显示 | PM 派发 5+ 个任务，列表可折叠滚动 |
| 子 Agent 多任务 | 子 Agent 同时执行 2 个任务，显示 "2 个任务进行中" |
| 动态轮询 | 3s 刷新后，多任务状态保持正确 |
| 任务完成 | 任务完成后，从列表中移除 |
| 连线动画 | 活跃连线显示动画效果 |

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 任务过多导致布局拥挤 | UI 混乱 | 限制 `maxDisplayedTasks=5`，折叠显示 |
| 旧前端不识别新字段 | 控制台警告 | 字段可选，`?.` 安全访问 |
| 动态接口未同步 | 闪烁 | 必须同步扩展 `/collaboration/dynamic` |
| API 响应变慢 | 用户体验 | `_build_agent_active_tasks` 复杂度 O(n)，影响小 |
| 连线过多视觉混乱 | 难以阅读 | 活跃连线高亮，静态连线淡化 |

### 回退方案

1. 后端：还原 `main_agent_task_created` 逻辑
2. 前端：移除 `agentTasks` prop，回退到 `currentTask` 单任务显示

---

## 八、验收标准

### 8.1 功能验收

- [ ] PM 同时派发 3 个任务，Dashboard 显示 3 个任务
- [ ] PM 卡片展开后显示任务列表，每个任务标注目标子 Agent
- [ ] 子 Agent 有 2+ 任务时，显示 "N 个任务进行中"
- [ ] 点击任务列表头部可折叠/展开
- [ ] 动态轮询 3s 后，多任务状态保持正确
- [ ] 任务完成后，从列表中移除

### 8.2 性能验收

- [ ] `/api/collaboration` 响应时间 < 500ms（20 个活跃任务）
- [ ] `/api/collaboration/dynamic` 响应时间 < 200ms
- [ ] 前端渲染无明显卡顿

### 8.3 兼容性验收

- [ ] 无 `agentActiveTasks` 时，原有单任务显示正常
- [ ] 旧前端访问新 API 不报错

---

## 九、后续优化方向

1. **任务详情弹窗**：点击任务项显示详细信息（时间、参数、状态）
2. **任务筛选**：按 Agent、Feature、状态筛选任务
3. **任务时间线**：任务执行进度可视化
4. **连线标签**：连线上显示 Feature ID 或任务名称
5. **任务取消**：支持从 Dashboard 取消运行中的任务
