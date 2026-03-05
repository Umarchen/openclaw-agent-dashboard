# TR-Timeline-03: 工具链路可视化详细设计

**版本**: v1.0  
**日期**: 2026-03-05  
**优先级**: P2  
**依赖**: TR-Timeline-01  

---

## 一、功能概述

强化 toolCall 与 toolResult 之间的因果关系，帮助用户理解：
- 哪个工具调用产生了哪个结果
- 工具执行的时间顺序
- 失败的工具调用与结果对应关系

---

## 二、需求清单

| 需求ID | 需求描述 | 优先级 |
|--------|---------|--------|
| TC-001 | toolCall 与 toolResult 之间显示连接线 | P2 |
| TC-002 | toolResult 相对 toolCall 缩进展示 | P2 |
| TC-003 | 配对高亮（点击 toolCall 高亮对应 toolResult） | P2 |
| TC-004 | 折叠联动（折叠 toolCall 时可选折叠 toolResult） | P3 |
| TC-005 | 工具执行时间指示 | P2 |

---

## 三、数据结构设计

### 3.1 扩展 TimelineStep

```typescript
// types.ts

export interface TimelineStep {
  // ... 现有字段
  
  // 工具链路关联（新增）
  pairedToolCallId?: string   // toolResult 专用：对应的 toolCall ID
  pairedToolResultId?: string // toolCall 专用：对应的 toolResult ID
  executionTime?: number      // 工具执行耗时（ms），toolResult 专用
}
```

### 3.2 后端配对逻辑

```python
def _pair_tool_calls_and_results(steps: List[Dict]) -> List[Dict]:
    """
    建立 toolCall 与 toolResult 的配对关系
    
    规则：
    1. 使用 toolCallId 字段匹配
    2. 按 toolCallId 建立 ID 映射
    3. 为 toolResult 添加 pairedToolCallId
    4. 为 toolCall 添加 pairedToolResultId
    """
    # 建立 toolCall ID 映射
    tool_call_map = {}  # toolCallId -> step_index
    for i, step in enumerate(steps):
        if step.get('type') == 'toolCall':
            tc_id = step.get('toolCallId') or step.get('id')
            tool_call_map[tc_id] = i
    
    # 配对 toolResult
    for i, step in enumerate(steps):
        if step.get('type') == 'toolResult':
            tc_id = step.get('toolCallId')
            if tc_id and tc_id in tool_call_map:
                call_idx = tool_call_map[tc_id]
                # 双向关联
                steps[i]['pairedToolCallId'] = steps[call_idx]['id']
                steps[call_idx]['pairedToolResultId'] = step['id']
                
                # 计算执行时间
                call_time = steps[call_idx].get('timestamp', 0)
                result_time = step.get('timestamp', 0)
                if call_time and result_time:
                    steps[i]['executionTime'] = result_time - call_time
    
    return steps
```

---

## 四、前端实现设计

### 4.1 连接线组件

```vue
<!-- TimelineToolLink.vue -->
<template>
  <div class="tool-link" v-if="showLink">
    <svg class="link-svg" :style="linkStyle">
      <path
        :d="pathD"
        class="link-path"
        :class="{ 'link-error': isError, 'link-active': isActive }"
      />
    </svg>
    <span class="link-time" v-if="executionTime">{{ formatDuration(executionTime) }}</span>
  </div>
</template>

<script setup>
const props = defineProps<{
  callRect: DOMRect | null
  resultRect: DOMRect | null
  isError: boolean
  isActive: boolean
  executionTime?: number
}>()

const pathD = computed(() => {
  if (!props.callRect || !props.resultRect) return ''
  const x1 = 20  // 缩进起点
  const y1 = props.callRect.bottom
  const x2 = 20
  const y2 = props.resultRect.top
  return `M ${x1} ${y1} C ${x1} ${(y1+y2)/2}, ${x2} ${(y1+y2)/2}, ${x2} ${y2}`
})
</script>

<style scoped>
.tool-link {
  position: relative;
  margin: -4px 0;
  padding-left: 20px;
}

.link-svg {
  position: absolute;
  left: 0;
  top: 0;
  width: 40px;
  height: 100%;
  pointer-events: none;
}

.link-path {
  fill: none;
  stroke: #94a3b8;
  stroke-width: 2;
  stroke-dasharray: 4 2;
}

.link-path.link-error {
  stroke: #ef4444;
}

.link-path.link-active {
  stroke: #3b82f6;
  stroke-width: 2.5;
}

.link-time {
  position: absolute;
  left: 28px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 10px;
  color: #64748b;
  background: white;
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
```

