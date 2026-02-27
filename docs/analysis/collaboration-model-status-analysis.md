# 协作流程模型状态动态显示需求分析

## 1. 当前实现分析

### 1.1 现有功能概述

当前协作流程（`CollaborationFlowSection.vue`）已经实现了：

1. **Agent 节点展示**：显示各 Agent 的基本信息（名称、状态）
2. **模型配置展示**：在 Agent 卡片中显示 primary 和 fallbacks 模型（静态配置）
3. **模型调用光球**：右侧模型节点显示最近的调用记录（`recentCalls`）
4. **拓扑关系**：Agent 与模型之间的边连接

### 1.2 数据来源

**后端接口** (`/api/collaboration`)：
- `agentModels`: 从 `openclaw.json` 读取每个 Agent 的模型配置
  ```typescript
  {
    primary: string        // 主模型
    fallbacks: string[]    // 备用模型列表
  }
  ```

- `recentCalls`: 从 session 日志解析最近 30 分钟的模型调用
  ```typescript
  {
    id: string
    agentId: string
    model: string          // 实际使用的模型（如 "zhipu/glm-4.7"）
    sessionId: string
    trigger: string
    tokens: number
    timestamp: number      // Unix 毫秒时间戳
    time: string           // 格式化时间 "HH:MM:SS"
  }
  ```

### 1.3 存在的问题

1. **静态配置信息**：只显示配置文件中的 primary/fallbacks，不反映实际运行状态
2. **无模型状态指示**：无法知道当前正在使用哪个模型（primary 还是 fallback）
3. **无错误状态展示**：不显示 429、timeout、auth 失败等错误
4. **无冷却/禁用状态**：不显示模型是否在冷却期或因 billing 被禁用
5. **无切换历史**：无法追踪模型切换事件
6. **无 Auth Profile 信息**：不显示当前使用的 API Key/OAuth profile

---

## 2. 需求详细拆解

### 2.1 核心需求

#### 需求 1：模型状态显示

**目标**：实时显示每个 Agent 当前使用的模型及其状态

**具体要求**：
- 显示当前使用的模型（primary/fallback 中的哪个）
- 显示模型状态：
  - ✅ **正常** (healthy)：正常工作
  - ⚠️ **错误** (error)：遇到错误（429、timeout、auth 失败）
  - 🔄 **冷却** (cooldown)：在冷却期，暂时不可用
  - 🔴 **禁用** (disabled)：因 billing/限额被禁用
- 状态应基于最近的调用和错误信息判断

**UI 位置**：Agent 卡片中，模型信息下方添加状态指示器

---

#### 需求 2：模型切换历史

**目标**：记录和展示模型切换事件

**具体要求**：
- 记录每次模型切换事件
- 显示切换时间
- 显示切换原因（429、timeout、auth 失败、用户手动切换等）
- 显示从哪个模型切换到哪个模型
- 按时间倒序排列，最近的事件在最上面

**UI 位置**：
- 可以在 Agent 详情面板中展示
- 或在 Agent 卡片中添加一个小图标，点击展开切换历史

---

#### 需求 3：Auth Profile 状态

**目标**：显示每个 Agent 使用的 API Key/OAuth profile

**具体要求**：
- 如果有多个 API Key/OAuth profile，显示当前使用的是哪个
- 显示其他 profile 的状态（正常/错误）
- 显示 profile 限流信息（如果有）

**UI 位置**：Agent 详情面板中

---

#### 需求 4：实时更新

**目标**：模型状态和切换事件实时推送

**具体要求**：
- 模型状态变化实时反映到 UI
- 切换事件实时推送
- 通过 WebSocket 更新，避免频繁轮询

---

## 3. 数据来源分析

### 3.1 Session 日志分析

Session 日志（`.jsonl` 文件）包含以下关键事件：

#### 3.1.1 模型切换事件 (`model_change`)

```json
{
  "type": "model_change",
  "id": "589ed7e9",
  "parentId": null,
  "timestamp": "2026-02-27T01:12:17.470Z",
  "provider": "zhipu",
  "modelId": "glm-4.7"
}
```

