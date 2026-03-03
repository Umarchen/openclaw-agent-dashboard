# OpenClaw Agent Dashboard 可视化能力分析报告

**分析日期**: 2026-03-03
**项目路径**: `/home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard`

---

## 一、当前实现概况

### 1.1 项目技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite |
| 后端 | Python FastAPI |
| 数据源 | OpenClaw 文件系统（runs.json、sessions/*.jsonl、openclaw.json） |

### 1.2 已实现的功能模块

| 模块 | 文件 | 功能描述 |
|------|------|----------|
| 协作流程 | `CollaborationFlowWrapper.vue` | 主 Agent + 子 Agent 拓扑图 |
| 任务状态 | `TaskStatusSection.vue` | 任务列表、过滤、详情弹窗 |
| Agent 详情 | `AgentDetailPanel.vue` | 状态、会话轮次、工具调用 |
| API 状态 | `ApiStatusCard.vue` | Provider/Model 状态 |
| 性能监控 | `PerformanceSection.vue` | 性能数据展示 |
| Token 分析 | `TokenAnalysisPanel.vue` | Token 使用统计 |
| 错误中心 | `ErrorCenterPanel.vue` | 错误聚合展示 |

---

## 二、核心问题：可视化能力不足以支撑多 Agent 调教

### 2.1 核心痛点：**看不到"内部流程"**

当前实现只展示**结果状态**，而非**执行过程**。以下是具体差距：

| 你需要的 | 当前实现 | 差距 |
|----------|----------|------|
| **实时执行流程** | 只有状态灯（空闲/工作/异常） | 看不到 Agent 正在执行什么步骤 |
| **决策过程** | 只展示最终输出 | 看不到 Agent 的 thinking、reasoning |
| **工具调用链** | 只列出工具名称 | 看不到调用参数、执行结果、耗时 |
| **任务派发关系** | 只有任务列表 | 看不到 Main→SubAgent 的派发链路 |
| **错误根因** | 只显示错误消息 | 看不到是哪个环节、哪个工具调用失败 |

### 2.2 具体问题分解

#### 问题 1：缺乏**执行时序视图**

```
当前展示：
  [analyst-agent] 🟡 工作中 - 任务: 编写PRD...

你需要的：
  [analyst-agent]
    10:32:01 📥 收到任务: 编写PRD
    10:32:02 🧠 思考: 分析需求...
    10:32:05 🔧 调用 Read(project_spec.md)
    10:32:06 ✅ 返回 342 行
    10:32:07 🧠 思考: 需要提取模块...
    10:32:10 ✏️ 调用 Write(prd.md)
    10:32:12 ✅ 完成
```

#### 问题 2：缺乏**Agent 协作链路追踪**

```
当前展示：
  Main Agent → analyst-agent → architect-agent → devops-agent
  （只是静态拓扑图）

你需要的：
  任务 #123 执行链路：
  Main (派发) → analyst-agent (PRD完成) → architect-agent (设计完成)
       → devops-agent (开发中 🔄) → Main (等待审核)

  点击任一节点可看到：
  - 输入是什么
  - 输出是什么
  - 耗时多久
  - 调用了哪些工具
```

#### 问题 3：缺乏**配置调优入口**

当前 Dashboard 是**只读**的，无法：
- 查看 Agent 当前使用的 model、prompt
- 查看 fallback 链配置
- 热调整配置后重新测试

#### 问题 4：错误追踪不够深入

`AgentDetailPanel.vue` 只展示：
```javascript
turn-error: {{ agent.error.message }}
```

你需要的是：
```
错误发生在：
  - 会话: agent:devops-agent:subagent:xxx
  - 轮次: #12
  - 工具调用: Bash(npm test)
  - 错误: 429 Rate Limit
  - 前序调用: Write(src/main.ts) ✅
  - 建议: 降低调用频率或切换 fallback model
```

---

## 三、数据源分析：其实数据都在，只是没展示

OpenClaw 的 `sessions/*.jsonl` 已经包含丰富的执行信息：

```json
{"type":"message","message":{
  "role":"assistant",
  "content": [
    {"type":"thinking","thinking":"我需要先读取项目规范..."},
    {"type":"toolCall","name":"Read","arguments":{"file_path":"/path/to/spec.md"}}
  ],
  "usage":{"input":1200,"output":350}
}}
{"type":"message","message":{
  "role":"toolResult",
  "toolName":"Read",
  "details":{"status":"ok"},
  "content":"文件内容..."
}}
```

**问题**：后端 `session_reader.py:get_session_turns()` 已经解析了这些数据，但前端只做了**简单展示**，没有做**时序可视化**。

---

## 四、改进建议

### 4.1 新增：**实时执行时序图**（优先级 P0）

```
┌─────────────────────────────────────────────────────────────────┐
│  [analyst-agent] 实时执行                                        │
├─────────────────────────────────────────────────────────────────┤
│  10:32:01 📥 收到任务: 编写PRD                                   │
│  10:32:02 🧠 思考: 分析需求范围...                               │
│  10:32:05 📖 Read(project_spec.md) → 342行                      │
│  10:32:07 🧠 思考: 提取核心模块...                               │
│  10:32:10 ✏️ Write(prd.md) → 完成                               │
│  10:32:12 ✅ 任务完成                                            │
├─────────────────────────────────────────────────────────────────┤
│  Token 消耗: input=1200, output=350                             │
│  耗时: 11秒                                                      │
└─────────────────────────────────────────────────────────────────┘
```

**实现要点**：
- 扩展 `GET /api/agents/:id/output` 返回完整时序
- 新增 `TimelineView.vue` 组件
- 支持 SSE/WebSocket 实时推送

### 4.2 新增：**任务执行链路图**（优先级 P0）

```
任务 #123: 开发用户登录功能
┌────────┐    ┌─────────┐    ┌───────────┐    ┌──────────────┐
│ Main   │───▶│ Analyst │───▶│ Architect │───▶│ DevOps       │
│ 派发   │    │ PRD✅    │    │ 设计✅     │    │ 开发中 🔄    │
│ 10:30  │    │ 10:35   │    │ 10:42     │    │ 10:50        │
└────────┘    └─────────┘    └───────────┘    └──────────────┘
```

**实现要点**：
- 解析 `runs.json` 中的 `requesterSessionKey` → `childSessionKey` 链路
- 新增 `TaskChainView.vue` 组件

### 4.3 增强：**Agent 配置面板**（优先级 P1）

点击 Agent 工位后，除了状态，还要展示：

```
┌─────────────────────────────────────────┐
│ [analyst-agent] 配置                    │
├─────────────────────────────────────────┤
│ 主模型: glm-4.7                         │
│ Fallback: glm-4.5 → glm-4              │
│ System Prompt:                          │
│   "你是一个资深需求分析师..."            │
│                                         │
│ 最近调用统计:                           │
│   成功: 45 | 失败: 2 | 降级: 3          │
│   平均耗时: 12.3秒                      │
│                                         │
│ [查看完整配置] [编辑]                    │
└─────────────────────────────────────────┘
```

### 4.4 增强：**错误根因分析**（优先级 P1）

当任务失败时：

```
❌ 任务失败: devops-agent #456

失败环节: 工具调用 Bash(npm run build)
错误类型: 429 Rate Limit
发生时间: 10:52:34

前序执行:
  10:52:01 ✅ Write(src/auth.ts)
  10:52:15 ✅ Write(tests/auth.test.ts)
  10:52:20 ✅ Bash(npm install)
  10:52:34 ❌ Bash(npm run build) ← 失败

建议:
  - 切换到 fallback model glm-4.5
  - 或降低调用频率（当前 120 TPM）
```

---

## 五、优先级排序

| 优先级 | 功能 | 工作量 | 价值 |
|--------|------|--------|------|
| **P0** | 实时执行时序图 | 2天 | 直接看到内部流程 |
| **P0** | 任务执行链路图 | 1天 | 看到环节状态和依赖 |
| **P1** | 错误根因分析 | 1天 | 快速定位问题 |
| **P1** | Agent 配置面板 | 1天 | 支撑调优决策 |
| **P2** | 配置热更新 | 2天 | 闭环调优流程 |

---

## 六、总结

当前 Dashboard 实现了**基础监控能力**（状态、任务列表、API 状态），但缺乏**深度可观测性**：

| 维度 | 现状 | 目标 |
|------|------|------|
| 状态展示 | ✅ 有 | ✅ 有 |
| 执行过程 | ❌ 无 | 需要时序图 |
| 协作链路 | ⚠️ 静态拓扑 | 需要动态链路 |
| 错误追踪 | ⚠️ 只有消息 | 需要根因分析 |
| 配置调优 | ❌ 只读 | 需要可编辑 |

**核心建议**：优先实现「实时执行时序图」和「任务执行链路图」，这两个功能能让你直接看到 Agent 内部在做什么、处于哪个环节。

---

## 七、下一步行动

1. **详细设计「实时执行时序图」** - 展示 Agent 执行的每一步（思考、工具调用、返回结果）
2. **详细设计「任务执行链路图」** - 展示 Main → Analyst → Architect → DevOps 的派发关系和各环节状态
3. **详细设计「Agent 配置面板」** - 展示 model、prompt、fallback 配置，支撑调优决策
4. **直接开始实现** - 从最紧迫的功能开始编码

---

*报告生成时间: 2026-03-03*
