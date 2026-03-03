# 实时执行时序图 - 详细设计文档

**功能名称**: 实时执行时序图 (Realtime Execution Timeline)
**优先级**: P0
**版本**: 1.0
**日期**: 2026-03-03

---

## 一、需求背景

### 1.1 核心痛点

当前 Dashboard 只展示**结果状态**（空闲/工作/异常），无法看到 Agent 内部的执行过程：

| 需要看到的 | 当前状态 |
|-----------|---------|
| 用户输入了什么 | ❌ 看不到 |
| Agent 在思考什么 (thinking) | ❌ 看不到 |
| 调用了哪些工具、参数是什么 | ⚠️ 只显示名称 |
| 工具返回了什么结果 | ⚠️ 简单展示 |
| 每一步的耗时 | ❌ 看不到 |
| 错误发生在哪个环节 | ⚠️ 只有错误消息 |

### 1.2 目标

提供**完整的交互时序视图**，让用户能够：

1. 看到用户与 Agent 的完整对话流程
2. 实时追踪 Agent 的思考过程 (thinking)
3. 清晰展示工具调用的参数和结果
4. 定位错误发生的具体环节
5. 了解每个步骤的耗时和 Token 消耗

---

## 二、数据源分析

### 2.1 Session JSONL 结构

OpenClaw 的 `sessions/*.jsonl` 包含完整的事件流：

```json
// 1. 用户消息
{"type":"message","timestamp":"2026-03-03T10:32:01Z","message":{
  "role":"user",
  "content":[{"type":"text","text":"帮我分析这个项目"}]
}}

// 2. Agent 思考
{"type":"message","timestamp":"2026-03-03T10:32:02Z","message":{
  "role":"assistant",
  "content":[
    {"type":"thinking","thinking":"用户需要项目分析，我需要先读取项目结构..."}
  ]
}}

// 3. 工具调用
{"type":"message","timestamp":"2026-03-03T10:32:03Z","message":{
  "role":"assistant",
  "content":[
    {"type":"toolCall","name":"Glob","id":"call_123","arguments":{"pattern":"**/*.py"}}
  ],
  "usage":{"input":500,"output":50}
}}

// 4. 工具结果
{"type":"message","timestamp":"2026-03-03T10:32:04Z","message":{
  "role":"toolResult",
  "toolName":"Glob",
  "toolCallId":"call_123",
  "details":{"status":"ok"},
  "content":"src/main.py\nsrc/utils.py\n..."
}}

// 5. 后续思考+响应
{"type":"message","timestamp":"2026-03-03T10:32:05Z","message":{
  "role":"assistant",
  "content":[
    {"type":"thinking","thinking":"找到了2个Python文件，我来分析..."},
    {"type":"text","text":"项目包含2个Python文件..."}
  ],
  "usage":{"input":800,"output":200}
}}

// 6. 错误情况
{"type":"message","timestamp":"2026-03-03T10:33:00Z","message":{
  "role":"assistant",
  "stopReason":"error",
  "errorMessage":"429 Rate Limit exceeded",
  "usage":{"input":1200,"output":0}
}}
```

### 2.2 现有后端支持

`session_reader.py:get_session_turns()` 已解析数据，返回格式：

```python
{
  "turnIndex": 0,
  "role": "user" | "assistant" | "toolResult",
  "timestamp": 1709471521000,
  "content": [...],
  "usage": {"input": 500, "output": 50},
  "toolCalls": [{"name": "Glob", "arguments": {...}, "id": "call_123"}],
  "toolName": "Glob",  # 仅 toolResult
  "stopReason": "error" | "end_turn" | null,
  "errorMessage": "..."
}
```

### 2.3 数据增强需求

需要新增以下计算字段：

| 字段 | 计算方式 | 用途 |
|------|----------|------|
| `duration` | 当前 timestamp - 上一条 timestamp | 步骤耗时 |
| `cumulativeTokens` | 累计 usage.input + usage.output | Token 消耗趋势 |
| `stepStatus` | pending/running/success/error | 步骤状态 |
| `parentStepId` | toolCall.id 关联 | 工具调用链路 |