**用途**：记录模型切换事件，包含时间戳、provider、modelId

---

#### 3.1.2 模型快照 (`model-snapshot`)

```json
{
  "type": "custom",
  "customType": "model-snapshot",
  "data": {
    "timestamp": 1772154737483,
    "provider": "zhipu",
    "modelApi": "openai-completions",
    "modelId": "glm-4.7"
  },
  "id": "93b1bbf0",
  "parentId": "6cdbd401",
  "timestamp": "2026-02-27T01:12:17.483Z"
}
```

**用途**：记录每次调用时使用的模型，可以用于追踪实际使用的模型

---

#### 3.1.3 消息中的模型信息

```json
{
  "type": "message",
  "id": "cb254a63",
  "timestamp": "2026-02-27T01:12:20.191Z",
  "message": {
    "role": "assistant",
    "api": "openai-completions",
    "provider": "zhipu",
    "model": "glm-4.7",
    "usage": {
      "input": 6005,
      "output": 251,
      "cacheRead": 6863,
      "cacheWrite": 0,
      "totalTokens": 13119
    },
    "stopReason": "stop"
  }
}
```

**用途**：
- `provider` + `model`：实际使用的模型
- `usage.totalTokens`：token 消耗
- `stopReason`：停止原因，可能包含错误信息

---

#### 3.1.4 错误信息

错误信息可能出现在：
1. **消息中的错误**：`stopReason`、`usage` 中的错误信息
2. **toolResult 中的错误**：工具调用失败
3. **自定义日志**：如 `model-failures.log`

**示例错误类型**：
- HTTP 429：Rate limit exceeded
- Timeout：请求超时
- Auth failed：认证失败

---

### 3.2 配置文件分析

#### 3.2.1 Agent 模型配置 (`openclaw.json`)

```json
{
  "agents": {
    "list": [
      {
        "id": "main",
        "name": "老 K (Project Manager)",
        "model": {
          "primary": "zhipu/glm-4.5",
          "fallbacks": ["zhipu/glm-4.7", "zhipu/glm-5"]
        }
      }
    ]
  }
}
```

**用途**：获取每个 Agent 的 primary 和 fallbacks 模型

---

#### 3.2.2 Auth Profiles (`openclaw.json`)

```json
{
  "auth": {
    "profiles": {
      "zhipu:default": {
        "provider": "zhipu",
        "mode": "api_key"
      },
      "qwen-portal:default": {
        "provider": "qwen-portal",
        "mode": "oauth"
      }
    }
  }
}
```

**用途**：获取可用的 Auth profiles，但目前没有显示哪个 profile 在使用中

---

### 3.3 数据提取策略

#### 3.3.1 当前使用的模型

**方法 1**：从最近的 `message` 中提取 `provider` 和 `model`
- 扫描每个 Agent 的 session 文件
- 找到最后一条 `role === 'assistant'` 的消息
- 提取 `provider` 和 `model`

**方法 2**：从最近的 `model-snapshot` 中提取
- 扫描 `customType === 'model-snapshot'` 的事件
- 找到最后一条
- 提取 `data.provider` 和 `data.modelId`

**推荐**：方法 1（消息中的信息更准确）

---

#### 3.3.2 模型错误信息

**方法 1**：从 `model-snapshot` 推断
- `model_change` 事件通常发生在错误之后
- 对比 `model-snapshot` 序列，可以检测到模型切换

**方法 2**：解析消息中的 `stopReason`
- 如果 `stopReason` 包含错误信息，则记录错误
- 例如：`stopReason: "rate_limit_exceeded"`

**方法 3**：解析 `model-failures.log`（已实现）
- `error_detector.py` 已经解析了失败日志
- 可以复用这个逻辑

**推荐**：方法 3（已实现，直接复用）

---

#### 3.3.3 模型切换历史

**方法**：
1. 扫描 session 文件，提取所有 `model_change` 事件
2. 提取 `timestamp`、`provider`、`modelId`
3. 按时间倒序排列
4. 对于每次切换，尝试推断原因：
   - 查看切换之前的消息是否有错误
   - 如果有 429 错误，原因 = "rate_limit"
   - 如果有 timeout 错误，原因 = "timeout"
   - 否则，原因 = "manual"（用户手动切换）

