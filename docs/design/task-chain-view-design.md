# 任务执行链路图 - 详细设计文档

**功能名称**: 任务执行链路图 (Task Execution Chain View)
**优先级**: P0
**版本**: 1.0
**日期**: 2026-03-03

---

## 一、需求背景

### 1.1 核心痛点

当前 Dashboard 只展示**静态的 Agent 拓扑图**，无法看到任务在 Agent 之间流转的动态过程：

| 需要看到的 | 当前状态 |
|-----------|---------|
| 任务从哪个 Agent 派发到哪个 Agent | ❌ 看不到 |
| 每个环节的输入/输出是什么 | ❌ 看不到 |
| 每个环节耗时多久 | ❌ 看不到 |
| 当前任务卡在哪个环节 | ❌ 看不到 |
| 整个任务链的完成进度 | ❌ 看不到 |

### 1.2 目标

提供**动态的任务执行链路视图**，让用户能够：

1. 直观看到任务在 Agent 间的流转路径
2. 实时追踪每个环节的状态（等待/进行中/完成/失败）
3. 点击任一节点查看该环节的详细信息
4. 了解整体任务进度和预估完成时间

---

## 二、数据源分析

### 2.1 SubagentRunRecord 结构

`~/.openclaw/subagents/runs.json` 存储子代理运行记录：

```json
{
  "version": 2,
  "runs": {
    "run_xxx": {
      "runId": "xxx",
      "childSessionKey": "agent:analyst-agent:subagent:uuid",
      "requesterSessionKey": "agent:main:main",
      "task": "根据需求文档编写 PRD",
      "startedAt": 1730000000000,
      "endedAt": 1730000060000,
      "outcome": "ok"
    }
  }
}
```

### 2.2 链路关系推导

```
requesterSessionKey: agent:main:main
                    ↓ 派发
childSessionKey: agent:analyst-agent:subagent:uuid
                    ↓ 派发
childSessionKey: agent:architect-agent:subagent:uuid2
                    ↓ 派发
childSessionKey: agent:devops-agent:subagent:uuid3
```

### 2.3 任务上下文关联

通过 `vrt-projects/projects/<project-id>/.staging/workflow_state.json` 获取项目上下文：

```json
{
  "projectId": "hello-cli",
  "artifacts": {
    "hello_spec.md": {"status": "APPROVED", "creator": "analyst-agent"},
    "design.md": {"status": "PENDING_REVIEW", "creator": "architect-agent"}
  }
}
```

---

## 三、UI 设计

### 3.1 整体布局

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  🔗 任务执行链路                                          [🔄] [⚙️]         │
├─────────────────────────────────────────────────────────────────────────────┤
│  项目: hello-cli                                        开始: 10:30:00     │
│  任务: 开发用户登录功能                                  状态: 🔄 进行中    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                          任务执行链路图                                  ││
│  │                                                                          ││
│  │    ┌────────┐     ┌─────────┐     ┌───────────┐     ┌──────────────┐   ││
│  │    │  Main  │────▶│ Analyst │────▶│ Architect │────▶│   DevOps     │   ││
│  │    │  派发   │     │  PRD✅   │     │  设计🔄   │     │   开发⏳     │   ││
│  │    │ 10:30   │     │ 10:35   │     │  10:42    │     │   10:50      │   ││
│  │    │         │     │ 7min    │     │  进行中   │     │   等待中     │   ││
│  │    └────────┘     └─────────┘     └───────────┘     └──────────────┘   ││
│  │                                                                          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  总进度: ████████░░░░░░░░ 53% (2/4 完成)                                    │
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  📋 链路详情 (点击节点查看)                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  选中: Architect (设计阶段)                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ 状态: 🔄 进行中                                                          ││
│  │ 开始: 10:42:15                                                          ││
│  │ 已耗时: 3分20秒                                                          ││
│  ├─────────────────────────────────────────────────────────────────────────┤│
│  │ 输入:                                                                    ││
│  │ ┌─────────────────────────────────────────────────────────────────────┐ ││
│  │ │ PRD 文档 (hello_spec.md)                                             │ ││
│  │ │ 根据 PRD 进行系统设计...                                              │ ││
│  │ └─────────────────────────────────────────────────────────────────────┘ ││
│  ├─────────────────────────────────────────────────────────────────────────┤│
│  │ 输出: (进行中)                                                           ││
│  │ ┌─────────────────────────────────────────────────────────────────────┐ ││
│  │ │ design.md (待审核)                                                   │ ││
│  │ │ 系统架构设计文档正在编写中...                                          │ ││
│  │ └─────────────────────────────────────────────────────────────────────┘ ││
│  ├─────────────────────────────────────────────────────────────────────────┤│
│  │ 工具调用: 5 次 (Read x3, Write x1, Bash x1)                             ││
│  │ Token: 1,200 / 800                                                      ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 节点状态样式

