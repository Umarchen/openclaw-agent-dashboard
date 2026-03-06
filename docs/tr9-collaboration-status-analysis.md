# 协作流程状态显示问题分析

> TR9: 综合分析 Agent 状态更新与显示策略

## 问题概述

用户反馈的核心问题：

1. **Agent 工作内容更新不及时**：显示的都是"思考中"，不会实时反映当前动作
2. **任务完成后状态刷新不及时**：任务已完成，但仍显示"工作中"
3. **模型调用小球匹配错误**：各 Agent 使用不同模型，调用后小球应落入对应模型框中，但目前存在 bug

---

## 第一部分：技术根因分析

### 1.1 为什么"思考中"无法准确显示

#### 技术现实

Agent 的思考、工具执行通常非常快（几百毫秒到几秒），而 Dashboard 通过读取文件来获取状态存在不可避免的延迟：

```
Agent 执行动作 ──► 写入 JSONL 文件 ──► Dashboard 读取 ──► 前端显示
    │                  │                    │               │
    │                  │                    │               │
   <1s              I/O 延迟            轮询间隔          渲染延迟
                    (10-100ms)          (3s)             (ms)
```

**结论**：等 Dashboard 读取到文件时，Agent 可能已经完成了思考/执行动作。

#### 当前代码的问题

**文件**: `src/backend/status/status_calculator.py:165-172`

```python
# 检查是否有 thinking 块
if has_thinking_block(agent_id):
    return {
        'status': 'working',
        'subStatus': 'thinking',
        'currentAction': '思考中...',
        ...
    }
```

**文件**: `src/backend/data/session_reader.py:333-344`

```python
def has_thinking_block(agent_id: str) -> bool:
    """检查最近消息是否有 thinking 块"""
    messages = get_recent_messages(agent_id, limit=5)
    for msg in reversed(messages):
        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'thinking':
                    return True  # 只要存在就返回 True，不管是什么时候的
    return False
```

**问题**：
- 只要历史消息中有 `thinking` 块，就一直返回 True
- 没有判断这个 thinking 是 1 秒前还是 1 分钟前的
- 模型响应中的 thinking 块会长期保留

### 1.2 为什么任务完成后状态不及时刷新

#### 状态判断流程

```
calculate_agent_status(agent_id)
    │
    ├─► has_recent_errors() ──► 是 ──► 'down'
    │
    ├─► is_agent_working() ──► 是 ──► 'working'
    │       │
    │       └─► 检查 runs.json 中是否有 endedAt=null 的记录
    │           匹配条件：childSessionKey 或 requesterSessionKey 包含 agent:{agent_id}:
    │
    ├─► has_recent_session_activity() ──► 是 ──► 'working'
    │       │
    │       └─► 检查 sessions.json 的 updatedAt 是否在 2 分钟内
    │           即使任务完成，2 分钟内仍显示工作中
    │
    └─► 默认 ──► 'idle'
```

#### 关键代码位置

**文件**: `src/backend/data/subagent_reader.py:61-75`

```python
def is_agent_working(agent_id: str) -> bool:
    """
    判断 Agent 是否在工作中
    - 作为执行者：childSessionKey 包含 agent:{agent_id}:
    - 作为派发者：requesterSessionKey 包含 agent:{agent_id}:（主 Agent 等待子 Agent 完成）
    """
    active_runs = get_active_runs()  # 获取 endedAt is None 的 runs
    for run in active_runs:
        child_key = run.get('childSessionKey', '')
        requester_key = run.get('requesterSessionKey', '')
        # 作为执行者：子 Agent 正在执行任务
        if f'agent:{agent_id}:' in child_key:
            return True
        # 作为派发者：主 Agent 等待子 Agent 完成
        if f'agent:{agent_id}:' in requester_key:
            return True
    return False
```

**问题**：
- 完全依赖 OpenClaw 框架写入 `endedAt` 的时间
- 如果 OpenClaw 进程异常，`endedAt` 可能永远不会写入

**文件**: `src/backend/status/status_calculator.py:38-39`

```python
if has_recent_session_activity(agent_id, minutes=2):
    return 'working'  # 2 分钟内的 session 活动都认为在工作
```

**问题**：
- 2 分钟的安全窗口导致状态延迟
- 这是为了容错设计的，但影响了实时性

### 1.3 数据流延迟分析