### 4.2 缩进展示

```vue
<!-- TimelineStep.vue 修改 -->
<template>
  <div 
    class="timeline-step" 
    :class="[
      `step-${step.type}`,
      `status-${step.status}`,
      { 'is-tool-result': isPairedToolResult }
    ]"
    :style="indentStyle"
    @click="handleClick"
  >
    <!-- 缩进指示器 -->
    <div class="indent-indicator" v-if="isPairedToolResult">
      <span class="indent-line"></span>
      <span class="indent-dot"></span>
    </div>
    
    <!-- ... 原有内容 -->
  </div>
</template>

<script setup>
const isPairedToolResult = computed(() => {
  return props.step.type === 'toolResult' && props.step.pairedToolCallId
})

const indentStyle = computed(() => {
  if (isPairedToolResult.value) {
    return { marginLeft: '24px' }
  }
  return {}
})

// 点击高亮配对
const emit = defineEmits(['highlight-pair'])

function handleClick() {
  if (props.step.pairedToolCallId || props.step.pairedToolResultId) {
    emit('highlight-pair', {
      callId: props.step.pairedToolCallId || props.step.id,
      resultId: props.step.pairedToolResultId || props.step.id
    })
  }
  toggleExpand()
}
</script>

<style scoped>
.is-tool-result {
  position: relative;
}

.indent-indicator {
  position: absolute;
  left: -24px;
  top: 0;
  bottom: 0;
  width: 24px;
}

.indent-line {
  position: absolute;
  left: 12px;
  top: 0;
  bottom: 50%;
  width: 2px;
  background: #e5e7eb;
}

.indent-dot {
  position: absolute;
  left: 8px;
  top: 50%;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #94a3b8;
  border: 2px solid white;
}

.step-toolResult.status-error .indent-dot {
  background: #ef4444;
}

/* 配对高亮 */
.timeline-step.highlighted {
  box-shadow: 0 0 0 2px #3b82f6;
}
</style>
```

### 4.3 TimelineView 集成

```vue
<!-- TimelineView.vue 修改 -->
<template>
  <div class="timeline-view">
    <!-- ... 头部 -->
    
    <div class="timeline-content">
      <!-- 步骤列表 -->
      <div class="steps-list" ref="stepsListRef">
        <template v-for="(step, index) in data.steps" :key="step.id">
          <!-- 工具链路连接线 -->
          <TimelineToolLink
            v-if="shouldShowLink(step, index)"
            :callRect="getStepRect(step.pairedToolCallId)"
            :resultRect="getStepRect(step.id)"
            :isError="step.toolResultStatus === 'error'"
            :isActive="highlightedPair?.resultId === step.id"
            :executionTime="step.executionTime"
          />
          
          <!-- 步骤 -->
          <TimelineStepItem
            :ref="el => setStepRef(step.id, el)"
            :step="step"
            :prevStep="data.steps[index - 1]"
            @highlight-pair="handleHighlightPair"
          />
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
const stepRefs = ref<Record<string, HTMLElement>>({})
const highlightedPair = ref<{ callId: string, resultId: string } | null>(null)

function setStepRef(id: string, el: unknown) {
  if (el) stepRefs.value[id] = el as HTMLElement
}

function getStepRect(id: string): DOMRect | null {
  const el = stepRefs.value[id]
  return el?.getBoundingClientRect() || null
}

function shouldShowLink(step: TimelineStep, index: number): boolean {
  // 只在 toolResult 前显示连接线
  if (step.type !== 'toolResult') return false
  if (!step.pairedToolCallId) return false
  return true
}

function handleHighlightPair(pair: { callId: string, resultId: string }) {
  highlightedPair.value = pair
  // 3秒后取消高亮
  setTimeout(() => {
    highlightedPair.value = null
  }, 3000)
}
</script>
```

---

## 五、UI 效果示意

