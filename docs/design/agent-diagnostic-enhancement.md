# Agent 诊断能力增强方案

## 问题背景

当前分析师 Agent 在 19:39:28 执行 `exec` 工具后返回 "(no output)"，然后卡住 17+ 分钟无响应。Dashboard 无法帮助用户：
1. 知道 Agent 卡在哪里
2. 判断是 API 问题还是内部错误
3. 决定是否需要手动干预

## 现状分析

### Dashboard 当前能获取的信息

| 数据源 | 信息 | 可用性 |
|--------|------|--------|
| `runs.json` | runId, status, startedAt, endedAt, outcome | ✅ 可用 |
| `sessions/*.jsonl` | 完整的对话历史、工具调用、token 使用 | ✅ 可用 |
| `sessions.json` | session 元数据、最后活跃时间 | ✅ 可用 |

### Dashboard 当前无法获取的信息

| 信息 | 原因 | 影响 |
|------|------|------|
| API 请求状态 | OpenClaw 内部状态，未暴露 | 无法知道是否在等待 API |
| 内部队列状态 | OpenClaw 内部状态，未暴露 | 无法知道是否有阻塞 |
| 详细错误堆栈 | 通常只有简单的 error message | 难以定位根本原因 |

## 解决方案

### Phase 1: 基于现有数据的诊断增强 (无需修改 OpenClaw)

#### 1.1 卡顿检测与警告

```typescript
// 在 AgentDetailPanel 中添加
const STUCK_THRESHOLD_MS = 5 * 60 * 1000; // 5 分钟

function detectStuckAgent(agent: Agent): StuckInfo | null {
  if (agent.status !== 'working') return null;

  const lastActive = agent.lastActive;
  const idleTime = Date.now() - lastActive;

  if (idleTime > STUCK_THRESHOLD_MS) {
    return {
      isStuck: true,
      idleMinutes: Math.floor(idleTime / 60000),
      severity: idleTime > 15 * 60 * 1000 ? 'critical' : 'warning'
    };
  }
  return null;
}
```

#### 1.2 最后操作详情展示

在时序视图中，对最后一个步骤进行特殊标注：

```vue
<div class="last-step-indicator" v-if="isLastStep(step)">
  <span class="waiting-badge">⏳ 等待中...</span>
  <span class="wait-time">已等待 {{ formatDuration(waitTime) }}</span>
</div>
```

#### 1.3 超时倒计时

```typescript
// 从 runs.json 获取 archiveAtMs
function getTimeToTimeout(run: SubagentRun): number {
  if (!run.archiveAtMs) return Infinity;
  return Math.max(0, run.archiveAtMs - Date.now());
}
```

#### 1.4 工具结果详情

对于返回 "(no output)" 或空结果的工具调用，显示更多信息：

```vue
<div class="tool-result-detail">
  <div class="result-status" :class="resultStatus">
    {{ resultStatus === 'empty' ? '⚠️ 无输出' : '✅ 完成' }}
  </div>
  <div class="result-hint" v-if="resultStatus === 'empty'">
    命令执行成功但没有产生输出，可能是：
    <ul>
      <li>命令本身不产生输出</li>
      <li>输出被重定向到文件</li>
      <li>执行路径有问题</li>
    </ul>
  </div>
</div>
```

### Phase 2: OpenClaw 源码增强 (需要修改 OpenClaw)

#### 2.1 新增诊断 API 端点

在 OpenClaw gateway 中添加：

```typescript
// src/gateway/server-diagnostic.ts
export async function handleDiagnosticRequest(
  req: Request,
  res: Response,
  agentId: string
) {
  const diagnostic = {
    // API 调用状态
    pendingApiCalls: getPendingApiCalls(agentId),

    // 内部队列
    messageQueue: getMessageQueueStatus(agentId),

    // 最后错误详情
    lastError: getLastErrorDetails(agentId),

    // 资源使用
    resources: {
      memoryUsage: process.memoryUsage(),
      activeConnections: getActiveConnections(agentId)
    }
  };

  return res.json(diagnostic);
}
```