```
┌─────────────────────────────────────────────────────────────────────┐
│                         延迟来源                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. OpenClaw 写入延迟                                               │
│     └─ Agent 完成动作 ──► 写入 runs.json/sessions.json              │
│        延迟: 100ms ~ 数秒（取决于 OpenClaw 实现）                     │
│                                                                     │
│  2. Dashboard 读取延迟                                               │
│     └─ 文件系统 I/O: 10-100ms                                       │
│                                                                     │
│  3. 轮询间隔                                                         │
│     └─ WebSocket 周期广播: 3s                                        │
│     └─ 前端 dynamic 轮询: 3s                                         │
│                                                                     │
│  4. 判断逻辑延迟                                                     │
│     └─ session 活跃窗口: 2 分钟                                      │
│                                                                     │
│  总延迟: 最坏情况 = OpenClaw延迟 + 3s + 3s + 2分钟 ≈ 2分6秒          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 第二部分：模型调用小球匹配问题分析

### 2.1 问题描述

协作流程右侧显示模型面板，每个模型卡片中应显示对应 Agent 的调用小球（颜色代表不同 Agent）。用户反馈：各 Agent 使用不同模型，但调用小球没有正确落入对应的模型框中。

### 2.2 数据流分析

```
┌─────────────────────────────────────────────────────────────────────┐
│                     模型调用数据流                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Agent 配置 (agents.yaml)                                        │
│     └─ main-agent: primary=anthropic/claude-sonnet-4.6             │
│     └─ dev-agent:   primary=anthropic/claude-sonnet-4.6            │
│     └─ test-agent:  primary=openai/gpt-4                           │
│                                                                     │
│  2. 模型节点创建 (collaboration.py)                                  │
│     └─ 从配置中提取所有模型 ID                                       │
│     └─ 创建节点: id="model-anthropic-claude-sonnet-4.6"            │
│     └─           metadata.modelId="anthropic/claude-sonnet-4.6"    │
│                                                                     │
│  3. 调用记录 (session.jsonl)                                        │
│     └─ 解析 assistant 消息中的 model 字段                           │
│     └─ 格式可能是: "claude-sonnet-4.6" 或 "anthropic/claude-sonnet" │
│                                                                     │
│  4. 前端匹配 (CollaborationFlowSection.vue)                         │
│     └─ 用 metadata.modelId 或 short name 匹配                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.3 关键代码分析

#### 后端：模型节点创建

**文件**: `src/backend/api/collaboration.py:379-389`

```python
# 3. 模型节点（右侧）
for i, model_id in enumerate(models_list):
    model_node = CollaborationNode(
        id=f"model-{model_id.replace('/', '-')}",  # ID: model-anthropic-claude-sonnet-4.6
        type="model",
        name=get_model_display_name(model_id),
        status="idle",
        timestamp=None,
        metadata={"modelId": model_id}  # 完整格式: anthropic/claude-sonnet-4.6
    )
    nodes.append(model_node)
```

#### 后端：调用记录获取

**文件**: `src/backend/api/performance.py:126`

```python
model = msg.get('model', '')  # 直接从 session 消息中读取 model 字段
```

**文件**: `src/backend/api/collaboration.py:255-262`

```python
records.append({
    'agentId': agent_id,
    'model': r.get('model', ''),  # model 格式取决于 session 文件中存储的值
    'sessionId': r['sessionId'],
    ...
})
```

#### 前端：匹配逻辑

**文件**: `frontend/src/components/collaboration/CollaborationFlowSection.vue:392-406`

```typescript
// 按模型分组调用记录
const callsPerModel = computed(() => {
  const map: Record<string, ModelCall[]> = {}
  for (const c of recentCalls.value) {
    const mid = c.model || '(unknown)'  // key 就是 session 中的 model 值
    if (!map[mid]) map[mid] = []
    map[mid].push(c)
  }
  return map
})

// 获取某个模型节点的调用记录
function getCallsForModelNode(node: CollaborationNode): ModelCall[] {
  const modelId = (node.metadata as { modelId?: string })?.modelId || ''  // 如: anthropic/claude-sonnet-4.6
  const short = modelId.split('/').pop() || modelId  // 如: claude-sonnet-4.6
  return callsPerModel.value[modelId] || callsPerModel.value[short] || []
}
```

### 2.4 问题根因

#### 格式不一致问题

| 来源 | 格式示例 | 说明 |
|------|----------|------|
| Agent 配置 | `anthropic/claude-sonnet-4.6` | provider/model 格式 |
| 模型节点 modelId | `anthropic/claude-sonnet-4.6` | 同配置 |
| Session 消息 model | `claude-sonnet-4.6` 或 `claude-sonnet-4.6-20250514` | 可能不含 provider，可能有版本号 |

