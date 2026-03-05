# TR-Timeline-02: LLM 轮次分组详细设计

**版本**: v1.0  
**日期**: 2026-03-05  
**优先级**: P2  
**依赖**: TR-Timeline-01  

---

## 一、功能概述

将时序步骤按「LLM 轮次」分组展示，帮助用户理解 Agent 的执行逻辑：
- 同一次 LLM 调用产生的 thinking + toolCall + text 归为一组
- toolResult 作为独立的「工具执行」块
- 用视觉分组区分「LLM 输出」与「工具执行」

---

## 二、数据结构设计

### 2.1 后端数据模型扩展

**新增 `LLMRound` 类型**:

```python
# timeline_reader.py

class LLMRound(BaseModel):
    """LLM 轮次"""
    id: str                    # round_0, round_1, ...
    index: int                 # 轮次序号（从1开始）
    trigger: Optional[str]     # 触发原因：'user_input' | 'tool_result' | 'start'
    triggerBy: Optional[str]   # 触发来源：用户消息/工具名/子Agent
    steps: List[str]           # 该轮次包含的步骤 ID 列表
    # 统计
    tokenUsage: Optional[Dict[str, int]] = None  # 该轮次的 token 使用
    duration: int = 0          # 该轮次耗时（ms）
```

**扩展 `TimelineResponse`**:

```python
class TimelineResponse(BaseModel):
    # ... 现有字段
    rounds: List[LLMRound] = []  # 新增：LLM 轮次分组
    roundMode: bool = True       # 新增：是否启用轮次分组模式
```

### 2.2 前端类型定义

```typescript
// types.ts

export interface LLMRound {
  id: string
  index: number
  trigger: 'user_input' | 'tool_result' | 'start' | 'subagent_result'
  triggerBy?: string  // 触发来源描述
  stepIds: string[]
  tokenUsage?: TokenUsage
  duration: number
}

export interface TimelineResponse {
  // ... 现有字段
  rounds?: LLMRound[]
  roundMode?: boolean
}
```

---

## 三、后端实现设计

### 3.1 轮次识别逻辑

**核心算法**:

```python
def _build_llm_rounds(steps: List[Dict]) -> List[Dict]:
    """
    根据步骤序列构建 LLM 轮次
    
    规则：
    1. user 消息开启新轮次
    2. toolResult 后的第一个 assistant 步骤开启新轮次
    3. 同一轮次内的 thinking + toolCall + text 归为一组
    """
    rounds = []
    current_round = None
    round_index = 0
    
    for step in steps:
        step_type = step.get('type')
        
        # user 消息：结束上一轮，开启新轮次
        if step_type == 'user':
            if current_round:
                rounds.append(current_round)
            round_index += 1
            current_round = {
                'id': f'round_{round_index}',
                'index': round_index,
                'trigger': 'user_input' if not step.get('senderId') else 'subagent_result',
                'triggerBy': step.get('senderName') or '用户',
                'stepIds': [step['id']],
                'duration': 0
            }
            continue
        
        # toolResult：单独作为工具执行块
        if step_type == 'toolResult':
            if current_round:
                rounds.append(current_round)
                current_round = None
            # toolResult 不属于任何 LLM 轮次
            continue
        
        # assistant 步骤（thinking, toolCall, text）
        if step_type in ('thinking', 'toolCall', 'text'):
            # 如果 toolResult 后第一个 assistant 步骤，开启新轮次
            if not current_round:
                round_index += 1
                current_round = {
                    'id': f'round_{round_index}',
                    'index': round_index,
                    'trigger': 'tool_result',
                    'triggerBy': '工具执行结果',
                    'stepIds': [],
                    'duration': 0
                }
            current_round['stepIds'].append(step['id'])
        
        # error：结束当前轮次
        if step_type == 'error':
            if current_round:
                rounds.append(current_round)
                current_round = None
    
    # 处理最后一个轮次
    if current_round:
        rounds.append(current_round)
    
    return rounds
```

### 3.2 触发原因识别

| trigger | triggerBy | 说明 |
|---------|-----------|------|
| `user_input` | `用户` | 用户输入消息 |
| `subagent_result` | `分析师回传` | 子 Agent 回传结果 |
| `tool_result` | `Read 结果` | 工具执行结果触发 |
| `start` | `会话开始` | 会话初始轮次 |

---

## 四、前端实现设计

### 4.1 组件结构

```
TimelineView.vue
├── TimelineLegend.vue          # 图例
├── TimelineRound.vue           # 轮次分组容器（新增）
│   ├── RoundHeader.vue         # 轮次标题
│   └── TimelineStep.vue x N    # 步骤列表
└── TimelineFooter.vue          # 统计
```

### 4.2 TimelineRound.vue 设计