#### 2.2 Session 文件增强

在 session jsonl 中添加诊断信息：

```json
{
  "type": "diagnostic",
  "timestamp": "2026-03-03T11:45:00.000Z",
  "data": {
    "apiCallStarted": "2026-03-03T11:39:30.000Z",
    "apiCallStatus": "pending",
    "apiEndpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "retryCount": 0
  }
}
```

#### 2.3 超时和错误追踪

```typescript
// 在 subagent-registry.types.ts 中添加
export type SubagentRunRecord = {
  // ... 现有字段

  // 新增诊断字段
  diagnostic?: {
    lastApiCallAt?: number;
    pendingApiCall?: {
      startedAt: number;
      endpoint: string;
      model: string;
    };
    lastError?: {
      timestamp: number;
      type: string;
      message: string;
      stack?: string;
    };
    stallDetectedAt?: number;
  };
};
```

## 实施计划

### Phase 1 (Dashboard 侧，无需修改 OpenClaw)

| 任务 | 预估时间 | 优先级 |
|------|----------|--------|
| 添加卡顿检测组件 | 2h | P0 |
| 增强最后操作展示 | 2h | P0 |
| 添加超时倒计时 | 1h | P1 |
| 工具结果详情展示 | 2h | P1 |

### Phase 2 (OpenClaw 源码修改)

| 任务 | 预估时间 | 优先级 |
|------|----------|--------|
| 设计诊断 API | 2h | P2 |
| 实现诊断数据收集 | 4h | P2 |
| 添加 session 诊断记录 | 3h | P2 |
| 测试和文档 | 2h | P2 |

## 当前分析师问题的诊断

基于现有数据，分析师 Agent 的状态：

```
时间线:
19:27:16 - Run 创建
19:39:16 - Run 开始执行
19:39:28 - 最后一条消息: exec 工具返回 "(no output)"
19:56:xx - 当前时间 (卡住 ~17 分钟)

状态判断:
- lastActive = 19:39:28 (17 分钟前)
- status = running
- endedAt = undefined (未结束)
- cleanupHandled = false

结论: Agent 在等待 LLM API 响应，可能是：
1. API 超时 (GLM-5 有时响应慢)
2. 网络问题
3. API 配额/限流

建议操作:
1. 等待到 20:27:16 (自动归档)
2. 或手动取消: openclaw subagents cancel cd1f907e-xxx
```

## 设计稿

### 诊断面板 UI

```
┌─────────────────────────────────────────────────────────────┐
│ 分析师 Agent                              [⚠️ 卡顿警告]      │
├─────────────────────────────────────────────────────────────┤
│ 状态: 🔄 运行中 (已等待 17 分钟)                              │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ⚠️ 异常检测                                              │ │
│ │                                                         │ │
│ │ • 最后活跃: 19:39:28 (17 分钟前)                         │ │
│ │ • 最后操作: exec → "(no output)"                        │ │
│ │ • 预计超时: 20:27:16 (剩余 30 分钟)                      │ │
│ │                                                         │ │
│ │ 可能原因:                                                │ │
│ │ • LLM API 响应超时                                       │ │
│ │ • 网络连接问题                                           │ │
│ │ • API 配额限制                                           │ │
│ │                                                         │ │
│ │ [取消任务]  [查看日志]  [刷新状态]                        │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ 时序视图:                                                   │
│ ┌─────┐   ┌─────┐   ┌─────┐   ┌─────────┐                 │
│ │用户 │──▶│思考 │──▶│exec │──▶│⏳等待中 │                 │
│ └─────┘   └─────┘   └─────┘   └─────────┘                 │
│                               ↑                             │
│                        已等待 17 分钟                        │
└─────────────────────────────────────────────────────────────┘
```