**匹配失败场景**：

```
模型节点 modelId: anthropic/claude-sonnet-4.6
                    │
                    ▼
              前端尝试匹配
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
  "anthropic/   "claude-    都不匹配
   claude-       sonnet-
   sonnet-4.6"   4.6"
                    │
                    ▼
           Session 中的实际值
           可能是: "claude-sonnet-4.6-20250514"
```

#### 具体问题点

1. **Session 中 model 字段格式不确定**
   - OpenClaw 框架写入的 model 字段可能是简短名（如 `claude-sonnet-4.6`）
   - 也可能是带版本号的（如 `claude-sonnet-4.6-20250514`）
   - 不一定包含 provider 前缀

2. **前端匹配逻辑过于简单**
   - 只尝试精确匹配和 short name 匹配
   - 没有处理版本号后缀的情况
   - 没有模糊匹配逻辑

3. **缺少日志和调试信息**
   - 无法知道实际收到的 model 值是什么
   - 难以排查匹配失败的原因

### 2.5 解决方案

#### 方案 A：后端统一格式（推荐）

在获取调用记录时，将 model 字段统一为标准格式：

**文件**: `src/backend/api/collaboration.py` 修改 `_get_recent_model_calls`

```python
import re

def _normalize_model_id(model_from_session: str, known_models: List[str]) -> str:
    """
    将 session 中的 model 值规范化为标准格式

    Args:
        model_from_session: session 中的 model 值，如 "claude-sonnet-4.6"
        known_models: 配置中已知的模型列表，如 ["anthropic/claude-sonnet-4.6", "openai/gpt-4"]

    Returns:
        标准化的模型 ID，如 "anthropic/claude-sonnet-4.6"

    注意:
        - 原始实现使用 split('-20')[0] 存在边界问题：
          * claude-sonnet-4-20250514 中 "-4" 会被错误截断
          * gpt-4-turbo-2024-04-09 中 "-20" 不在末尾，匹配失败
        - 改用正则表达式精确匹配 -20YYMMDD 格式的日期后缀
    """
    if not model_from_session:
        return '(unknown)'

    # 已经是标准格式
    if '/' in model_from_session:
        return model_from_session

    # 使用正则去除 -20YYMMDD 格式的日期后缀（更稳健）
    # 例如: claude-sonnet-4.6-20250514 -> claude-sonnet-4.6
    base_name = re.sub(r'-20\d{6}$', '', model_from_session)

    for known in known_models:
        known_short = known.split('/')[-1]
        # 精确匹配 short name
        if known_short == model_from_session:
            return known
        # 匹配去除版本号后的名称
        if known_short.startswith(base_name):
            return known

    return model_from_session


def _get_recent_model_calls(minutes: int = 30) -> List[Dict]:
    """获取最近 N 分钟的模型调用记录（用于光球展示）

    注意:
        - since 为 timezone-aware datetime (UTC)
        - parse_session_file_with_details 返回的 r['timestamp'] 也必须是 timezone-aware
        - 如果 timestamp 为 naive datetime，与 aware datetime 比较会抛出 TypeError
    """
    from datetime import datetime, timezone, timedelta
    from api.performance import parse_session_file_with_details
    from data.config_reader import get_all_models_from_agents

    # 获取已知模型列表用于匹配
    known_models = get_all_models_from_agents()

    # 确保 since 是 UTC timezone-aware
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=minutes)

    records = []
    # ... 现有代码 ...

    for r in parse_session_file_with_details(session_file, agent_id):
        ts = r['timestamp']
        # 确保 timestamp 是 timezone-aware，naive 的统一视为 UTC
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        if ts >= since:
            # 规范化 model 字段
            normalized_model = _normalize_model_id(r.get('model', ''), known_models)

            records.append({
                'agentId': agent_id,
                'model': normalized_model,  # 使用规范化后的值
                ...
            })
    # ...
```

#### 方案 B：前端增强匹配

**文件**: `frontend/src/components/collaboration/CollaborationFlowSection.vue`

```typescript
function getCallsForModelNode(node: CollaborationNode): ModelCall[] {
  const modelId = (node.metadata as { modelId?: string })?.modelId || ''
  const short = modelId.split('/').pop() || modelId

  // 尝试多种匹配方式
  const candidates = [
    modelId,                    // anthropic/claude-sonnet-4.6
    short,                      // claude-sonnet-4.6
    short.split('-20')[0],      // claude-sonnet-4.6 (去除版本号)
  ]

  for (const candidate of candidates) {
    // 精确匹配
    if (callsPerModel.value[candidate]) {
      return callsPerModel.value[candidate]
    }
    // 前缀匹配
    for (const key of Object.keys(callsPerModel.value)) {
      if (key.startsWith(candidate) || candidate.startsWith(key)) {
        return callsPerModel.value[key]
      }
    }
  }

  return []
}
```

