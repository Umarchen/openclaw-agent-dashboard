# 看板交互可视化设计文档

**版本**: 1.0
**日期**: 2026-02-26
**状态**: 已完成

---

## 1. 概述

### 1.1 目标

为 OpenClaw Agent Dashboard 添加交互可视化功能，实时展示多 Agent 协作流程、任务状态和性能数据。

### 1.2 范围

- **仅观察层** - 不涉及执行逻辑
- **三大展示区域** - 协作流程、任务状态、性能数据
- **实时更新** - WebSocket + HTTP 轮询
- **性能优化** - 虚拟滚动、数据缓存、防抖节流

### 1.3 技术栈

- **前端**: Vue 3 + TypeScript + Composition API
- **样式**: Scoped CSS + CSS Variables
- **实时通信**: WebSocket + HTTP 轮询回退
- **状态管理**: Reactive + Provide/Inject

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Dashboard App                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐  │
│  │ CollaborationFlow│  │  TaskStatus     │  │ Performance │  │
│  │ Section          │  │  Section        │  │ Section     │  │
│  └────────┬────────┘  └────────┬────────┘  └──────┬──────┘  │
│           │                    │                   │         │
│           └────────────────────┼───────────────────┘         │
│                                │                             │
│                    ┌───────────▼───────────┐                 │
│                    │   EventDispatcher     │                 │
│                    └───────────┬───────────┘                 │
│                                │                             │
│                    ┌───────────▼───────────┐                 │
│                    │   StateManager        │                 │
│                    └───────────┬───────────┘                 │
│                                │                             │
│                    ┌───────────▼───────────┐                 │
│                    │ RealtimeDataManager   │                 │
│                    └───────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| **CollaborationFlowSection** | 展示 Agent 间的协作流程图 |
| **TaskStatusSection** | 展示任务状态列表和进度 |
| **PerformanceSection** | 展示性能数据和趋势图表 |
| **RealtimeDataManager** | 管理 WebSocket 连接和 HTTP 轮询 |
| **StateManager** | 集中状态管理和响应式数据 |
| **EventDispatcher** | 事件分发和组件通信 |

---

## 3. 数据模型

### 3.1 协作流程数据

```typescript
interface CollaborationNode {
  id: string
  type: 'agent' | 'task' | 'tool'
  name: string
  status: 'idle' | 'active' | 'completed' | 'error'
  timestamp?: number
}

interface CollaborationEdge {
  id: string
  source: string
  target: string
  type: 'delegates' | 'calls' | 'returns' | 'error'
  label?: string
}

interface CollaborationFlow {
  nodes: CollaborationNode[]
  edges: CollaborationEdge[]
  activePath: string[] // 当前活跃路径
}
```

### 3.2 任务状态数据

```typescript
interface Task {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  progress: number // 0-100
  startTime?: number
  endTime?: number
  agentId?: string
  subtasks?: Task[]
  error?: string
}

interface TaskStatus {
  tasks: Task[]
  total: number
  completed: number
  failed: number
  running: number
}
```

### 3.3 性能数据

```typescript
interface PerformanceMetric {
  timestamp: number
  tpm: number // Tokens per minute
  rpm: number // Requests per minute
  latency: number // API response time (ms)
  errorRate: number // 0-1
}

interface PerformanceData {
  current: PerformanceMetric
  history: PerformanceMetric[]
  aggregates: {
    avgTpm: number
    avgLatency: number
    totalTokens: number
    totalRequests: number
  }
}
```

---

## 4. 组件设计

### 4.1 CollaborationFlowSection

**功能**:
- 可视化 Agent 间的协作关系
- 高亮当前活跃的协作路径
- 支持缩放和平移

**组件结构**:
```
CollaborationFlowSection/
├── FlowCanvas.vue         # 主画布
├── FlowNode.vue           # 节点组件
├── FlowEdge.vue           # 边组件
└── FlowLegend.vue         # 图例说明
```

