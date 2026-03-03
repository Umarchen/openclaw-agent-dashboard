<template>
  <div class="timeline-step" :class="[`step-${step.type}`, `status-${step.status}`]">
    <!-- 步骤头部 -->
    <div class="step-header" @click="toggleExpand">
      <div class="header-left">
        <span class="step-icon">{{ stepIcon }}</span>
        <span class="step-type">{{ stepLabel }}</span>
        <span class="step-time">{{ formatTime(step.timestamp) }}</span>
        <span class="step-duration" v-if="step.duration && step.duration > 0">
          +{{ formatDuration(step.duration) }}
        </span>
        <span class="tool-name" v-if="step.toolName">{{ step.toolName }}</span>
      </div>
      <div class="header-right">
        <span class="step-tokens" v-if="step.tokens">
          <span class="token-label">tokens:</span>
          {{ step.tokens.input + step.tokens.output }}
        </span>
        <span class="expand-icon" v-if="hasExpandableContent">
          {{ isExpanded ? '▼' : '▶' }}
        </span>
      </div>
    </div>

    <!-- 步骤内容 -->
    <div class="step-content" v-if="hasExpandableContent && isExpanded">
      <!-- 用户消息 -->
      <div class="content-block user-content" v-if="step.type === 'user' && step.content">
        <pre>{{ step.content }}</pre>
      </div>

      <!-- 思考内容 -->
      <div class="content-block thinking-content" v-if="step.type === 'thinking' && step.thinking">
        <div class="thinking-label">💭 思考过程</div>
        <pre>{{ step.thinking }}</pre>
      </div>

      <!-- 文本响应 -->
      <div class="content-block text-content" v-if="step.type === 'text' && step.content">
        <pre>{{ step.content }}</pre>
      </div>

      <!-- 工具调用 -->
      <div class="content-block tool-call-content" v-if="step.type === 'toolCall'">
        <div class="args-section" v-if="step.toolArguments">
          <div class="section-label">参数:</div>
          <pre class="code-block">{{ formatJson(step.toolArguments) }}</pre>
        </div>
      </div>

      <!-- 工具结果 -->
      <div class="content-block tool-result-content" v-if="step.type === 'toolResult'">
        <div class="result-header">
          <span class="result-status" :class="step.toolResultStatus">
            {{ step.toolResultStatus === 'ok' ? '✅ 成功' : '❌ 失败' }}
          </span>
          <button class="copy-btn" @click="copyResult" v-if="step.toolResult">
            复制
          </button>
        </div>
        <div class="result-body" v-if="step.toolResult">
          <pre :class="{ truncated: !showFullResult }">{{ displayResult }}</pre>
          <button
            v-if="isResultLong"
            class="show-more-btn"
            @click.stop="showFullResult = !showFullResult"
          >
            {{ showFullResult ? '收起' : `展开全部 (${resultLineCount} 行)` }}
          </button>
        </div>
      </div>

      <!-- 错误信息 -->
      <div class="content-block error-content" v-if="step.type === 'error'">
        <div class="error-type">{{ step.errorType || 'unknown' }}</div>
        <div class="error-message">{{ step.errorMessage }}</div>
        <div class="error-suggestion" v-if="errorSuggestion">
          <div class="suggestion-label">💡 建议:</div>
          <ul>
            <li v-for="(s, i) in errorSuggestion" :key="i">{{ s }}</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { TimelineStep, StepType } from './types'
import { stepConfig } from './types'

const props = defineProps<{
  step: TimelineStep
  prevStep?: TimelineStep
}>()

const emit = defineEmits<{
  'toggle-collapse': []
}>()

const isExpanded = ref(!props.step.collapsed)
const showFullResult = ref(false)

const stepIcon = computed(() => {
  return stepConfig[props.step.type as StepType]?.icon || '📄'
})

const stepLabel = computed(() => {
  return stepConfig[props.step.type as StepType]?.label || props.step.type
})

const hasExpandableContent = computed(() => {
  const { type, content, thinking, toolArguments, toolResult, errorMessage } = props.step
  return content || thinking || toolArguments || toolResult || errorMessage
})

const isResultLong = computed(() => {
  if (!props.step.toolResult) return false
  return props.step.toolResult.length > 500 || props.step.toolResult.split('\n').length > 10
})

const resultLineCount = computed(() => {
  if (!props.step.toolResult) return 0
  return props.step.toolResult.split('\n').length
})

const displayResult = computed(() => {
  if (!props.step.toolResult) return ''
  if (showFullResult.value || !isResultLong.value) {
    return props.step.toolResult
  }
  const lines = props.step.toolResult.split('\n')
  return lines.slice(0, 10).join('\n') + '\n...'
})