### 2.6 调试建议

添加日志以确认实际问题（生产环境使用 logging 模块）：

```python
import logging
logger = logging.getLogger(__name__)

# 在 _get_recent_model_calls 中添加
logger.debug(f"Session model: {r.get('model')}, Known models: {known_models}")
```

```typescript
// 在前端添加（仅开发环境）
if (import.meta.env.DEV) {
  console.log('[DEBUG] Model node:', modelId, 'Calls keys:', Object.keys(callsPerModel.value))
}
```

### 2.7 性能考虑

`_get_recent_model_calls` 会遍历所有 agent 的 sessions 目录下 `*.jsonl`，在 session 较多时可能较慢。

**优化建议**：

1. **优先使用 sessions.json 索引**
   - 只解析 `sessions.json` 中 `updatedAt` 在时间范围内的 session
   - 避免扫描所有 `*.jsonl` 文件

2. **限制文件数量和大小**
   ```python
   # 只处理最近 N 个 session 文件
   session_files = sorted(sessions_path.glob('*.jsonl'),
                         key=lambda x: x.stat().st_mtime,
                         reverse=True)[:10]

   # 限制单个文件读取大小
   MAX_FILE_SIZE = 1024 * 1024  # 1MB
   if session_file.stat().st_size > MAX_FILE_SIZE:
       continue
   ```

3. **缓存已知模型映射**
   ```python
   # 模块级缓存，避免重复读取配置
   _model_mapping_cache: Optional[Dict[str, str]] = None

   def _get_model_mapping() -> Dict[str, str]:
       global _model_mapping_cache
       if _model_mapping_cache is None:
           _model_mapping_cache = _build_model_mapping()
       return _model_mapping_cache
   ```

---

## 第三部分：用户真正关心的是什么？

### 3.1 无价值的显示

| 状态 | 问题 |
|------|------|
| "思考中..." | 持续时间短（<1s），无法准确判断 |
| "执行: Read" | 快速工具（<100ms），显示即过时 |
| "执行: Grep" | 同上 |

### 3.2 有价值的场景

**用户核心问题：卡住了吗？卡在哪里？**

| 场景 | 持续时间 | 价值 | 判断依据 |
|------|----------|------|----------|
| 等待模型响应 | 5s ~ 60s+ | 高 | 模型慢/网络问题/限流 |
| 等待子代理完成 | 10s ~ 数分钟 | 高 | 子代理任务进度 |
| Bash 长命令 | 3s ~ 数分钟 | 高 | 命令卡住/资源阻塞 |
| 大文件读写 | 2s ~ 30s | 中 | 文件操作进度 |
| 快速执行 | <2s | 低 | 不需要显示 |

### 3.3 状态显示原则

1. **不追求精确**：快速动作无法精确捕获，不如不显示
2. **关注异常**：只显示超过阈值的"卡顿"状态
3. **提供上下文**：显示等待对象、持续时间
4. **减少闪烁**：用"处理中..."作为过渡状态

---

## 第四部分：解决方案

### 4.1 基于时间阈值的状态显示

**核心思路：只有超过阈值才显示具体动作**

```
                    时间轴
    ─────────────────────────────────────────────►

    工具开始      阈值(2s)       工具结束
       │            │              │
       ▼            ▼              ▼
    ┌──────┐    ┌──────┐      ┌──────┐
    │ 处理中│───►│ 显示  │─────►│ 完成 │
    │ ...  │    │ 具体状态│      │      │
    └──────┘    └──────┘      └──────┘
```

### 4.2 建议的阈值

| 状态类型 | 阈值 | 显示内容 |
|----------|------|----------|
| 等待模型响应 | 5s | "等待响应 ⏱Xs" |
| 等待模型（可能限流） | 15s | "等待响应 (可能限流) ⏱Xs" ⚠️ |
| 等待子代理 | 3s | "等待 [agent名] ⏱Xs" |
| Bash 命令 | 2s | "执行命令 ⏱Xs" |
| 文件操作 | 2s | "读写文件 ⏱Xs" |
| 其他工具 | 3s | "执行工具 ⏱Xs" |
| 快速执行中 | - | "处理中..." |

### 4.3 简化后的状态体系