---

#### 3.3.4 模型状态计算

**状态定义**：
- ✅ **healthy**：最近一次调用成功，且没有错误
- ⚠️ **error**：最近一次调用失败（429、timeout、auth 失败）
- 🔄 **cooldown**：模型在冷却期（暂无直接数据源，需推断）
- 🔴 **disabled**：因 billing/限额被禁用（暂无直接数据源）

**计算逻辑**：
```
如果最近一次调用成功 → healthy
如果最近一次调用失败 → error
如果切换到 fallback 且最近没有调用 primary → cooldown（推断）
如果多次 429 错误 → disabled（推断）
```

**注意**：cooldown 和 disabled 状态需要更多数据支持，当前版本可以先基于错误信息实现

---

## 4. 数据结构设计

### 4.1 ModelStatus（模型状态）

```typescript
interface ModelStatus {
  modelId: string              // 模型 ID（如 "zhipu/glm-4.7"）
  provider: string             // Provider（如 "zhipu"）
  status: 'healthy' | 'error' | 'cooldown' | 'disabled'
  lastUsedAt?: number          // 最后使用时间（Unix 毫秒）
  lastError?: ModelError       // 最后一次错误信息
  cooldownUntil?: number       // 冷却结束时间（Unix 毫秒）
}
```

```typescript
interface ModelError {
  type: 'rate_limit' | 'timeout' | 'auth_failed' | 'unknown'
  message: string             // 错误消息
  timestamp: number           // 错误时间（Unix 毫秒）
  code?: number               // HTTP 状态码（如 429）
}
```

---

### 4.2 AgentModelStatus（Agent 模型状态）

```typescript
interface AgentModelStatus {
  agentId: string
  agentName: string

  // 配置信息
  config: {
    primary: string           // 配置的 primary 模型
    fallbacks: string[]       // 配置的 fallbacks 模型
  }

  // 当前状态
  currentModel: ModelStatus   // 当前使用的模型
  allModels: ModelStatus[]   // 所有模型的状态（primary + fallbacks）

  // 切换历史
  switchHistory: ModelSwitchEvent[]

  // Auth Profile（可选）
  authProfile?: AuthProfile
}
```

---

### 4.3 ModelSwitchEvent（模型切换事件）

```typescript
interface ModelSwitchEvent {
  id: string                  // 事件 ID（可以由时间戳生成）
  agentId: string             // Agent ID
  fromModel?: string          // 切换前的模型（第一次可能为空）
  toModel: string             // 切换后的模型
  reason: SwitchReason        // 切换原因
  timestamp: number           // 切换时间（Unix 毫秒）
  time: string               // 格式化时间（如 "09:12:17"）
}

type SwitchReason =
  | 'rate_limit'             // 429 错误
  | 'timeout'                // 超时
  | 'auth_failed'            // 认证失败
  | 'manual'                 // 用户手动切换
  | 'cooldown_end'           // 冷却期结束，切回 primary
  | 'unknown'                // 未知原因
```

---

### 4.4 AuthProfile（Auth Profile）

```typescript
interface AuthProfile {
  profileId: string           // Profile ID（如 "zhipu:default"）
  provider: string            // Provider（如 "zhipu"）
  mode: 'api_key' | 'oauth'  // 认证模式
  status: 'active' | 'error'  // 状态
  lastError?: AuthError       // 最后一次错误
}

interface AuthError {
  type: 'rate_limit' | 'auth_failed' | 'unknown'
  message: string
  timestamp: number
}
```

---

## 5. API 接口设计

### 5.1 新增后端 API

#### 5.1.1 获取 Agent 模型状态

**端点**：`GET /api/agents/{agentId}/model-status`

**响应**：
```typescript
{
  agentId: string
  agentName: string
  config: {
    primary: string
    fallbacks: string[]
  }
  currentModel: ModelStatus
  allModels: ModelStatus[]
  switchHistory: ModelSwitchEvent[]
  authProfile?: AuthProfile
}
```

