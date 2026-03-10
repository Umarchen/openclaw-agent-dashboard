# 任务状态模块深度分析

> 文档版本：1.0  
> 创建日期：2026-03-07  
> 分析目标：明确任务状态模块的独立价值，区分与协作流程的定位差异

---

## 一、模块定位与差异化价值

### 1.1 核心问题

**用户提问**：任务状态模块是否应该与协作流程合并？它有什么独特价值？

**结论**：**任务状态模块应该独立存在**，它与协作流程是互补关系，而非竞争关系。

### 1.2 两个模块的本质区别

| 维度 | 协作流程 | 任务状态 |
|------|----------|----------|
| **关注点** | Agent 实时状态与拓扑 | Task 历史记录与结果 |
| **时间视角** | "现在正在发生什么" | "完成了哪些任务" |
| **粒度** | Agent 级别（谁在干活） | Task 级别（干了什么活） |
| **生命周期** | 瞬态（随 Agent 状态变化） | 持久化（历史可追溯） |
| **核心用户问题** | "我的团队现在在干什么？" | "这个任务完成得怎么样？" |
| **数据结构** | 拓扑图（节点+边） | 列表（记录+状态） |
| **典型场景** | 实时监控、资源调度 | 任务审计、问题排查 |

### 1.3 用户场景对比

```
场景 A：实时监控（协作流程）
─────────────────────────────────────────────────────────────
用户工作：
  "我的多 Agent 团队现在在干什么？有没有卡住？"
  
协作流程展示：
  ┌──────────┐     委托      ┌──────────┐
  │ 主 Agent │ ────────────→ │分析师    │ 正在执行...
  │  (思考中)│               │ 执行中   │
  └──────────┘               └──────────┘
       │
       └── 等待子任务完成
  
用户行为：观察 Agent 状态，判断是否需要干预

─────────────────────────────────────────────────────────────

场景 B：任务审计（任务状态）
─────────────────────────────────────────────────────────────
用户工作：
  "之前重构认证模块的任务完成了吗？生成了哪些文件？"
  
任务状态展示：
  ┌─────────────────────────────────────────────────────┐
  │ ✅ 重构认证模块                                     │
  │    devops-agent · 2分15秒 · 09:23-09:25            │
  │    结果：新增 3 文件，修改 5 文件                    │
  │    输出：已完成 JWT 认证重构...                     │
  └─────────────────────────────────────────────────────┘
  
用户行为：查看任务详情，检查输出和生成的文件

─────────────────────────────────────────────────────────────

场景 C：失败分析（任务状态）
─────────────────────────────────────────────────────────────
用户工作：
  "为什么部署任务失败了？具体报什么错？"
  
任务状态展示：
  ┌─────────────────────────────────────────────────────┐
  │ ❌ 部署到测试环境                                   │
  │    devops-agent · 45秒 · 10:15-10:16               │
  │    失败原因：任务执行超时                            │
  │    Agent 工作区：~/.openclaw/workspaces/devops      │
  └─────────────────────────────────────────────────────┘
  
用户行为：分析失败原因，决定是否重试
```

### 1.4 关键差异总结

| 用户问题 | 查看模块 | 原因 |
|----------|----------|------|
| "现在谁在干活？" | 协作流程 | 需要实时 Agent 状态 |
| "这个任务做完了吗？" | 任务状态 | 需要任务完成状态 |
| "任务执行了多久？" | 任务状态 | 需要历史耗时统计 |
| "为什么这个任务失败了？" | 任务状态 | 需要错误详情和上下文 |
| "任务生成了哪些文件？" | 任务状态 | 需要输出和产物 |
| "Agent A 的负载高吗？" | 协作流程 | 需要实时任务数 |
| "查看昨天所有失败任务" | 任务状态 | 需要历史搜索过滤 |

---

## 二、功能架构分析

### 2.1 当前实现功能清单

#### 已实现功能