```
┌─ 步骤列表 ──────────────────────────────────────────────────────┐
│                                                                 │
│  👤 用户  分析项目结构                          10:32:01  +0ms  │
│                                                                 │
│  🧠 思考  LLM 推理 · 约 120 字                 10:32:02  +1.2s  │
│                                                                 │
│  🔧 Read 调用  path: src/main.py               10:32:03  +0.8s  │
│       │                                                         │
│       │ 1.5s                                                    │
│       ▼                                                         │
│  ┌─ ✅ Read 结果 · 342 行 ───────────────────  10:32:05  +1.5s ─┐│
│  │                                                               ││
│  │  返回 342 行内容...                                           ││
│  │                                                               ││
│  └───────────────────────────────────────────────────────────────┘│
│                                                                 │
│  🧠 思考  LLM 推理 · 约 80 字                  10:32:06  +0.3s  │
│                                                                 │
│  🔧 Bash 调用  command: ls -la                 10:32:07  +0.2s  │
│       │                                                         │
│       │ 0.8s                                                    │
│       ▼                                                         │
│  ┌─ ❌ Bash 失败 · 权限不足 ──────────────────  10:32:08  +0.8s ─┐│
│  │                                                               ││
│  │  ❌ 工具执行失败                                              ││
│  │  EACCES: permission denied                                    ││
│  │                                                               ││
│  │  💡 建议:                                                     ││
│  │  • 检查文件/目录权限                                          ││
│  │  • 确认当前用户有访问权限                                     ││
│  │                                                               ││
│  └───────────────────────────────────────────────────────────────┘│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 六、交互设计

### 6.1 点击高亮

| 操作 | 效果 |
|------|------|
| 点击 toolCall | 高亮对应的 toolResult（蓝色边框） |
| 点击 toolResult | 高亮对应的 toolCall（蓝色边框） |
| 高亮持续 3 秒 | 自动取消高亮 |

### 6.2 悬停提示

| 悬停位置 | 提示内容 |
|---------|---------|
| 连接线 | 「工具执行耗时: 1.5s」 |
| 缩进指示器 | 「来自 Read 调用」 |

### 6.3 折叠联动（P3 可选）

| 操作 | 效果 |
|------|------|
| 折叠 toolCall | 可选：同时折叠对应 toolResult |
| 折叠 toolResult | 不影响 toolCall |

---

## 七、实现步骤

### 7.1 后端改动

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `timeline_reader.py` | 新增 `_pair_tool_calls_and_results()` |
| 2 | `timeline_reader.py` | 在 `_parse_session_file()` 末尾调用配对 |
| 3 | `timeline_reader.py` | 添加 `executionTime` 计算 |

### 7.2 前端改动

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1 | `types.ts` | 添加配对字段 |
| 2 | `TimelineToolLink.vue` | 新建连接线组件 |
| 3 | `TimelineStep.vue` | 添加缩进、高亮逻辑 |
| 4 | `TimelineView.vue` | 集成连接线、管理高亮状态 |

---

## 八、测试用例

### 8.1 配对测试

| 场景 | 预期结果 |
|------|---------|
| 单个 toolCall + toolResult | 正确配对 |
| 多个 toolCall + 多个 toolResult | 按 toolCallId 正确配对 |
| toolCall 无对应 toolResult | pairedToolResultId 为空 |
| toolResult 无对应 toolCall | pairedToolCallId 为空 |
| 失败的 toolResult | 连接线显示红色 |

### 8.2 执行时间测试

| 场景 | 预期结果 |
|------|---------|
| 正常执行 | 显示执行耗时 |
| 快速执行 (<100ms) | 显示 ms |
| 长时间执行 (>1s) | 显示 s |
| 无时间戳 | 不显示执行时间 |

---

## 九、工作量评估

| 任务 | 预估时间 |
|------|---------|
| 后端配对逻辑 | 1h |
| 后端执行时间计算 | 0.5h |
| 前端类型扩展 | 0.25h |
| TimelineToolLink 组件 | 1.5h |
| TimelineStep 缩进/高亮 | 1h |
| TimelineView 集成 | 1h |
| 样式调整 | 0.5h |
| 测试与调试 | 1h |
| **总计** | **6.75h** |

---

## 十、风险与依赖

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| toolCallId 不一致 | 配对失败 | 后端兼容多种 ID 格式 |
| DOM 位置计算误差 | 连接线错位 | 使用 nextTick 确保 DOM 更新 |
| 步骤动态增删 | 引用失效 | 使用响应式 ref 管理 |