**交互**:
- 鼠标悬停显示详细信息
- 点击节点查看 Agent/Task 详情
- 自动滚动到活跃区域

### 4.2 TaskStatusSection

**功能**:
- 展示任务列表和状态
- 显示任务进度条
- 支持展开/折叠子任务

**组件结构**:
```
TaskStatusSection/
├── TaskList.vue           # 任务列表（虚拟滚动）
├── TaskItem.vue           # 任务项
├── TaskProgress.vue       # 进度条
└── TaskFilters.vue        # 筛选器
```

**交互**:
- 状态筛选（全部/运行中/已完成/失败）
- 任务搜索
- 展开/折叠子任务

### 4.3 PerformanceSection

**功能**:
- 展示实时性能指标
- 绘制趋势图表
- 显示性能告警

**组件结构**:
```
PerformanceSection/
├── MetricCards.vue        # 指标卡片
├── TrendChart.vue         # 趋势图
├── AlertPanel.vue         # 告警面板
└── TimeRangeSelector.vue  # 时间范围选择
```

**交互**:
- 时间范围切换（5m/15m/1h/6h）
- 指标筛选
- 告警静默

---

## 5. 数据管理模块

### 5.1 RealtimeDataManager

**职责**:
- 管理 WebSocket 连接
- 处理连接断开和重连
- 提供 HTTP 轮询回退
- 数据订阅和发布

**API**:
```typescript
class RealtimeDataManager {
  // 连接管理
  connect(url: string): void
  disconnect(): void
  isConnected(): boolean
  
  // 数据订阅
  subscribe(event: string, callback: Function): () => void
  unsubscribe(event: string, callback: Function): void
  
  // 数据请求
  fetchInitialData(): Promise<void>
  
  // 状态
  getConnectionState(): ConnectionState
}
```

**状态机**:
```
DISCONNECTED -> CONNECTING -> CONNECTED
     ↑                          │
     └──────── ERROR ←──────────┘
```

### 5.2 StateManager

**职责**:
- 集中管理应用状态
- 提供响应式数据
- 数据缓存
- 状态持久化

**API**:
```typescript
class StateManager {
  // 状态访问
  getState<T>(key: string): T | undefined
  setState<T>(key: string, value: T): void
  
  // 响应式
  useStore<T>(key: string): Ref<T>
  
  // 缓存
  getCache<T>(key: string): T | undefined
  setCache<T>(key: string, value: T, ttl?: number): void
  
  // 批量更新
  batchUpdate(updates: Record<string, any>): void
}
```

### 5.3 EventDispatcher

**职责**:
- 组件间事件通信
- 事件队列管理
- 错误处理

**API**:
```typescript
class EventDispatcher {
  // 事件分发
  emit(event: string, payload?: any): void
  
  // 事件监听
  on(event: string, handler: Function): () => void
  once(event: string, handler: Function): void
  
  // 事件队列
  enqueue(event: string, payload?: any): void
  flush(): void
}
```

---

## 6. 实时更新方案

### 6.1 WebSocket 协议

**连接**:
```
ws://localhost:8000/ws/dashboard
```

**消息格式**:
```json
{
  "type": "update",
  "channel": "collaboration|tasks|performance",
  "data": { ... },
  "timestamp": 1708969478000
}
```

**事件类型**:
| type | 说明 |
|------|------|
| `update` | 数据更新 |
| `ping` | 心跳请求 |
| `pong` | 心跳响应 |
| `error` | 错误消息 |

### 6.2 HTTP 轮询回退

当 WebSocket 不可用时：
- 使用 `POST /api/poll` 长轮询
- 轮询间隔：5-30 秒（指数退避）
- 超时时间：30 秒

---

## 7. 性能优化

### 7.1 虚拟滚动

**适用场景**:
- 任务列表超过 100 条
- 协作流程节点超过 50 个