| 状态 | 图标 | 边框色 | 背景色 | 说明 |
|------|------|--------|--------|------|
| 等待 | ⏳ | #9ca3af | #f3f4f6 | 灰色，虚线边框 |
| 进行中 | 🔄 | #3b82f6 | #eff6ff | 蓝色，动画边框 |
| 完成 | ✅ | #22c55e | #f0fdf4 | 绿色 |
| 失败 | ❌ | #ef4444 | #fef2f2 | 红色 |

### 3.3 连接线设计

```
完成 → 完成:    ═════▶  实线绿色箭头
完成 → 进行中:  ═════▶  实线蓝色箭头，动画
进行中 → 等待:  - - - ▶  虚线灰色箭头
完成 → 失败:    ═════▶  实线红色箭头
```

### 3.4 进度条设计

```
总进度: ████████░░░░░░░░ 53% (2/4 完成)

颜色:
- 完成部分: #22c55e (绿色)
- 进行中: #3b82f6 (蓝色，动画)
- 等待: #e5e7eb (灰色)
```

---

## 四、数据结构

### 4.1 后端数据模型

```python
# 任务链节点
class ChainNode(BaseModel):
    agentId: str
    agentName: str
    role: str  # main, analyst, architect, devops

    status: str  # pending, running, completed, error
    startedAt: Optional[int] = None
    endedAt: Optional[int] = None
    duration: Optional[int] = None  # ms

    # 任务信息
    task: Optional[str] = None
    runId: Optional[str] = None

    # 输入输出
    input: Optional[str] = None
    output: Optional[str] = None
    artifacts: List[str] = []

    # 统计
    toolCallCount: int = 0
    tokenUsage: dict = {"input": 0, "output": 0}

# 任务链
class TaskChain(BaseModel):
    chainId: str
    projectId: Optional[str] = None
    rootTask: str  # 根任务描述

    startedAt: int
    status: str  # running, completed, error

    nodes: List[ChainNode]
    edges: List[dict]  # [{from: "main", to: "analyst"}]

    # 统计
    progress: float  # 0.0 - 1.0
    completedNodes: int
    totalNodes: int
    totalDuration: int

# 响应
class TaskChainResponse(BaseModel):
    chains: List[TaskChain]
    activeChain: Optional[TaskChain] = None
```

### 4.2 前端类型定义

```typescript
// types/taskChain.ts

export type ChainNodeStatus = 'pending' | 'running' | 'completed' | 'error'
export type ChainStatus = 'running' | 'completed' | 'error'

export interface ChainNode {
  agentId: string
  agentName: string
  role: 'main' | 'analyst' | 'architect' | 'devops'

  status: ChainNodeStatus
  startedAt?: number
  endedAt?: number
  duration?: number

  task?: string
  runId?: string

  input?: string
  output?: string
  artifacts: string[]

  toolCallCount: number
  tokenUsage: { input: number; output: number }
}

export interface ChainEdge {
  from: string
  to: string
}

export interface TaskChain {
  chainId: string
  projectId?: string
  rootTask: string

  startedAt: number
  status: ChainStatus

  nodes: ChainNode[]
  edges: ChainEdge[]

  progress: number
  completedNodes: number
  totalNodes: number
  totalDuration: number
}

export interface TaskChainResponse {
  chains: TaskChain[]
  activeChain?: TaskChain
}
```

---

## 五、后端 API 设计

### 5.1 REST API

#### GET /api/chains

获取所有任务链列表。

**响应**:
```json
{
  "chains": [
    {
      "chainId": "chain_001",
      "projectId": "hello-cli",
      "rootTask": "开发用户登录功能",
      "startedAt": 1730000000000,
      "status": "running",
      "progress": 0.53,
      "completedNodes": 2,
      "totalNodes": 4
    }
  ]
}
```