**实现要点**：
1. 从 `openclaw.json` 读取配置
2. 扫描 session 文件，提取当前使用的模型
3. 从 `model-failures.log` 或 session 日志提取错误信息
4. 扫描 `model_change` 事件，构建切换历史
5. 计算模型状态

---

#### 5.1.2 获取所有 Agent 的模型状态

**端点**：`GET /api/agents/model-statuses`

**响应**：
```typescript
{
  agents: AgentModelStatus[]
  lastUpdate: number          // 最后更新时间（Unix 毫秒）
}
```

**用途**：一次性获取所有 Agent 的模型状态，减少前端请求

---

#### 5.1.3 获取 Agent 模型切换历史

**端点**：`GET /api/agents/{agentId}/model-switches?limit=20`

**查询参数**：
- `limit`：返回数量限制（默认 20）

**响应**：
```typescript
{
  agentId: string
  agentName: string
  switches: ModelSwitchEvent[]
  total: number              // 总切换次数
}
```

---

### 5.2 WebSocket 消息扩展

#### 5.2.1 模型状态更新

```typescript
{
  type: 'model_status_update'
  data: {
    agentId: string
    modelStatus: ModelStatus
    timestamp: number
  }
}
```

**触发条件**：
- Agent 使用了新模型（检测到 `model_change` 事件）
- 模型状态变化（healthy ↔ error）

**实现要点**：
- 需要在 session 日志解析时检测变化
- 或定时轮询 session 日志

---

#### 5.2.2 模型切换事件

```typescript
{
  type: 'model_switch_event'
  data: {
    agentId: string
    switchEvent: ModelSwitchEvent
    timestamp: number
  }
}
```

**触发条件**：
- 检测到 `model_change` 事件

---

#### 5.2.3 模型错误事件

```typescript
{
  type: 'model_error'
  data: {
    agentId: string
    modelId: string
    error: ModelError
    timestamp: number
  }
}
```

**触发条件**：
- 检测到模型调用错误（429、timeout、auth 失败）

---

## 6. UI 组件设计

### 6.1 Agent 卡片扩展

#### 6.1.1 当前模型信息

**位置**：在 Agent 卡片底部，model-info 区域下方

**布局**：
```
┌─────────────────────────────────┐
│ 👨‍💼 老 K (Project Manager)     │
│ ● 空闲                         │
│ 任务: 无                        │
│ 活跃: 5 分钟前                  │
│                                │
│ [模型信息]                      │
│   glm-5 → glm-4.7, glm-4.6      │
│                                │
│ [新增] 模型状态                 │
│   ✅ 当前: glm-5 (正常)         │
│   最近调用: 3 分钟前           │
│                                │
│ [新增] 切换历史 (3次) ▼         │
└─────────────────────────────────┘
```

**实现**：
- 在 `AgentCard.vue` 中添加 `modelStatus` prop
- 显示状态图标（✅/⚠️/🔄/🔴）
- 点击"切换历史"可展开/折叠历史列表

---

#### 6.1.2 模型切换历史列表

**位置**：在 Agent 卡片下方，点击"切换历史"后展开

**布局**：
```
[切换历史 (3次)]
┌─────────────────────────────────────┐
│ glm-5 → glm-4.7                   │
│ 原因: rate_limit (429)             │
│ 时间: 09:45:35                     │
├─────────────────────────────────────┤
│ glm-5 → glm-4.7                   │
│ 原因: rate_limit (429)             │
│ 时间: 09:06:54                     │
├─────────────────────────────────────┤
│ glm-4.7 → glm-5                   │
│ 原因: manual                      │
│ 时间: 08:54:30                     │
└─────────────────────────────────────┘
```

**颜色编码**：
- **rate_limit**：橙色 ⚠️
- **timeout**：红色 🔴
- **auth_failed**：红色 🔴
- **manual**：蓝色 🔵
- **cooldown_end**：绿色 ✅

---

### 6.2 Agent 详情面板扩展

#### 6.2.1 模型状态 Tab

**位置**：在 `AgentDetailPanel.vue` 中添加新 Tab

**内容**：
1. **当前模型**：显示所有模型的状态（primary + fallbacks）
2. **切换历史**：完整的切换历史列表
3. **错误详情**：显示最近的错误信息
4. **Auth Profile**：显示当前使用的 profile