| 功能 | 前端组件 | 后端 API | 数据源 |
|------|----------|----------|--------|
| 任务列表展示 | TaskStatusSection.vue | /api/tasks | runs.json |
| 状态过滤 | TaskStatusSection.vue | - | 前端过滤 |
| 搜索功能 | TaskStatusSection.vue | - | 前端过滤 |
| 任务详情弹窗 | TaskStatusSection.vue | - | 前端状态 |
| Agent 输出展示 | TaskStatusSection.vue | subagents.py | *.jsonl |
| 生成文件列表 | TaskStatusSection.vue | subagents.py | *.jsonl |
| 耗时计算 | subagents.py | calculate_runtime() | runs.json |
| 错误信息格式化 | subagents.py | _format_error_message() | runs.json |
| 任务路径提取 | subagents.py | _extract_task_path() | runs.json |
| 历史持久化 | task_history.py | merge_with_history() | task_history.json |

#### 数据模型

```typescript
// types/task.ts
interface Task {
  id: string
  name: string                      // 任务摘要
  task?: string                     // 完整任务内容
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number                  // 0-100
  startTime?: number
  endTime?: number
  agentId?: string
  agentName?: string
  agentWorkspace?: string           // Agent 工作区路径
  taskPath?: string                 // 项目路径
  subtasks?: Task[]
  error?: string
  output?: string                   // Agent 输出内容
  generatedFiles?: string[]         // 生成的文件路径
  metadata?: Record<string, unknown>
}
```

### 2.2 数据流分析

```
数据源                    处理层                    展示层
─────────────────────────────────────────────────────────────
                          subagent_reader.py
runs.json ───────────────→ load_subagent_runs() ──┐
                          get_active_runs()       │
                          get_agent_runs()        │
                                                  ├──→ /api/tasks ──→ TaskStatusSection.vue
sessions.json ───────────→ get_agent_output_for_run()
                          get_agent_files_for_run() ──┘

task_history.json ───────→ merge_with_history() ──────→ 持久化已完成任务
```

### 2.3 现有问题

#### 问题 1：进度百分比硬编码

```python
# api/subagents.py:252
progress = 100 if run.get('endedAt') else 50  # 硬编码！
```

**影响**：执行中的任务显示 50%，已完成显示 100%，无法反映真实进度。

**建议**：基于 session 消息数/步骤数计算：
```python
def calculate_progress(child_session_key: str) -> int:
    """基于消息数估算进度"""
    # 解析 session 文件，统计 assistant 消息数
    # 假设平均任务需要 5-10 轮对话
    # progress = min(90, msg_count * 10)  # 每条消息 10%，最高 90%
    pass
```

#### 问题 2：Agent 名称硬编码

```typescript
// TaskStatusSection.vue:274-282
function getAgentName(agentId: string) {
  const names: Record<string, string> = {
    main: '主 Agent',
    'analyst-agent': '分析师',
    // ...
  }
  return names[agentId] || agentId
}
```

**建议**：从 `/api/agents` 获取动态映射，或通过 props 传入。

#### 问题 3：实时更新未验证

```typescript
// TaskStatusSection.vue:368
unsubscribe = subscribe('tasks', handleTasksUpdate)
```

需确认 WebSocket 是否正确推送 tasks 频道的数据。当前 `file_watcher.py` 可能未实现 tasks 频道。

#### 问题 4：子任务功能未激活

```typescript
// TaskStatusSection.vue:129-138
<div v-if="selectedTask.subtasks?.length" class="detail-row">
  <span class="detail-label">子任务</span>
  ...
</div>
```

后端 `_run_to_task()` 未填充 `subtasks` 字段，导致此功能不生效。

---

## 三、独特功能增强建议

### 3.1 短期增强（保持差异化）

#### 增强 1：任务时间线视图

在详情弹窗中展示任务执行时间线：

```
任务执行时间线
─────────────────────────────────────────────────────────────
09:23:15  任务开始
09:23:18  分析代码结构
09:24:02  生成重构方案
09:24:45  执行代码修改
09:25:30  任务完成
─────────────────────────────────────────────────────────────
总耗时：2分15秒
```

**实现**：解析 session 文件，提取 assistant 消息的时间戳。

#### 增强 2：失败任务快速筛选

在头部增加快速筛选按钮：

```
┌─────────────────────────────────────────────────────────────┐
│ 任务状态                                    [仅失败] [今日]  │
├─────────────────────────────────────────────────────────────┤
│ ❌ 部署到测试环境     devops-agent     45秒    10:15       │
│ ❌ 运行测试用例       test-agent       1分20秒  09:45       │
└─────────────────────────────────────────────────────────────┘
```