#### GET /api/chains/{chain_id}

获取单个任务链详情。

**响应**: 完整的 TaskChain 对象

#### GET /api/chains/active

获取当前活跃的任务链（正在执行的）。

**响应**:
```json
{
  "chains": [...],
  "activeChain": {
    "chainId": "chain_001",
    "nodes": [...],
    "edges": [...],
    ...
  }
}
```

### 5.2 WebSocket 事件

#### 连接: ws://host/api/chains/ws

**服务端推送**:
```typescript
// 节点状态变更
{
  "event": "node_status_change",
  "data": {
    "chainId": "chain_001",
    "nodeId": "analyst-agent",
    "status": "completed",
    "output": "PRD 文档已完成"
  }
}

// 新节点开始
{
  "event": "node_start",
  "data": {
    "chainId": "chain_001",
    "nodeId": "architect-agent",
    "task": "根据 PRD 进行系统设计"
  }
}

// 链路完成
{
  "event": "chain_complete",
  "data": {
    "chainId": "chain_001",
    "status": "completed",
    "totalDuration": 1800000
  }
}
```

---

## 六、组件设计

### 6.1 组件结构

```
TaskChainView.vue              # 主容器
├── ChainHeader.vue            # 头部（项目信息、状态）
├── ChainDiagram.vue           # 链路图（节点+连线）
│   ├── ChainNode.vue          # 单个节点
│   └── ChainEdge.vue          # 连接线
├── ChainProgress.vue          # 进度条
└── ChainDetailPanel.vue       # 节点详情面板
    ├── NodeStatus.vue         # 状态信息
    ├── NodeIO.vue             # 输入输出
    └── NodeStats.vue          # 统计信息
```

### 6.2 核心交互

1. **点击节点** → 展开详情面板
2. **悬停节点** → 显示简要 tooltip
3. **自动滚动** → 跟踪当前活跃节点
4. **刷新/实时更新** → WebSocket 推送

---

## 七、实现计划

### 7.1 阶段 1: 基础链路图（1天）

**后端**:
- [ ] 新增 `/api/chains` API
- [ ] 新增 `chain_reader.py` 解析 runs.json
- [ ] 构建 Agent 派发关系链

**前端**:
- [ ] 创建 `TaskChainView.vue` 主组件
- [ ] 创建 `ChainNode.vue` 节点组件
- [ ] 创建 `ChainEdge.vue` 连接线组件
- [ ] 实现基础布局

### 7.2 阶段 2: 详情展示（0.5天）

- [ ] 创建 `ChainDetailPanel.vue`
- [ ] 展示节点输入/输出
- [ ] 展示工具调用和 Token 统计

### 7.3 阶段 3: 实时更新（0.5天）

- [ ] WebSocket 实时推送节点状态
- [ ] 动画效果（进行中节点）
- [ ] 自动滚动到活跃节点

---

## 八、验收标准

### 8.1 功能验收

- [ ] 能正确展示 Main → SubAgent 的派发链路
- [ ] 每个节点状态正确（等待/进行中/完成/失败）
- [ ] 点击节点可查看详细信息
- [ ] 进度条正确反映整体进度
- [ ] WebSocket 实时更新正常

### 8.2 性能验收

- [ ] 10 个节点内渲染 < 500ms
- [ ] 实时更新延迟 < 200ms

---

## 九、文件清单

### 9.1 后端新增

```
src/backend/
├── api/
│   └── chains.py              # 链路 API
├── data/
│   └── chain_reader.py        # 链路数据解析
└── main.py                    # 注册路由
```

### 9.2 前端新增

```
frontend/src/
├── components/
│   └── chain/
│       ├── TaskChainView.vue      # 主容器
│       ├── ChainHeader.vue        # 头部
│       ├── ChainDiagram.vue       # 链路图
│       ├── ChainNode.vue          # 节点
│       ├── ChainEdge.vue          # 连接线
│       ├── ChainProgress.vue      # 进度条
│       ├── ChainDetailPanel.vue   # 详情面板
│       ├── index.ts               # 导出
│       └── types.ts               # 类型定义
```

---

*设计文档版本: 1.0*
*创建时间: 2026-03-03*