const errorSuggestion = computed(() => {
  if (props.step.type !== 'error' || !props.step.errorType) return null

  const suggestions: Record<string, string[]> = {
    'rate-limit': [
      '降低调用频率',
      '切换到 fallback model',
      '等待配额恢复'
    ],
    'token-limit': [
      '减少上下文长度',
      '分段处理任务',
      '使用更大 context 的模型'
    ],
    'timeout': [
      '检查网络连接',
      '简化任务复杂度',
      '增加超时时间'
    ],
    'quota': [
      '充值账户',
      '切换到其他 provider',
      '等待配额重置'
    ]
  }

  return suggestions[props.step.errorType] || null
})

function toggleExpand() {
  if (hasExpandableContent.value) {
    isExpanded.value = !isExpanded.value
  }
}

function formatTime(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDuration(ms: number): string {
  if (!ms) return '0ms'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}

function formatJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2)
  } catch {
    return String(obj)
  }
}

async function copyResult() {
  if (!props.step.toolResult) return
  try {
    await navigator.clipboard.writeText(props.step.toolResult)
    alert('已复制到剪贴板')
  } catch {
    // fallback
  }
}
</script>

<style scoped>
.timeline-step {
  border-radius: 6px;
  overflow: hidden;
  transition: all 0.2s;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  user-select: none;
}

.step-header:hover {
  filter: brightness(0.98);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.step-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.step-type {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
  flex-shrink: 0;
}

.step-time {
  font-size: 11px;
  color: #9ca3af;
  flex-shrink: 0;
}

.step-duration {
  font-size: 11px;
  color: #6b7280;
  background: rgba(0,0,0,0.05);
  padding: 2px 6px;
  border-radius: 3px;
  flex-shrink: 0;
}

.tool-name {
  font-size: 12px;
  font-weight: 500;
  color: #6b7280;
  font-family: monospace;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.step-tokens {
  font-size: 11px;
  color: #9ca3af;
}

.token-label {
  margin-right: 4px;
}

.expand-icon {
  font-size: 10px;
  color: #9ca3af;
}

/* 步骤类型样式 */
.step-user .step-header { background: #f0f9ff; border-left: 3px solid #3b82f6; }
.step-thinking .step-header { background: #fef3c7; border-left: 3px solid #f59e0b; }
.step-text .step-header { background: #f0fdf4; border-left: 3px solid #22c55e; }
.step-toolCall .step-header { background: #f5f3ff; border-left: 3px solid #8b5cf6; }
.step-toolResult .step-header { background: #ecfdf5; border-left: 3px solid #10b981; }
.step-error .step-header { background: #fef2f2; border-left: 3px solid #dc2626; }

.step-toolResult.status-error .step-header { border-left-color: #ef4444; }

/* 内容区域 */
.step-content {
  padding: 0 12px 12px 12px;
  margin-top: -4px;
}

.content-block {
  margin-top: 8px;
}

.content-block pre {
  margin: 0;
  padding: 10px;
  background: rgba(0,0,0,0.03);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
}

.content-block pre.truncated {
  max-height: 200px;
}

.thinking-label {
  font-size: 11px;
  color: #92400e;
  margin-bottom: 6px;
}

.thinking-content pre {
  background: #fffbeb;
  color: #78350f;
}

.section-label {
  font-size: 11px;
  color: #6b7280;
  margin-bottom: 4px;
}

.code-block {
  font-family: 'Monaco', 'Menlo', monospace;
  font-size: 11px;
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.result-status {
  font-size: 12px;
  font-weight: 500;
}

.result-status.ok { color: #059669; }
.result-status.error { color: #dc2626; }

.copy-btn {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid #e5e7eb;
  border-radius: 3px;
  background: #fff;
  cursor: pointer;
}

.copy-btn:hover {
  background: #f3f4f6;
}

.show-more-btn {
  display: block;
  width: 100%;
  margin-top: 8px;
  padding: 6px;
  font-size: 11px;
  color: #6b7280;
  background: rgba(0,0,0,0.02);
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.show-more-btn:hover {
  background: rgba(0,0,0,0.05);
}

/* 错误样式 */
.error-content {
  background: #fef2f2;
  padding: 10px;
  border-radius: 4px;
}

.error-type {
  font-size: 12px;
  font-weight: 600;
  color: #dc2626;
  margin-bottom: 6px;
}

.error-message {
  font-size: 12px;
  color: #7f1d1d;
  padding: 8px;
  background: #fee2e2;
  border-radius: 4px;
  margin-bottom: 8px;
}

.error-suggestion {
  margin-top: 8px;
  padding: 8px;
  background: #fff;
  border-radius: 4px;
}

.suggestion-label {
  font-size: 11px;
  color: #374151;
  margin-bottom: 4px;
}

.error-suggestion ul {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #4b5563;
}

.error-suggestion li {
  margin: 4px 0;
}
</style>