**实现**：
```typescript
const quickFilters = ref({
  failedOnly: false,
  todayOnly: false
})

const filteredTasks = computed(() => {
  let result = tasks.value
  if (quickFilters.value.failedOnly) {
    result = result.filter(t => t.status === 'failed')
  }
  if (quickFilters.value.todayOnly) {
    const today = new Date().setHours(0, 0, 0, 0)
    result = result.filter(t => t.startTime >= today)
  }
  return result
})
```

#### 增强 3：任务结果快速预览

在列表项中增加结果预览：

```
┌─────────────────────────────────────────────────────────────┐
│ ✅ 重构用户认证模块                                          │
│    devops-agent · 2分15秒 · 09:25                           │
│    结果：新增 2 文件，修改 3 文件                            │
└─────────────────────────────────────────────────────────────┘
```

**实现**：
```typescript
// 在 Task 接口中增加 summary 字段
interface Task {
  // ...
  summary?: string  // "新增 2 文件，修改 3 文件"
}
```

### 3.2 中期增强（功能扩展）

#### 增强 4：任务对比功能

用户可选择两个任务进行对比：

```
任务对比
─────────────────────────────────────────────────────────────
              任务 A              任务 B
开始时间      09:23               10:15
执行者        devops-agent        architect-agent
耗时          2分15秒             1分30秒
Token 消耗    15,234              8,921
结果文件      5 个                3 个
```

**场景**：对比同一任务的不同执行结果，或对比不同 Agent 执行类似任务的效率。

#### 增强 5：任务依赖关系

展示任务之间的依赖关系（如果存在）：

```
任务依赖图
─────────────────────────────────────────────────────────────
[分析需求] ──→ [设计方案] ──→ [实现代码]
                              ↓
                         [运行测试]
```

**实现**：从 session 消息中提取任务派发链，构建依赖图。

#### 增强 6：任务导出

支持导出任务执行报告（Markdown/JSON）：

```markdown
## 任务执行报告

**任务**：重构用户认证模块
**执行者**：devops-agent
**状态**：已完成
**耗时**：2分15秒
**Token 消耗**：15,234

### 生成的文件
- src/auth/login.py
- src/auth/session.py
- tests/test_auth.py

### Agent 输出
> 已完成用户认证模块重构，采用 JWT 方案...
```

---

## 四、与协作流程的联动设计

### 4.1 交叉跳转

```
协作流程 ──点击任务节点──→ 任务状态（高亮该任务）
任务状态 ──点击 Agent ──→ 协作流程（聚焦该 Agent）
```

**实现**：
```typescript
// TaskStatusSection.vue
function onAgentClick(agentId: string) {
  emit('agent-click', { agentId })
  // 父组件监听，切换到协作流程 tab 并高亮该 Agent
}

// CollaborationFlowSection.vue
function highlightTask(taskId: string) {
  // 高亮指定的任务节点
}
```

### 4.2 状态同步

```
协作流程展示：Agent 当前正在执行的任务
     ↓
任务状态展示：该任务的历史执行记录
```

**数据共享**：
```typescript
// 共享 task id，用于关联
interface Task {
  id: string  // runId，协作流程的任务节点也使用此 id
  // ...
}
```

### 4.3 统一数据模型

建议将 Task 类型与 CollaborationNode 中的 task 类型统一：

```typescript
// 统一的任务类型
interface UnifiedTask {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  
  // 协作流程关注的字段
  agentId: string
  requesterId?: string  // 派发者
  
  // 任务状态关注的字段
  startTime: number
  endTime?: number
  duration?: number
  output?: string
  generatedFiles?: string[]
  error?: string
  
  // 共享字段
  taskPath?: string
  tokens?: number
}
```

---

## 五、典型用户场景与模块选择

### 5.1 场景决策树

```
用户需求
    │
    ├── 想知道"现在"的状态
    │       │
    │       ├── Agent 在干什么？ ─────────→ 协作流程
    │       ├── 任务卡住了吗？ ───────────→ 协作流程
    │       └── 谁在执行哪个任务？ ────────→ 协作流程
    │
    └── 想知道"过去"或"结果"
            │
            ├── 任务完成了吗？ ───────────→ 任务状态
            ├── 执行了多久？ ─────────────→ 任务状态
            ├── 输出了什么？ ─────────────→ 任务状态
            ├── 生成了哪些文件？ ─────────→ 任务状态
            ├── 为什么失败？ ─────────────→ 任务状态
            └── 查看历史任务 ─────────────→ 任务状态
```