**实现**:
- 使用 `IntersectionObserver` 检测可见项
- 仅渲染可视区域 + 缓冲区
- 动态计算 item 高度

### 7.2 数据缓存

**策略**:
- 协作流程数据：5 秒缓存
- 任务状态数据：2 秒缓存
- 性能数据：1 秒缓存

**缓存失效**:
- WebSocket 更新时立即失效
- 手动刷新时失效

### 7.3 防抖节流

**应用场景**:
| 操作 | 策略 | 时间 |
|------|------|------|
| 搜索输入 | 防抖 | 300ms |
| 滚动事件 | 节流 | 100ms |
| 窗口 resize | 防抖 | 200ms |
| 状态更新 | 节流 | 50ms |

---

## 8. 样式设计

### 8.1 设计令牌

```css
:root {
  /* 颜色 */
  --color-primary: #4a9eff;
  --color-success: #22c55e;
  --color-warning: #f59e0b;
  --color-error: #ef4444;
  
  /* 状态颜色 */
  --status-idle: #94a3b8;
  --status-active: #4a9eff;
  --status-completed: #22c55e;
  --status-error: #ef4444;
  
  /* 间距 */
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --spacing-xl: 2rem;
  
  /* 圆角 */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  
  /* 阴影 */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.15);
}
```

### 8.2 响应式断点

```css
/* 移动端 */
@media (max-width: 640px) { }

/* 平板 */
@media (min-width: 641px) and (max-width: 1024px) { }

/* 桌面端 */
@media (min-width: 1025px) { }
```

---

## 9. 错误处理

### 9.1 网络异常

- WebSocket 断开：显示重连状态，自动重连
- HTTP 请求失败：3 次重试，显示错误提示
- 超时：30 秒超时，显示超时提示

### 9.2 数据异常

- 数据为空：显示空状态占位符
- 数据格式错误：降级处理，记录日志
- 数据过大：分页加载，虚拟滚动

### 9.3 权限不足

- 显示权限错误提示
- 提供重试按钮
- 不阻塞其他模块

---

## 10. 集成方案

### 10.1 模块化集成

```
App.vue
├── <CollaborationFlowSection />
├── <TaskStatusSection />
├── <PerformanceSection />
└── [现有组件]
```

### 10.2 保护现有架构

- 新增组件独立封装
- 通过 Provide/Inject 共享数据管理器
- 不修改现有组件内部逻辑
- 样式隔离（scoped CSS）

---

## 11. 文件结构

```
frontend/src/
├── components/
│   ├── collaboration/           # 协作流程
│   │   ├── CollaborationFlowSection.vue
│   │   ├── FlowCanvas.vue
│   │   ├── FlowNode.vue
│   │   └── FlowEdge.vue
│   ├── tasks/                   # 任务状态
│   │   ├── TaskStatusSection.vue
│   │   ├── TaskList.vue
│   │   ├── TaskItem.vue
│   │   └── VirtualList.vue
│   └── performance/             # 性能数据
│       ├── PerformanceSection.vue
│       ├── MetricCards.vue
│       └── TrendChart.vue
├── managers/                    # 数据管理
│   ├── RealtimeDataManager.ts
│   ├── StateManager.ts
│   └── EventDispatcher.ts
├── composables/                 # 组合函数
│   ├── useRealtime.ts
│   ├── useState.ts
│   ├── useDebounce.ts
│   └── useThrottle.ts
├── types/                       # 类型定义
│   ├── collaboration.ts
│   ├── task.ts
│   └── performance.ts
└── styles/                      # 样式
    └── tokens.css
```

---

## 12. 测试策略

### 12.1 单元测试

- 数据管理器测试
- 工具函数测试
- 组件逻辑测试

### 12.2 集成测试

- WebSocket 连接测试
- 数据流测试
- 组件交互测试

### 12.3 E2E 测试

- 完整流程测试
- 响应式布局测试
- 错误场景测试

---

*设计文档完成: 2026-02-26*