**布局**：
```
┌─────────────────────────────────────────┐
│ [详情] [任务] [模型状态] [配置]        │
├─────────────────────────────────────────┤
│ 当前模型状态                           │
│ ┌───────────────────────────────────┐  │
│ │ ✅ glm-5 (primary)               │  │
│ │    状态: healthy                 │  │
│ │    最后使用: 3 分钟前            │  │
│ ├───────────────────────────────────┤  │
│ │ ⚠️ glm-4.7 (fallback #1)        │  │
│ │    状态: error (rate_limit)      │  │
│ │    最后错误: 10 分钟前           │  │
│ ├───────────────────────────────────┤  │
│ │ ✅ glm-4.6 (fallback #2)        │  │
│ │    状态: healthy                 │  │
│ │    最后使用: 2 小时前            │  │
│ └───────────────────────────────────┘  │
│                                         │
│ 切换历史                               │
│ [完整列表...]                          │
│                                         │
│ Auth Profile                           │
│ ┌───────────────────────────────────┐  │
│ │ zhipu:default (active)          │  │
│ │ qwen-portal:default (error)     │  │
│ └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

---

### 6.3 状态指示器组件

创建 `ModelStatusIndicator.vue` 组件，用于显示模型状态：

**Props**：
```typescript
interface Props {
  status: 'healthy' | 'error' | 'cooldown' | 'disabled'
  modelId: string
  lastUsedAt?: number
  lastError?: ModelError
}
```

**样式**：
- **healthy**：绿色 ✅，浅绿色背景
- **error**：橙色 ⚠️，浅橙色背景
- **cooldown**：蓝色 🔄，浅蓝色背景
- **disabled**：红色 🔴，浅红色背景

---

## 7. 实现建议

### 7.1 实现优先级

#### Phase 1：基础状态显示（高优先级）

**目标**：显示当前使用的模型和基本状态

**任务**：
1. 实现后端 API：
   - `GET /api/agents/{agentId}/model-status`
   - 实现数据解析逻辑（session 日志 → ModelStatus）
2. 扩展 AgentCard：
   - 添加 `modelStatus` prop
   - 显示当前模型和状态
   - 添加状态指示器组件

**预估工作量**：2-3 小时

---

#### Phase 2：切换历史（中优先级）

**目标**：显示模型切换历史

**任务**：
1. 实现后端 API：
   - `GET /api/agents/{agentId}/model-switches`
   - 解析 `model_change` 事件
   - 推断切换原因
2. 扩展 UI：
   - 在 AgentCard 中添加切换历史展开/折叠
   - 创建切换历史列表组件

**预估工作量**：3-4 小时

---

#### Phase 3：实时更新（中优先级）

**目标**：通过 WebSocket 实时推送模型状态变化

**任务**：
1. 扩展 WebSocket：
   - 添加 `model_status_update` 消息
   - 添加 `model_switch_event` 消息
   - 添加 `model_error` 消息
2. 实现状态监听：
   - 定时扫描 session 日志（或使用文件监听）
   - 检测模型切换和错误
3. 前端订阅：
   - 在 `useWebSocket` 中添加模型状态订阅
   - 更新本地状态

**预估工作量**：4-5 小时

---

#### Phase 4：Auth Profile 和高级状态（低优先级）

**目标**：显示 Auth Profile 和高级状态（cooldown/disabled）

**任务**：
1. 扩展后端 API：
   - 添加 Auth Profile 状态
   - 实现 cooldown 和 disabled 状态推断
2. 扩展 UI：
   - 在 AgentDetailPanel 中显示 Auth Profile
   - 实现高级状态显示

**预估工作量**：2-3 小时

---

### 7.2 技术要点

#### 7.2.1 Session 日志解析

**性能考虑**：
- Session 文件可能很大，不要全量读取
- 只读取最近的日志（如最近 1 小时）
- 使用 `tail -n` 或从文件末尾读取
- 缓存解析结果，避免重复读取

**实现示例**：
```python
def parse_last_n_lines(session_path: Path, n: int = 1000) -> List[Dict]:
    """从文件末尾读取最后 N 行"""
    lines = []
    with open(session_path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell()
        while len(lines) < n and pos > 0:
            f.seek(pos)
            char = f.read(1)
            pos -= 1
            if char == b'\n':
                line = f.readline().decode('utf-8').strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except:
                        pass
    return lines[::-1]  # 反转，按时间顺序
```

---

#### 7.2.2 模型状态计算

**实现示例**：
```python
def calculate_model_status(agent_id: str, model_id: str) -> ModelStatus:
    # 1. 获取最后一次调用
    last_call = get_last_successful_call(agent_id, model_id)

    # 2. 获取最后一次错误
    last_error = get_last_error(agent_id, model_id)

    # 3. 计算状态
    if last_error and last_error['timestamp'] > (last_call['timestamp'] if last_call else 0):
        # 有错误且错误比最后调用更近 → error
        status = 'error'
    elif last_call:
        # 有成功调用 → healthy
        status = 'healthy'
    else:
        # 没有任何记录 → unknown（可以视为 healthy）
        status = 'healthy'

    return ModelStatus(
        modelId=model_id,
        provider=model_id.split('/')[0],
        status=status,
        lastUsedAt=last_call['timestamp'] if last_call else None,
        lastError=last_error if status == 'error' else None
    )
```

---

#### 7.2.3 WebSocket 实时更新

**实现策略**：
- 方案 1：定时轮询 session 日志（简单，但有延迟）
- 方案 2：使用文件监听（如 `watchdog` 库）
- 方案 3：OpenClaw 内部推送（需要修改 OpenClaw 代码，不推荐）

**推荐**：方案 1（定时轮询，每 5-10 秒扫描一次）

**实现示例**：
```python
async def monitor_model_changes():
    """定时扫描 session 日志，检测模型变化"""
    last_models = {}  # agentId -> last model

    while True:
        for agent_id in get_all_agents():
            last_model = get_last_used_model(agent_id)

            # 检测模型切换
            if agent_id in last_models and last_models[agent_id] != last_model:
                # 模型切换，推送 WebSocket 消息
                await broadcast_model_switch(agent_id, last_models[agent_id], last_model)

            last_models[agent_id] = last_model

        await asyncio.sleep(10)  # 每 10 秒扫描一次
```

---

#### 7.2.4 前端数据管理

**推荐使用 Vue 的响应式状态管理**：

```typescript
// composables/useModelStatus.ts
export function useModelStatus(agentId: string) {
  const modelStatus = ref<AgentModelStatus | null>(null)
  const loading = ref(false)

  const fetchModelStatus = async () => {
    loading.value = true
    try {
      const res = await fetch(`/api/agents/${agentId}/model-status`)
      modelStatus.value = await res.json()
    } finally {
      loading.value = false
    }
  }

  // WebSocket 订阅
  const { onMessage } = useWebSocket()
  onMessage('model_status_update', (data) => {
    if (data.agentId === agentId) {
      modelStatus.value = { ...modelStatus.value, currentModel: data.modelStatus }
    }
  })

  return { modelStatus, loading, fetchModelStatus }
}
```

---

### 7.3 性能考虑

1. **Session 日志读取**：
   - 只读取必要的行（如最后 1000 行）
   - 使用缓存，避免重复读取
   - 并行处理多个 Agent 的日志

2. **WebSocket 推送**：
   - 只推送变化的数据，不要推送整个状态
   - 使用防抖（debounce）避免频繁推送

3. **前端渲染**：
   - 虚拟滚动处理大量切换历史
   - 使用 `v-memo` 优化渲染性能

---

### 7.4 错误处理

1. **Session 文件不存在**：返回空状态
2. **日志解析失败**：忽略错误行，继续解析
3. **WebSocket 连接失败**：降级到轮询
4. **数据不一致**：以 session 日志为准（配置可能过期）

---

## 8. 数据流向图

```
┌─────────────────┐
│ openclaw.json   │ (配置: primary/fallbacks)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Session 日志 (.jsonl)          │
│ - model_change                 │
│ - model-snapshot               │
│ - message (provider/model)     │
│ - error info                   │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 后端解析器                      │
│ - extract_current_model()       │
│ - extract_switch_events()       │
│ - extract_errors()             │
│ - calculate_status()           │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ API 响应                        │
│ AgentModelStatus                │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ WebSocket 推送                  │
│ - model_status_update          │
│ - model_switch_event           │
│ - model_error                  │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ 前端组件                        │
│ - AgentCard                     │
│ - AgentDetailPanel              │
│ - ModelStatusIndicator          │
└─────────────────────────────────┘
```

---

## 9. 核心发现总结

### 9.1 数据可用性

| 数据类型 | 数据源 | 可用性 | 备注 |
|---------|--------|--------|------|
| Agent 配置 (primary/fallbacks) | openclaw.json | ✅ 完全可用 | 当前已实现 |
| 当前使用的模型 | Session 日志 (message.model-snapshot) | ✅ 完全可用 | 需解析最后一条消息 |
| 模型切换事件 | Session 日志 (model_change) | ✅ 完全可用 | 需解析时间序列 |
| 错误信息 | Session 日志 (stopReason) + model-failures.log | ✅ 部分可用 | model-failures.log 已解析 |
| Auth Profile | openclaw.json (auth.profiles) | ⚠️ 部分可用 | 没有当前使用信息 |
| Cooldown 状态 | ❌ 无直接数据源 | ❌ 不可用 | 需推断 |
| Disabled 状态 | ❌ 无直接数据源 | ❌ 不可用 | 需推断 |

### 9.2 技术挑战

1. **Cooldown/Disabled 状态**：
   - 没有直接的数据源
   - 需要从错误频率推断
   - 当前版本可以先跳过

2. **实时更新延迟**：
   - Session 日志是追加写入的
   - 检测变化需要轮询或文件监听
   - 预计延迟 5-10 秒

3. **Auth Profile 当前使用**：
   - Session 日志中没有记录使用哪个 profile
   - 暂时无法显示

4. **Session 日志性能**：
   - 文件可能很大
   - 需要优化读取策略

### 9.3 实现建议

1. **优先实现基础功能**：
   - 显示当前使用的模型
   - 显示基本状态（healthy/error）
   - 显示切换历史

2. **实时更新可以先使用轮询**：
   - 每 10 秒扫描一次 session 日志
   - 后续可以优化为文件监听

3. **Cooldown/Disabled 状态暂时跳过**：
   - 需要更多数据支持
   - 可以作为后续增强功能

4. **Auth Profile 可以先显示配置**：
   - 显示可用的 profiles
   - 暂时不显示当前使用

---

## 10. 附录

### 10.1 相关文件列表

**后端**：
- `/src/backend/api/collaboration.py` - 协作流程 API
- `/src/backend/api/performance.py` - 性能统计（已有 session 解析逻辑）
- `/src/backend/data/config_reader.py` - 配置读取
- `/src/backend/status/error_detector.py` - 错误检测
- `/src/backend/api/websocket.py` - WebSocket

**前端**：
- `/frontend/src/components/collaboration/CollaborationFlowSection.vue`
- `/frontend/src/components/AgentCard.vue`
- `/frontend/src/types/collaboration.ts`
- `/frontend/src/composables/useWebSocket.ts`

**数据源**：
- `~/.openclaw/openclaw.json` - 配置文件
- `~/.openclaw/agents/{agentId}/sessions/*.jsonl` - Session 日志
- `~/.openclaw/workspace-main/memory/model-failures.log` - 错误日志

### 10.2 术语表

| 术语 | 解释 |
|-----|------|
| Primary Model | Agent 的主模型，优先使用 |
| Fallback Model | 备用模型，当 primary 失败时切换 |
| Model Switch | 模型切换事件 |
| Cooldown | 冷却期，模型暂时不可用 |
| Rate Limit | 请求频率限制（HTTP 429） |
| Auth Profile | API Key 或 OAuth 认证配置 |
| Session 日志 | Agent 的运行日志，记录所有事件和消息 |

---

**文档版本**：v1.0
**创建日期**：2026-02-27
**作者**：analyst-agent subagent