---

## 三、UI 设计

### 3.1 整体布局

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  📊 实时执行时序                                          [🔄 实时] [⚙️]  │
├─────────────────────────────────────────────────────────────────────────────┤
│  Agent: main (PM)                          Model: glm-4.5                   │
│  Session: 4620ba1c...                      开始: 10:32:01                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ 👤 用户  10:32:01                                              +0ms    ││
│  │ ┌─────────────────────────────────────────────────────────────────────┐││
│  │ │ 帮我分析 openclaw-agent-dashboard 项目的代码结构                     │││
│  │ └─────────────────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  │                                                                           │
│  ▼                                                                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ 🤖 Agent  10:32:02                                            +1.2s   🧠││
│  │ ┌─────────────────────────────────────────────────────────────────────┐││
│  │ │ 💭 思考: 用户需要分析项目结构，我应该先查看目录布局...                │││
│  │ │     需要用 Glob 工具找出主要文件类型。                               │││
│  │ └─────────────────────────────────────────────────────────────────────┘││
│  │                                                              tokens: 150 ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  │                                                                           │
│  ▼                                                                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ 🔧 工具调用  10:32:03                                         +0.8s      ││
│  │ ┌─────────────────────────────────────────────────────────────────────┐││
│  │ │ Glob                                                               ▶│││
│  │ │ 参数: { "pattern": "**/*.{py,vue,ts}" }                            │││
│  │ └─────────────────────────────────────────────────────────────────────┘││
│  │                                                              tokens: 80  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  │ ⏳ 执行中...                                                              │
│  ▼                                                                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ ✅ 工具结果  10:32:04                                         +1.5s      ││
│  │ ┌─────────────────────────────────────────────────────────────────────┐││
│  │ │ Glob → 返回 47 个文件                                                │││
│  │ │ src/backend/main.py                                                 │││
│  │ │ src/backend/api/agents.py                                           │││
│  │ │ frontend/src/App.vue                                                │││
│  │ │ ... (展开查看全部)                                                   │││
│  │ └─────────────────────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  │                                                                           │
│  ▼                                                                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ 🤖 Agent  10:32:05                                           +2.1s   🧠││
│  │ ┌─────────────────────────────────────────────────────────────────────┐││
│  │ │ 💭 思考: 项目包含后端(Python)和前端(Vue)，我需要分别读取...         │││
│  │ └─────────────────────────────────────────────────────────────────────┘││
│  │ ┌─────────────────────────────────────────────────────────────────────┐││
│  │ │ 📝 项目结构分析：                                                    │││
│  │ │                                                                     │││
│  │ │ 这是一个 Vue 3 + FastAPI 的全栈项目，包含：                          │││
│  │ │ - 后端: 12 个 Python 文件                                           │││
│  │ │ - 前端: 9 个 Vue/TS 文件                                            │││
│  │ └─────────────────────────────────────────────────────────────────────┘││
│  │                                                              tokens: 450 ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  📊 统计                                                                      │
│  ├─ 总耗时: 5.6s                                                             │
│  ├─ Token: 输入 1,280 / 输出 680 / 总计 1,960                                │
│  ├─ 工具调用: 3 次 (Glob, Read, Read)                                        │
│  └─ 状态: ✅ 成功完成                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 步骤类型与样式

| 步骤类型 | 图标 | 背景色 | 左边框色 | 说明 |
|---------|------|--------|---------|------|
| 用户消息 | 👤 | #f0f9ff | #3b82f6 | 蓝色系 |
| Agent 思考 | 🧠 | #fef3c7 | #f59e0b | 黄色系，可折叠 |
| Agent 文本 | 🤖 | #f0fdf4 | #22c55e | 绿色系 |
| 工具调用 | 🔧 | #f5f3ff | #8b5cf6 | 紫色系，可展开参数 |
| 工具结果-成功 | ✅ | #ecfdf5 | #10b981 | 绿色边框 |
| 工具结果-失败 | ❌ | #fef2f2 | #ef4444 | 红色边框 |
| 错误 | ⚠️ | #fef2f2 | #dc2626 | 红色系，高亮显示 |