```
┌─────────────────────────────────────────────────────────────────┐
│                      Agent 状态显示                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐                                                │
│  │ 空闲        │  无活跃任务                                    │
│  └─────────────┘                                                │
│         │                                                       │
│         ▼ 有任务开始                                            │
│  ┌─────────────┐                                                │
│  │ 处理中...   │  任务刚开始，或快速执行中                       │
│  └─────────────┘                                                │
│         │                                                       │
│         ├───────────────────────────────────┐                   │
│         │ 超过阈值                         │                   │
│         ▼                                   ▼                   │
│  ┌─────────────┐                     ┌─────────────┐           │
│  │ 等待响应    │ >5s                 │ 执行命令    │ >2s       │
│  │ 等待子代理  │ >3s                 │ 读写文件    │ >2s       │
│  └─────────────┘                     └─────────────┘           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 前端显示效果

```
┌────────────────────────────────────────────┐
│ 🤖 frontend-agent                    [PM] │
├────────────────────────────────────────────┤
│ 模型  claude-sonnet-4.6                     │
├────────────────────────────────────────────┤
│ ▶ 当前任务                                  │
│   实现用户登录页面组件...                    │
├────────────────────────────────────────────┤
│ ⚡ 等待 dev-agent              ⏱ 45s       │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ 🤖 dev-agent                               │
├────────────────────────────────────────────┤
│ ⚙️ 执行命令                    ⏱ 12s       │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ 🤖 test-agent                              │
├────────────────────────────────────────────┤
│ 🟢 空闲                                     │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ 🤖 analyst-agent                           │
├────────────────────────────────────────────┤
│ 🔄 处理中...                                │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ 🤖 backend-agent                           │
├────────────────────────────────────────────┤
│ ⚠️ 等待响应 (可能限流)         ⏱ 23s       │
└────────────────────────────────────────────┘
```

---

## 第五部分：实现建议

### 5.1 关键数据源分析

#### timestamp 来源问题

**重要**：`get_recent_messages()` 只返回 `message` 对象，不包含 `data.timestamp`。

**文件**: `src/backend/data/session_reader.py:68-88`

```python
def get_recent_messages(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    # ...
    for line in raw_lines:
        # ...
        if data.get('type') == 'message':
            messages.append(data.get('message', {}))  # 只返回 message，不含 data.timestamp
            # ...
    return messages
```

**影响**：
- 无法通过 `msg.get('timestamp')` 获取消息时间戳
- 需要新增接口或修改现有接口返回时间戳信息

### 5.2 后端修改

#### 文件: `src/backend/data/session_reader.py`

**方案 A**：新增返回带时间戳的消息接口

```python
def get_recent_messages_with_timestamp(agent_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    获取最近的会话消息（包含时间戳）

    Returns:
        [{'message': {...}, 'timestamp': int, 'data_timestamp': int}, ...]
    """
    session_file = get_latest_session_file(agent_id)
    if not session_file:
        return []
    raw_lines = _read_tail_lines(session_file, max(limit * 5, 500))
    messages = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if data.get('type') == 'message':
                messages.append({
                    'message': data.get('message', {}),
                    'timestamp': data.get('message', {}).get('timestamp', 0),
                    'data_timestamp': data.get('timestamp', ''),  # ISO 格式
                })
                if len(messages) >= limit:
                    break
        except json.JSONDecodeError:
            continue
    return messages[-limit:]


def get_last_activity_time(agent_id: str) -> int:
    """
    获取最后活动时间

    优先使用 sessions.json 的 updatedAt，更可靠
    """
    # 方案 1：使用 sessions.json 的 updatedAt（推荐）
    return get_session_updated_at(agent_id)

    # 方案 2：解析最新消息的时间戳（备用）
    # messages = get_recent_messages_with_timestamp(agent_id, limit=10)
    # for item in reversed(messages):
    #     ts = item.get('timestamp', 0)
    #     if ts:
    #         return ts
    # return 0


def get_pending_tool_call_with_timestamp(agent_id: str) -> Optional[Dict[str, Any]]:
    """
    获取待处理的工具调用（包含时间戳）

    复用 get_latest_tool_call 的匹配逻辑，但返回消息级别的时间戳

    Returns:
        {'id': str, 'name': str, 'hasResult': bool, 'timestamp': int} or None
    """
    messages = get_recent_messages_with_timestamp(agent_id, limit=30)

    tool_calls = {}  # id -> {name, timestamp, hasResult}
    tool_results = set()

    for item in messages:
        msg = item.get('message', {})
        ts = item.get('timestamp', 0)

        if msg.get('role') == 'assistant':
            content = msg.get('content', [])
            if isinstance(content, str):
                continue
            for c in content:
                if isinstance(c, dict) and c.get('type') == 'toolCall':
                    tool_id = c.get('id')
                    if tool_id:
                        tool_calls[tool_id] = {
                            'id': tool_id,
                            'name': c.get('name', 'unknown'),
                            'timestamp': ts,
                            'hasResult': False
                        }

        elif msg.get('role') == 'toolResult':
            tool_call_id = msg.get('toolCallId') or msg.get('tool_call_id')
            if tool_call_id:
                tool_results.add(tool_call_id)

    # 标记已有结果的 toolCall
    for tool_id in tool_calls:
        if tool_id in tool_results:
            tool_calls[tool_id]['hasResult'] = True

    # 返回最后一个未完成的 toolCall
    for tool_id in reversed(list(tool_calls.keys())):
        info = tool_calls[tool_id]
        if not info['hasResult']:
            return info

    # 所有 toolCall 都已完成，返回最后一个
    if tool_calls:
        last_id = list(tool_calls.keys())[-1]
        return tool_calls[last_id]

    return None
```

#### 文件: `src/backend/status/status_calculator.py`

```python
import logging
import time
from typing import Dict, Any
from data.session_reader import get_last_activity_time, get_pending_tool_call_with_timestamp
from data.subagent_reader import is_agent_working, get_waiting_child_agent

logger = logging.getLogger(__name__)


def get_display_status(agent_id: str) -> Dict[str, Any]:
    """
    获取用于前端显示的状态（基于时间阈值）

    Returns:
        {
            'status': 'idle' | 'working',
            'display': str,      # 显示文本
            'duration': int,     # 持续时间（秒）
            'alert': bool,       # 是否需要警告
        }
    """
    # 无任务
    if not is_agent_working(agent_id):
        return {'status': 'idle', 'display': '空闲', 'duration': 0, 'alert': False}

    # 计算空闲时间（使用 sessions.json 的 updatedAt）
    last_activity = get_last_activity_time(agent_id)
    now = int(time.time() * 1000)
    idle_seconds = int((now - last_activity) / 1000) if last_activity else 0

    # 检查等待子代理
    waiting_for = get_waiting_child_agent(agent_id)
    if waiting_for and idle_seconds > 3:
        logger.debug(f"[{agent_id}] Waiting for child: {waiting_for}, duration: {idle_seconds}s")
        return {
            'status': 'working',
            'display': f'等待 {waiting_for}',
            'duration': idle_seconds,
            'alert': idle_seconds > 60
        }

    # 检查工具执行（使用消息级别的时间戳计算 duration）
    tool_call = get_pending_tool_call_with_timestamp(agent_id)
    if tool_call:
        tool_timestamp = tool_call.get('timestamp', 0)
        tool_duration = int((now - tool_timestamp) / 1000) if tool_timestamp else 0
        tool_name = tool_call.get('name', '')

        # 只有未完成且超过阈值才显示
        if not tool_call.get('hasResult') and tool_duration > 2:
            logger.debug(f"[{agent_id}] Tool executing: {tool_name}, duration: {tool_duration}s")
            if tool_name == 'Bash':
                return {'status': 'working', 'display': '执行命令', 'duration': tool_duration, 'alert': tool_duration > 30}
            elif tool_name in ('Write', 'Edit'):
                return {'status': 'working', 'display': '读写文件', 'duration': tool_duration, 'alert': False}
            elif tool_duration > 3:
                return {'status': 'working', 'display': '执行工具', 'duration': tool_duration, 'alert': False}

    # 检查等待模型
    if idle_seconds > 5:
        alert = idle_seconds > 15
        display = '等待响应' + (' (可能限流)' if alert else '')
        logger.debug(f"[{agent_id}] Waiting for model, duration: {idle_seconds}s, alert: {alert}")
        return {'status': 'working', 'display': display, 'duration': idle_seconds, 'alert': alert}

    # 快速执行中
    return {'status': 'working', 'display': '处理中...', 'duration': 0, 'alert': False}
```

#### 文件: `src/backend/data/subagent_reader.py`

```python
from typing import Optional

def get_waiting_child_agent(agent_id: str) -> Optional[str]:
    """
    获取正在等待的子代理名称

    Returns:
        子代理名称，如果没有则返回 None
    """
    active_runs = get_active_runs()
    for run in active_runs:
        requester_key = run.get('requesterSessionKey', '')
        # 检查这个 agent 是否是 requester（即它在等待子 agent）
        if f'agent:{agent_id}:' in requester_key:
            child_key = run.get('childSessionKey', '')
            if child_key and ':' in child_key:
                parts = child_key.split(':')
                if len(parts) >= 2 and parts[0] == 'agent':
                    return parts[1]
    return None
```

#### 文件: `src/backend/api/collaboration.py`

修改 `/api/collaboration/dynamic` 接口，填充 `agentDynamicStatuses`：

```python
import logging
from pydantic import BaseModel
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AgentDisplayStatus(BaseModel):
    """Agent 显示状态"""
    status: str  # 'idle' | 'working'
    display: str
    duration: int
    alert: bool


class CollaborationDynamic(BaseModel):
    """动态数据模型"""
    activePath: list
    recentCalls: list
    agentStatuses: Dict[str, str]
    agentDynamicStatuses: Optional[Dict[str, AgentDisplayStatus]] = None  # 新增，向后兼容
    taskNodes: list
    taskEdges: list
    mainAgentId: str
    lastUpdate: int


@router.get("/collaboration/dynamic", response_model=CollaborationDynamic)
async def get_collaboration_dynamic():
    """获取动态数据"""
    from data.config_reader import get_agents_list, get_main_agent_id
    from data.subagent_reader import get_active_runs
    from status.status_calculator import calculate_agent_status, get_display_status

    # ... 现有逻辑 ...

    # 添加显示状态
    agent_dynamic_statuses = {}
    for agent in agents_list:
        aid = agent.get('id', '')
        if aid:
            try:
                agent_dynamic_statuses[aid] = get_display_status(aid)
            except Exception as e:
                logger.warning(f"Failed to get display status for {aid}: {e}")

    return CollaborationDynamic(
        activePath=list(set(active_path)),
        recentCalls=model_calls,
        agentStatuses=agent_statuses,
        agentDynamicStatuses=agent_dynamic_statuses,  # 新增
        taskNodes=task_nodes,
        taskEdges=task_edges,
        mainAgentId=main_agent_id,
        lastUpdate=int(__import__('time').time() * 1000),
    )
```

修复模型调用小球匹配问题：

```python
import re
import logging

logger = logging.getLogger(__name__)

# 模块级缓存
_model_mapping_cache: Optional[Dict[str, str]] = None


def _get_model_mapping() -> Dict[str, str]:
    """获取 model 映射（带缓存）"""
    global _model_mapping_cache
    if _model_mapping_cache is None:
        from data.config_reader import get_all_models_from_agents
        _model_mapping_cache = {}
        for model_id in get_all_models_from_agents():
            short = model_id.split('/')[-1]
            _model_mapping_cache[short] = model_id
            # 添加去除日期版本号的映射（使用正则精确匹配 -20YYMMDD）
            base = re.sub(r'-20\d{6}$', '', short)
            if base != short:
                _model_mapping_cache[base] = model_id
    return _model_mapping_cache


def _normalize_model_id(model_from_session: str) -> str:
    """将 session 中的 model 值规范化为标准格式

    注意:
        - 使用正则表达式精确匹配 -20YYMMDD 日期后缀
        - 避免 split('-20')[0] 的边界问题：
          * claude-sonnet-4-20250514 不会被错误截断为 "claude-sonnet-4"
          * gpt-4-turbo-2024-04-09 不会被错误处理（格式不匹配正则）
    """
    if not model_from_session:
        return '(unknown)'

    if '/' in model_from_session:
        return model_from_session

    mapping = _get_model_mapping()

    # 精确匹配
    if model_from_session in mapping:
        return mapping[model_from_session]

    # 使用正则去除日期版本号后匹配
    base_name = re.sub(r'-20\d{6}$', '', model_from_session)
    if base_name in mapping:
        return mapping[base_name]

    logger.debug(f"Unknown model format: {model_from_session}")
    return model_from_session
```

### 5.3 前端修改

#### 文件: `frontend/src/types/collaboration.ts`

更新类型定义：

```typescript
export interface AgentDisplayStatus {
  status: 'idle' | 'working'
  display: string        // 显示文本
  duration: number       // 持续时间（秒）
  alert: boolean         // 是否需要警告
}

export interface CollaborationDynamic {
  activePath: string[]
  recentCalls: ModelCall[]
  agentStatuses: Record<string, string>
  agentDynamicStatuses?: Record<string, AgentDisplayStatus>  // 可选字段，向后兼容
  taskNodes: CollaborationNode[]
  taskEdges: CollaborationEdge[]
  mainAgentId: string
  lastUpdate: number
}
```

#### 文件: `frontend/src/components/collaboration/CollaborationFlowSection.vue`

更新动态数据处理：

```typescript
function handleCollaborationDynamicUpdate(dyn: CollaborationDynamic): void {
  // ... 现有逻辑 ...

  // 更新详细状态（兼容旧版本 API）
  if (dyn.agentDynamicStatuses) {
    for (const node of agentNodesLocal) {
      if (node.id && dyn.agentDynamicStatuses[node.id]) {
        const dynStatus = dyn.agentDynamicStatuses[node.id]
        node.subStatus = mapDisplayToSubStatus(dynStatus.display)
        node.currentAction = dynStatus.display
        // 可选：存储 duration 和 alert 到 metadata
        node.metadata = {
          ...node.metadata,
          duration: dynStatus.duration,
          alert: dynStatus.alert
        }
      }
    }
  }
}

function mapDisplayToSubStatus(display: string): SubStatus | undefined {
  if (display.includes('等待响应')) return 'waiting_llm'
  if (display.includes('等待')) return 'waiting_child'
  if (display.includes('执行') || display.includes('读写')) return 'tool_executing'
  return undefined
}
```

#### 文件: `frontend/src/components/AgentCard.vue`

更新显示逻辑（注意：实际使用的是 `CollaborationFlowSection.vue` 中的 AgentCard）：

```vue
<template>
  <!-- 详细状态（工作中时显示） -->
  <div v-if="agent.status === 'working' && currentAction" class="status-detail" :class="{ 'alert': isAlert }">
    <span class="action-icon">{{ statusIcon }}</span>
    <span class="action-text">{{ currentAction }}</span>
    <span v-if="duration > 0" class="duration">⏱ {{ duration }}s</span>
  </div>

  <!-- 空闲状态 -->
  <div v-else-if="agent.status === 'idle'" class="idle-hint">
    空闲
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  agent: { name: string; status: 'idle' | 'working' | 'down' }
  currentAction?: string
  duration?: number
  isAlert?: boolean
  // ... 其他 props
}>()

const statusIcon = computed(() => {
  const display = props.currentAction || ''
  if (display.includes('等待响应')) return '📡'
  if (display.includes('等待')) return '⏳'
  if (display.includes('执行')) return '⚙️'
  if (display.includes('读写')) return '📄'
  return '🔄'
})
</script>
```

---

## 第六部分：总结

### 问题根因

| 问题 | 根因 |
|------|------|
| 一直显示"思考中" | thinking 块判断过于宽松，无时间判断 |
| 任务完成仍显示工作中 | runs.json 更新延迟 + 2分钟活跃窗口 |
| 状态闪烁 | 追求精确显示快速动作 |
| 模型调用小球匹配错误 | Session 中 model 格式与配置不一致 |
| timestamp 获取错误 | get_recent_messages 不返回 data.timestamp |

### 解决方案核心

1. **去掉"思考中"**：用"处理中..."代替快速执行时的通用状态
2. **基于时间阈值**：只有超过阈值才显示具体状态
3. **显示持续时间**：让用户知道"卡了多久"
4. **填充 dynamic API**：后端返回 `agentDynamicStatuses`
5. **规范化 model 字段**：后端统一 session 中的 model 格式
6. **修复 timestamp 获取**：新增带时间戳的消息接口

### 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `session_reader.py` | 新增 `get_recent_messages_with_timestamp()`, `get_last_activity_time()`, `get_pending_tool_call_with_timestamp()` |
| `subagent_reader.py` | 新增 `get_waiting_child_agent()` |
| `status_calculator.py` | 新增 `get_display_status()`，使用 logging |
| `collaboration.py` | 新增 `AgentDisplayStatus` 模型，填充 `agentDynamicStatuses`，新增 `_normalize_model_id()` |
| `collaboration.ts` | 更新类型定义，`agentDynamicStatuses` 为可选字段 |
| `CollaborationFlowSection.vue` | 更新动态数据处理逻辑 |
| `AgentCard.vue` | 适配新的显示逻辑 |

### 注意事项

1. **向后兼容**：`agentDynamicStatuses` 为可选字段，旧版前端可忽略
2. **日志规范**：生产环境使用 `logging` 模块，通过配置控制日志级别
3. **性能优化**：`_get_recent_model_calls` 需要限制文件扫描范围
4. **组件路径**：协作流程中使用的是 `CollaborationFlowSection.vue` 引用的 `AgentCard.vue`
