<template>
  <div class="timeline-round" :class="`trigger-${round.trigger}`">
    <!-- 轮次标题 -->
    <div class="round-header">
      <span class="round-badge">LLM #{{ round.index }}</span>
      <span class="round-trigger">{{ triggerLabel }}</span>
      <span class="round-stats" v-if="round.tokens">
        {{ round.tokens.input + round.tokens.output }} tokens
      </span>
    </div>

    <!-- 轮次内容 -->
    <div class="round-content">
      <template v-for="(stepId, idx) in round.stepIds" :key="stepId">
        <TimelineConnector v-if="idx > 0" />
        <TimelineStepItem
          :step="getStep(stepId)"
          :prevStep="idx > 0 ? getStep(round.stepIds[idx - 1]) : undefined"
          :highlightedPair="highlightedPair"
          @highlight-pair="$emit('highlight-pair', $event)"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LLMRound, TimelineStep } from './types'
import TimelineStepItem from './TimelineStep.vue'
import TimelineConnector from './TimelineConnector.vue'

const props = defineProps<{
  round: LLMRound
  steps: TimelineStep[]
  highlightedPair?: { callId: string; resultId: string } | null
}>()

defineEmits<{
  'highlight-pair': [pair: { callId: string; resultId: string }]
}>()

const triggerLabels: Record<string, string> = {
  'user_input': '👤 用户输入触发',
  'subagent_result': '↩️ 子代理回传',
  'tool_result': '🔧 工具结果触发',
  'start': '🚀 会话开始'
}

const triggerLabel = computed(() => {
  const label = triggerLabels[props.round.trigger] || props.round.trigger
  if (props.round.triggerBy && props.round.trigger !== 'user_input') {
    return `${label} · ${props.round.triggerBy}`
  }
  return label
})

function getStep(stepId: string): TimelineStep {
  const step = props.steps.find(s => s.id === stepId)
  if (!step) {
    console.warn(`Step not found: ${stepId}`)
    return {
      id: stepId,
      type: 'text',
      status: 'success',
      timestamp: 0
    } as TimelineStep
  }
  return step
}
</script>

<style scoped>
.timeline-round {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
  background: #fff;
}

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
  flex: 1;
}

.round-stats {
  font-size: 11px;
  color: #9ca3af;
  background: rgba(0, 0, 0, 0.04);
  padding: 2px 6px;
  border-radius: 3px;
}

.round-content {
  padding: 12px;
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

.trigger-start .round-header {
  border-left: 3px solid #8b5cf6;
}
</style>