### 3.3 交互设计

#### 3.3.1 折叠/展开

```
┌─────────────────────────────────────────────────────┐
│ 🧠 思考 (点击展开)                          +1.2s  ▶│
└─────────────────────────────────────────────────────┘

                    ↓ 点击展开

┌─────────────────────────────────────────────────────┐
│ 🧠 思考                                    +1.2s  ▼│
│ ┌─────────────────────────────────────────────────┐ │
│ │ 用户需要分析项目结构，我应该先查看目录布局...   │ │
│ │ 需要用 Glob 工具找出主要文件类型。              │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

#### 3.3.2 工具调用详情

```
┌─────────────────────────────────────────────────────┐
│ 🔧 Read                                    +0.5s  ▶│
└─────────────────────────────────────────────────────┘

                    ↓ 点击展开

┌─────────────────────────────────────────────────────┐
│ 🔧 Read                                    +0.5s  ▼│
│ ┌─────────────────────────────────────────────────┐ │
│ │ 参数:                                           │ │
│ │ {                                               │ │
│ │   "file_path": "/home/ubuntu/project/main.py"  │ │
│ │ }                                               │ │
│ └─────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────┐ │
│ │ 结果: (342 行)                        [复制]    │ │
│ │ 1→"""                                           │ │
│ │ 2→FastAPI 主入口                                │ │
│ │ 3→...                                           │ │
│ │ [展开全部]                                      │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

#### 3.3.3 错误展示

```
┌─────────────────────────────────────────────────────┐
│ ⚠️ 错误                                    10:33:00 │
│ ┌─────────────────────────────────────────────────┐ │
│ │ ❌ 429 Rate Limit exceeded                      │ │
│ │                                                 │ │
│ │ 错误详情:                                       │ │
│ │ 智谱 API 调用频率超限，请稍后重试或切换模型     │ │
│ │                                                 │ │
│ │ 发生位置:                                       │ │
│ │ 轮次 #12 / 工具调用 Bash(npm run build)        │ │
│ │                                                 │ │
│ │ 建议:                                           │ │
│ │ • 切换到 fallback model glm-4.5                │ │
│ │ • 降低调用频率 (当前 120 TPM)                  │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 3.4 实时更新指示器

```
┌───────────────────────────────────────┐
│ 📊 实时执行时序         [🟢 实时] [⚙️] │
└───────────────────────────────────────┘

状态说明:
🟢 实时 - WebSocket 连接正常，实时接收更新
🟡 重连 - 连接断开，正在重连
🔴 离线 - 连接失败，回退到轮询模式
```

---

## 四、组件设计

### 4.1 组件结构

```
TimelineView.vue                 # 主容器组件
├── TimelineHeader.vue           # 头部信息（Agent、Session、统计）
├── TimelineStep.vue             # 单个步骤组件
│   ├── StepHeader.vue           # 步骤头部（图标、时间、耗时）
│   ├── StepContent.vue          # 步骤内容（可折叠）
│   │   ├── ThinkingBlock.vue    # 思考内容块
│   │   ├── TextBlock.vue        # 文本内容块
│   │   ├── ToolCallBlock.vue    # 工具调用块（参数+结果）
│   │   └── ErrorBlock.vue       # 错误内容块
│   └── StepStats.vue            # 步骤统计（token、状态）
├── TimelineFooter.vue           # 底部统计汇总
└── TimelineConnector.vue        # 步骤间连接线
```

### 4.2 数据流

```
┌──────────────┐    WebSocket     ┌──────────────┐
│   Backend    │ ───────────────▶ │  TimelineView │
│  /api/timeline│                  │              │
└──────────────┘                  └──────────────┘
      │                                  │
      │ 读取 sessions/*.jsonl            │ props
      ▼                                  ▼
┌──────────────┐                  ┌──────────────┐
│ session_     │                  │ TimelineStep │
│ reader.py    │                  │   (多个)     │
└──────────────┘                  └──────────────┘
```

### 4.3 类型定义

```typescript
// types/timeline.ts

/** 时间线步骤类型 */
export type StepType =
  | 'user'           // 用户消息
  | 'thinking'       // Agent 思考
  | 'text'           // Agent 文本响应
  | 'toolCall'       // 工具调用
  | 'toolResult'     // 工具结果
  | 'error'          // 错误

/** 时间线步骤状态 */
export type StepStatus = 'pending' | 'running' | 'success' | 'error'

/** 时间线步骤 */
export interface TimelineStep {
  id: string                    // 唯一标识
  type: StepType                // 步骤类型
  status: StepStatus            // 步骤状态
  timestamp: number             // 时间戳 (ms)
  duration?: number             // 耗时 (ms)

  // 内容
  content?: string              // 文本内容
  thinking?: string             // 思考内容

  // 工具调用
  toolName?: string             // 工具名称
  toolCallId?: string           // 工具调用 ID
  toolArguments?: Record<string, unknown>  // 工具参数
  toolResult?: string           // 工具结果
  toolResultStatus?: 'ok' | 'error'  // 工具结果状态

  // 错误
  errorMessage?: string         // 错误消息
  errorType?: string            // 错误类型

  // 统计
  tokens?: {
    input: number
    output: number
    cumulative: number          // 累计 token
  }

  // 展示控制
  collapsed?: boolean           // 是否折叠
  highlight?: boolean           // 是否高亮
}

/** 时间线会话 */
export interface TimelineSession {
  sessionId: string
  agentId: string
  agentName: string
  model: string
  startedAt: number
  status: 'running' | 'completed' | 'error'

  steps: TimelineStep[]

  // 汇总统计
  stats: {
    totalDuration: number       // 总耗时 (ms)
    totalInputTokens: number
    totalOutputTokens: number
    toolCallCount: number
    stepCount: number
  }
}
```

---

## 五、后端 API 设计

### 5.1 REST API

#### GET /api/timeline/{agent_id}

获取 Agent 当前会话的完整时序数据。

**请求参数**:
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| agent_id | string | 是 | Agent ID |
| session_key | string | 否 | 指定 session，默认最新 |
| limit | int | 否 | 步骤数量限制，默认 100 |

**响应**:
```json
{
  "sessionId": "4620ba1c-4aac-4447-8446-faa2c47cb328",
  "agentId": "main",
  "agentName": "项目经理",
  "model": "glm-4.5",
  "startedAt": 1709471521000,
  "status": "running",
  "steps": [
    {
      "id": "step_0",
      "type": "user",
      "status": "success",
      "timestamp": 1709471521000,
      "duration": 0,
      "content": "帮我分析项目结构"
    },
    {
      "id": "step_1",
      "type": "thinking",
      "status": "success",
      "timestamp": 1709471522000,
      "duration": 1200,
      "thinking": "用户需要分析项目结构...",
      "tokens": { "input": 150, "output": 0, "cumulative": 150 }
    }
  ],
  "stats": {
    "totalDuration": 5600,
    "totalInputTokens": 1280,
    "totalOutputTokens": 680,
    "toolCallCount": 3,
    "stepCount": 8
  }
}
```

### 5.2 WebSocket 事件

#### 连接: ws://host/api/timeline/{agent_id}/ws

**服务端推送事件**:

```typescript
// 新步骤开始
{
  "event": "step_start",
  "data": {
    "stepId": "step_8",
    "type": "toolCall",
    "toolName": "Read",
    "timestamp": 1709471528000
  }
}

// 步骤更新（流式）
{
  "event": "step_update",
  "data": {
    "stepId": "step_8",
    "content": "部分内容...",
    "isDelta": true
  }
}

// 步骤完成
{
  "event": "step_complete",
  "data": {
    "stepId": "step_8",
    "status": "success",
    "duration": 1500,
    "tokens": { "input": 200, "output": 50 }
  }
}

// 错误
{
  "event": "step_error",
  "data": {
    "stepId": "step_8",
    "errorType": "rate-limit",
    "errorMessage": "429 Rate Limit exceeded"
  }
}

// 会话结束
{
  "event": "session_end",
  "data": {
    "status": "completed",
    "stats": { ... }
  }
}
```

---

## 六、实现计划

### 6.1 阶段 1: 基础时序展示（1天）

**后端**:
- [ ] 新增 `/api/timeline/{agent_id}` REST API
- [ ] 扩展 `session_reader.py` 添加 `get_timeline_steps()` 方法
- [ ] 计算耗时、累计 Token 等增强字段

**前端**:
- [ ] 创建 `TimelineView.vue` 主组件
- [ ] 创建 `TimelineStep.vue` 步骤组件
- [ ] 实现折叠/展开交互
- [ ] 集成到 `AgentDetailPanel.vue`

### 6.2 阶段 2: 实时更新（0.5天）

**后端**:
- [ ] 新增 WebSocket 端点 `/api/timeline/{agent_id}/ws`
- [ ] 实现 session 文件监听（watch）
- [ ] 推送 step_start/step_update/step_complete 事件

**前端**:
- [ ] 创建 `useTimelineWebSocket()` composable
- [ ] 实现实时追加步骤
- [ ] 添加连接状态指示器

### 6.3 阶段 3: 增强功能（0.5天）

- [ ] 工具调用参数/结果详情展示
- [ ] 错误根因分析和建议
- [ ] Token 消耗趋势图
- [ ] 步骤搜索/过滤
- [ ] 导出时序报告

---

## 七、文件清单

### 7.1 后端新增文件

```
src/backend/
├── api/
│   └── timeline.py              # 时序 API 路由
├── data/
│   └── timeline_reader.py       # 时序数据解析（扩展 session_reader）
└── main.py                      # 注册 timeline 路由
```

### 7.2 前端新增文件

```
frontend/src/
├── components/
│   └── timeline/
│       ├── TimelineView.vue         # 主容器
│       ├── TimelineHeader.vue       # 头部
│       ├── TimelineStep.vue         # 步骤组件
│       ├── TimelineFooter.vue       # 底部统计
│       ├── TimelineConnector.vue    # 连接线
│       └── blocks/
│           ├── ThinkingBlock.vue    # 思考块
│           ├── TextBlock.vue        # 文本块
│           ├── ToolCallBlock.vue    # 工具调用块
│           └── ErrorBlock.vue       # 错误块
├── composables/
│   └── useTimeline.ts           # 时序数据管理
└── types/
    └── timeline.ts              # 类型定义
```

---

## 八、验收标准

### 8.1 功能验收

- [ ] 能完整展示用户与 Agent 的交互时序
- [ ] 能展示 Agent 的思考过程 (thinking)
- [ ] 能展示工具调用的参数和结果
- [ ] 能清晰标识错误发生的环节
- [ ] 支持折叠/展开长内容
- [ ] WebSocket 实时更新正常

### 8.2 性能验收

- [ ] 100 步骤内渲染时间 < 500ms
- [ ] 实时更新延迟 < 200ms
- [ ] 内存占用 < 50MB

### 8.3 兼容性

- [ ] 不影响现有 Dashboard 功能
- [ ] 支持 Chrome/Firefox/Safari 最新版

---

## 九、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Session 文件过大导致解析慢 | 用户体验差 | 分页加载 + 虚拟滚动 |
| WebSocket 断连 | 实时性下降 | 自动重连 + 回退轮询 |
| Thinking 内容过长 | 页面臃肿 | 默认折叠 + 截断展示 |

---

*设计文档版本: 1.0*
*创建时间: 2026-03-03*
