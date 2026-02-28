# OpenClaw Agent 循环与完成回传机制

**文档目的**：说明 OpenClaw 的 Agent 循环是什么、子任务完成回传的流程，以及 Dashboard 中「完成回传」标识的含义。  
**目标读者**：使用 OpenClaw 多 Agent 协作的开发者、看板使用者  
**版本**：1.0  
**日期**：2026-02-27  

---

## 一、Agent 循环是什么

### 1.1 定义

**Agent 循环**是 OpenClaw 内部负责「对话 → 模型推理 → 工具执行 → 写回结果 → 继续推理」的完整执行链路。它把用户消息或工具结果转化为模型的下一步动作和回复，并保持 session 状态一致。

### 1.2 核心组件

| 组件 | 作用 |
|------|------|
| **Gateway RPC** | `agent`、`agent.wait`：接收请求，启动一次 Agent 运行 |
| **runEmbeddedPiAgent** | 主执行逻辑（`src/agents/pi-embedded-runner/`） |
| **pi-agent-core** | Pi SDK 的 Agent 循环：LLM 调用、工具执行、消息类型 |
| **SessionManager** | 读写 session（`.jsonl`），维护对话历史 |

### 1.3 循环逻辑

```
1. 读取 session 最新消息（user / assistant / toolResult）
2. 构建 prompt，调用 LLM
3. 若 LLM 返回 toolCall → 执行工具 → 得到 toolResult → 写入 session
4. 若 session 末尾是 toolResult → 回到步骤 1，继续调用 LLM 处理
5. 若 LLM 返回普通文本且无 toolCall → 结束本轮
```

**关键**：当 session 末尾是 toolResult 时，循环会**自动继续**调用 LLM，无需外部触发。

---

## 二、子任务完成回传流程

### 2.1 标准工具调用循环

```
用户消息
    ↓
Main LLM 输出 toolCall（如 sessions_spawn）
    ↓
OpenClaw 执行工具（创建子 Agent、运行任务）
    ↓
子 Agent 完成，生成 toolResult
    ↓
【OpenClaw 运行时】将 toolResult 写入 Main 的 session
    ↓
【Agent 循环】检测到新 toolResult → 自动调用 Main LLM
    ↓
Main LLM 处理 toolResult，生成下一步回复
```

### 2.2 谁触发的

| 步骤 | 触发方 | 说明 |
|-----|--------|------|
| **子任务完成，生成 toolResult** | OpenClaw 运行时 | 子 Agent 会话结束时，OpenClaw 检测到完成，将结果封装为 toolResult，写入主 Agent 的 session |
| **Main LLM 再次被调用** | OpenClaw 的 Agent 循环 | 发现 session 末尾有新的 toolResult，按标准工具调用流程自动继续，调用 Main 的 LLM 处理该结果 |

整个过程由 OpenClaw 内部的 Agent 循环驱动，用户无需额外操作。

### 2.3 为什么 Main 还要再调一次 GLM？

- OpenClaw 把子任务结果作为 **toolResult** 注入到 Main 的对话中。
- 在标准 Agent 设计中，工具返回后需要再次调用 LLM，让模型「看到」结果并决定下一步。
- Main 再次调用 GLM 用于：
  - 理解子任务结果
  - 决定是总结给用户、继续派发新任务，还是做其他操作

---

## 三、Dashboard 中的「完成回传」标识

### 3.1 时间戳含义

在协作流程和性能监控中，当某次模型调用的**触发**显示为「完成回传」时：

- **时间戳**：表示**子任务完成后的回传时间**，不是派发时间。
- **因果顺序**：派发 → 子 Agent 执行 → 完成回传。

### 3.2 显示示例

| 时间 | Agent | 含义 |
|------|-------|------|
| 21:14:39 | main | Main 对用户回复，包含 sessions_spawn 的 toolCall（派发） |
| 21:14:52 | analyst-agent | 分析师开始执行任务 |
| 21:14:57 | main | **完成回传**：Main 收到 toolResult 后的 LLM 调用，处理子任务完成结果 |

### 3.3 为何需要标识

若不做区分，21:14:57 的 main 调用容易被误读为「派发时间」。实际上这是**完成回传**时间，因果顺序是正确的：先派发（21:14:39），再执行（21:14:52），最后回传（21:14:57）。

---

## 四、参考

- OpenClaw 官方文档：`docs/concepts/agent-loop.md`
- sessions_spawn 工具说明：`docs/concepts/session-tool.md`
- Pi SDK：`pi-agent-core` 负责 Agent 循环与工具执行