```vue
<template>
  <div class="timeline-round" :class="`trigger-${round.trigger}`">
    <!-- 轮次标题 -->
    <div class="round-header">
      <span class="round-badge">LLM #{{ round.index }}</span>
      <span class="round-trigger">{{ triggerLabel }}</span>
      <span class="round-stats" v-if="round.tokenUsage">
        {{ round.tokenUsage.input + round.tokenUsage.output }} tokens
      </span>
    </div>
    
    <!-- 轮次内容 -->
    <div class="round-content">
      <template v-for="(stepId, idx) in round.stepIds" :key="stepId">
        <TimelineConnector v-if="idx > 0" />
        <TimelineStepItem :step="getStep(stepId)" />
      </template>
    </div>
  </div>
</template>

<script setup>
const triggerLabels = {
  'user_input': '👤 用户输入触发',
  'subagent_result': '↩️ 子代理回传',
  'tool_result': '🔧 工具结果触发',
  'start': '🚀 会话开始'
}

const triggerLabel = computed(() => {
  const label = triggerLabels[props.round.trigger]
  if (props.round.triggerBy && props.round.trigger !== 'user_input') {
    return `${label} · ${props.round.triggerBy}`
  }
  return label
})
</script>
```

### 4.3 样式设计

```css
/* 轮次容器 */
.timeline-round {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
}

/* 轮次标题 */
.round-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-bottom: 1px solid #e5e7eb;
}

.round-badge {
  font-size: 11px;
  font-weight: 600;
  color: #4338ca;
  background: #e0e7ff;
  padding: 2px 8px;
  border-radius: 4px;
}

.round-trigger {
  font-size: 12px;
  color: #64748b;
}

/* 触发类型样式 */
.trigger-user_input .round-header {
  border-left: 3px solid #3b82f6;
}

.trigger-subagent_result .round-header {
  border-left: 3px solid #10b981;
}

.trigger-tool_result .round-header {
  border-left: 3px solid #f59e0b;
}

/* 轮次内容 */
.round-content {
  padding: 12px;
}
```

---

## 五、UI 效果示意

```
+=================================================================+
|  📊 实时执行时序                                                |
|  图例: 👤 用户  🧠 思考  🤖 回复  🔧 调用  ✅ 成功  ❌ 失败      |
+=================================================================+
|                                                                 |
|  ┌─ LLM #1 · 👤 用户输入触发 ─────────────────────────────────┐ |
|  │                                                             │ |
|  │  👤 用户  帮我分析项目结构                   10:32:01 +0ms  │ |
|  │  🧠 思考  LLM 推理 · 约 120 字              +1.2s          │ |
|  │  🔧 Read 调用  src/main.py                  +0.8s          │ |
|  │                                                             │ |
|  └─────────────────────────────────────────────────────────────┘ |
|                                                                 |
|  ── 工具执行 ─────────────────────────────────────────────────── |
|  ✅ Read 结果 · 342 行                          10:32:04  +1.5s |
|                                                                 |
|  ┌─ LLM #2 · 🔧 工具结果触发 · Read ──────────────────────────┐ |
|  │                                                             │ |
|  │  🧠 思考  LLM 推理 · 约 80 字               +0.3s          │ |
|  │  🤖 回复  LLM 输出 · 约 200 字              +1.2s          │ |
|  │                                                             │ |
|  └─────────────────────────────────────────────────────────────┘ |
|                                                                 |
+=================================================================+
```

---

## 六、实现步骤

### 6.1 后端改动

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `timeline_reader.py` | 新增 `LLMRound` 数据类 |
| 2 | `timeline_reader.py` | 新增 `_build_llm_rounds()` 函数 |
| 3 | `timeline_reader.py` | 修改 `get_timeline_steps()` 返回 rounds |
| 4 | `api/timeline.py` | 更新响应模型 |

### 6.2 前端改动

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `types.ts` | 新增 `LLMRound` 类型 |
| 2 | `TimelineRound.vue` | 新建轮次组件 |
| 3 | `TimelineView.vue` | 集成轮次分组逻辑 |
| 4 | `TimelineView.vue` | 添加轮次切换开关 |

---

## 七、测试用例

### 7.1 基础场景

| 场景 | 预期结果 |
|------|---------|
| 纯用户消息 | 1 个轮次，包含 user |
| user → assistant(thinking+text) | 1 个轮次，包含 user+thinking+text |
| user → assistant(toolCall) → toolResult → assistant(text) | 2 个轮次 + 1 个工具执行块 |
| 子 Agent 回传 | trigger 为 subagent_result |

### 7.2 边界场景

| 场景 | 预期结果 |
|------|---------|
| 空步骤列表 | 0 个轮次 |
| 只有 toolResult | 0 个轮次，直接显示 |
| 连续多个 toolResult | 顺序显示，不分组 |
| error 中断 | 已有轮次正常显示 |

---

## 八、工作量评估

| 任务 | 预估时间 |
|------|---------|
| 后端数据模型 | 0.5h |
| 后端轮次识别算法 | 1h |
| 前端类型定义 | 0.25h |
| TimelineRound 组件 | 1.5h |
| TimelineView 集成 | 1h |
| 样式调整 | 0.5h |
| 测试与调试 | 1h |
| **总计** | **5.75h** |

---

## 九、风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 步骤顺序不确定 | 轮次识别错误 | 后端严格按时间戳排序 |
| token 统计跨轮次 | 数据不准确 | 按步骤归属累加 |
| 向后兼容 | 旧 API 消费者异常 | roundMode 可选参数 |