### 5.2 详细场景映射

| 场景 | 首选模块 | 辅助模块 | 说明 |
|------|----------|----------|------|
| 1. 监控团队工作状态 | 协作流程 | - | 实时 Agent 状态 |
| 2. 发现任务卡住 | 协作流程 | 任务状态 | 先看协作流程发现异常，再看任务状态了解详情 |
| 3. 检查任务完成情况 | 任务状态 | - | 历史记录 |
| 4. 分析失败原因 | 任务状态 | 协作流程 | 任务状态看错误，协作流程看上下文 |
| 5. 评估 Agent 效率 | 任务状态 | 性能数据 | 任务耗时 + Token 消耗 |
| 6. 回溯任务执行过程 | 任务状态 | 时间线 | 任务详情 + 执行时间线 |
| 7. 规划资源分配 | 协作流程 | 任务状态 | Agent 负载 + 任务队列 |
| 8. 生成工作报告 | 任务状态 | - | 任务导出功能 |

---

## 六、实现优先级建议

### 6.1 P0（必须修复）

| 任务 | 原因 | 工作量 |
|------|------|--------|
| 修复实时更新 | 核心功能不生效 | 中 |
| 实现 WebSocket tasks 频道 | 实时性要求 | 中 |
| 消除 Agent 名称硬编码 | 可维护性 | 低 |

### 6.2 P1（重要增强）

| 任务 | 价值 | 工作量 |
|------|------|--------|
| 任务时间线视图 | 差异化功能 | 中 |
| 失败任务快速筛选 | 效率提升 | 低 |
| 任务结果预览 | 体验提升 | 低 |
| 进度百分比真实计算 | 准确性 | 中 |

### 6.3 P2（功能扩展）

| 任务 | 价值 | 工作量 |
|------|------|--------|
| 任务对比功能 | 高级分析 | 中 |
| 任务依赖图 | 可视化 | 高 |
| 任务导出 | 报告生成 | 中 |

---

## 七、总结

### 任务状态模块的独特价值

1. **历史视角**：记录任务完整生命周期，协作流程只展示实时状态
2. **结果导向**：展示任务输出、生成的文件，协作流程不关注结果
3. **可追溯性**：持久化历史记录，支持搜索和过滤
4. **分析能力**：失败分析、耗时统计、Token 消耗

### 与协作流程的互补关系

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│     协作流程                      任务状态                       │
│    ─────────                    ─────────                       │
│    "正在发生什么？"              "完成了什么？"                   │
│    实时监控                      历史追溯                        │
│    Agent 视角                    Task 视角                       │
│    拓扑可视化                    列表+搜索                       │
│                                                                 │
│              └────── 互补而非竞争 ──────┘                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 核心建议

1. **保持模块独立性**：任务状态有其独特价值，不应与协作流程合并
2. **强化差异化功能**：时间线、失败分析、结果预览
3. **增强模块联动**：两个模块之间支持交叉跳转
4. **统一数据模型**：共享 Task 类型定义，避免重复

---

## 附录：相关文件索引

### 前端文件

| 文件 | 说明 |
|------|------|
| `frontend/src/components/tasks/TaskStatusSection.vue` | 任务状态主组件 |
| `frontend/src/types/task.ts` | 任务类型定义 |

### 后端文件

| 文件 | 说明 |
|------|------|
| `src/backend/api/subagents.py` | 任务 API 路由 |
| `src/backend/subagent_reader.py` | 任务数据读取 |
| `src/backend/data/task_history.py` | 任务历史持久化 |

### 数据文件

| 文件 | 说明 |
|------|------|
| `~/.openclaw/subagents/runs.json` | 子代理运行记录 |
| `~/.openclaw-agent-dashboard/task_history.json`（或 `$OPENCLAW_AGENT_DASHBOARD_DATA/task_history.json`） | 任务历史持久化 |
| `~/.openclaw/agents/*/sessions/*.jsonl` | Session 消息日志 |
