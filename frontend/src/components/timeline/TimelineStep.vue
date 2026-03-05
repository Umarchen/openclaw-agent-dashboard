<template>
  <div
    class="timeline-step"
    :class="[
      `step-${step.type}`,
      `status-${step.status}`,
      { 'is-paired-result': isPairedToolResult, 'highlighted': isHighlighted }
    ]"
  >
    <!-- 步骤头部 -->
    <div class="step-header" @click="handleClick">
      <div class="header-left">
        <span class="step-icon">{{ stepIcon }}</span>
        <span class="step-type">{{ stepLabel }}</span>
        <span class="step-subtitle" v-if="stepSubtitle">{{ stepSubtitle }}</span>
        <span class="collapse-summary" v-if="!isExpanded && collapseSummary">{{ collapseSummary }}</span>
        <span class="step-time">{{ formatTime(step.timestamp) }}</span>
        <span class="step-duration" v-if="step.duration && step.duration > 0">
          +{{ formatDuration(step.duration) }}
        </span>
        <!-- 工具执行时间 -->
        <span class="execution-time" v-if="step.executionTime">
          ⏱ {{ formatDuration(step.executionTime) }}
        </span>
      </div>
      <div class="header-right">
        <span class="step-tokens" v-if="step.tokens">
          <span class="token-label">tokens:</span>
          {{ step.tokens.input + step.tokens.output }}
        </span>
        <span class="pair-indicator" v-if="hasPair" :title="pairTitle">
          🔗
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
            {{ step.toolResultStatus === 'ok' ? '✅ 成功' : '❌ 工具执行失败' }}
          </span>
          <button class="copy-btn" @click="copyResult" v-if="step.toolResult">
            复制
          </button>
        </div>
        <!-- 失败时优先展示错误信息与建议 -->
        <template v-if="step.toolResultStatus === 'error'">
          <div class="tool-error-section" v-if="toolResultErrorDisplay">
            <div class="tool-error-message">{{ toolResultErrorDisplay }}</div>
            <div class="tool-error-suggestion" v-if="toolResultErrorSuggestion">
              <span class="suggestion-label">💡 建议:</span>
              <ul>
                <li v-for="(s, i) in toolResultErrorSuggestion" :key="i">{{ s }}</li>
              </ul>
            </div>
          </div>
          <div class="result-body" v-if="step.toolResult">
            <div class="section-label">原始返回:</div>
            <pre :class="{ truncated: !showFullResult }">{{ displayResult }}</pre>
            <button
              v-if="isResultLong"
              class="show-more-btn"
              @click.stop="showFullResult = !showFullResult"
            >
              {{ showFullResult ? '收起' : `展开全部 (${resultLineCount} 行)` }}
            </button>
          </div>
        </template>
        <template v-else>
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
        </template>
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
import { stepConfig, getUserStepLabel } from './types'

const props = defineProps<{
  step: TimelineStep
  prevStep?: TimelineStep
  highlightedPair?: { callId: string; resultId: string } | null
}>()

const emit = defineEmits<{
  'toggle-collapse': []
  'highlight-pair': [pair: { callId: string; resultId: string }]
}>()

const isExpanded = ref(!props.step.collapsed)
const showFullResult = ref(false)

const stepIcon = computed(() => {
  return stepConfig[props.step.type as StepType]?.icon || '📄'
})

const stepLabel = computed(() => {
  // 对于 user 类型，如果有发送者信息，显示发送者名称
  if (props.step.type === 'user') {
    return getUserStepLabel(props.step)
  }
  // toolCall: "Read 调用" 等
  if (props.step.type === 'toolCall') {
    return `${props.step.toolName || '工具'} 调用`
  }
  // toolResult: "Read 结果" 或 "Read 失败"
  if (props.step.type === 'toolResult') {
    const name = props.step.toolName || '工具'
    const suffix = props.step.toolResultStatus === 'ok' ? '结果' : '失败'
    return `${name} ${suffix}`
  }
  return stepConfig[props.step.type as StepType]?.label || props.step.type
})

/** thinking/text 的副标题，标注为 LLM 输出 */
const stepSubtitle = computed(() => {
  if (props.step.type === 'thinking') return 'LLM 推理'
  if (props.step.type === 'text') return 'LLM 输出'
  return ''
})

/** 是否有配对的工具调用/结果 */
const hasPair = computed(() => {
  return !!(props.step.pairedToolCallId || props.step.pairedToolResultId)
})

/** 是否是配对的 toolResult（用于缩进显示） */
const isPairedToolResult = computed(() => {
  return props.step.type === 'toolResult' && props.step.pairedToolCallId
})

/** 是否高亮 */
const isHighlighted = computed(() => {
  if (!props.highlightedPair || !hasPair.value) return false
  const { callId, resultId } = props.highlightedPair
  return props.step.id === callId || props.step.id === resultId
})

/** 配对提示 */
const pairTitle = computed(() => {
  if (props.step.type === 'toolCall' && props.step.pairedToolResultId) {
    return '点击高亮对应结果'
  }
  if (props.step.type === 'toolResult' && props.step.pairedToolCallId) {
    return '点击高亮对应调用'
  }
  return ''
})

const hasExpandableContent = computed(() => {
  const { type, content, thinking, toolArguments, toolResult, errorMessage } = props.step
  return content || thinking || toolArguments || toolResult || errorMessage
})

/** 折叠时在头部显示的摘要 */
const collapseSummary = computed(() => {
  const s = props.step
  if (s.type === 'toolCall' && s.toolArguments) {
    const path = s.toolArguments.path ?? s.toolArguments.file_path ?? s.toolArguments.filePath
    if (typeof path === 'string') return path
    const pattern = s.toolArguments.pattern
    if (typeof pattern === 'string') return pattern
    const cmd = s.toolArguments.command
    if (typeof cmd === 'string') return cmd.length > 40 ? cmd.slice(0, 40) + '…' : cmd
  }
  if (s.type === 'toolResult') {
    if (s.toolResultStatus === 'error') {
      const err = (s.toolResultError || s.toolResult || '').slice(0, 30)
      return err ? `${err}${err.length >= 30 ? '…' : ''}` : '失败'
    }
    if (s.toolResult) {
      const lines = s.toolResult.split('\n').length
      return lines > 1 ? `${lines} 行` : ''
    }
  }
  if (s.type === 'thinking' && s.thinking) {
    const len = s.thinking.length
    return len > 0 ? `约 ${len} 字` : ''
  }
  if (s.type === 'text' && s.content) {
    const len = s.content.length
    return len > 0 ? `约 ${len} 字` : ''
  }
  return ''
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

/** 工具失败时的错误信息展示（优先用 toolResultError，否则从 toolResult 提取） */
const toolResultErrorDisplay = computed(() => {
  if (props.step.type !== 'toolResult' || props.step.toolResultStatus !== 'error') return ''
  if (props.step.toolResultError) return props.step.toolResultError
  return props.step.toolResult || '工具执行失败'
})

/** 工具失败时的建议（根据错误内容推断） */
const toolResultErrorSuggestion = computed(() => {
  if (props.step.type !== 'toolResult' || props.step.toolResultStatus !== 'error') return null
  const text = (props.step.toolResultError || props.step.toolResult || '').toLowerCase()
  const toolName = (props.step.toolName || '').toLowerCase()

  const suggestions: string[] = []
  if (text.includes('enoent') || text.includes('no such file') || text.includes('文件不存在')) {
    suggestions.push('检查文件路径是否正确', '确认文件是否存在')
  }
  if (text.includes('eacces') || text.includes('permission') || text.includes('权限')) {
    suggestions.push('检查文件/目录权限', '确认当前用户有访问权限')
  }
  if (text.includes('timeout') || text.includes('超时')) {
    suggestions.push('增加超时时间', '简化任务或检查网络')
  }
  if (toolName === 'read' && suggestions.length === 0) {
    suggestions.push('检查路径是否在 workspace 内', '确认文件编码正确')
  }
  if (toolName.includes('bash') && suggestions.length === 0) {
    suggestions.push('检查命令语法', '确认依赖已安装', '查看退出码')
  }
  if (suggestions.length === 0) {
    suggestions.push('查看原始返回详情', '尝试调整参数后重试')
  }
  return suggestions
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

function handleClick() {
  // 如果有配对关系，触发高亮事件
  if (hasPair.value) {
    const callId = props.step.pairedToolCallId || props.step.id
    const resultId = props.step.pairedToolResultId || props.step.id
    emit('highlight-pair', { callId, resultId })
  }
  toggleExpand()
}

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

.step-subtitle {
  font-size: 10px;
  color: #9ca3af;
  background: rgba(0,0,0,0.04);
  padding: 1px 6px;
  border-radius: 3px;
  flex-shrink: 0;
}

.collapse-summary {
  font-size: 11px;
  color: #9ca3af;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.execution-time {
  font-size: 10px;
  color: #64748b;
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 3px;
}

.pair-indicator {
  font-size: 10px;
  cursor: pointer;
  opacity: 0.6;
  transition: opacity 0.2s;
}

.pair-indicator:hover {
  opacity: 1;
}

/* 步骤类型样式 */
.step-user .step-header { background: #f0f9ff; border-left: 3px solid #3b82f6; }
.step-thinking .step-header { background: #fef3c7; border-left: 3px solid #f59e0b; }
.step-text .step-header { background: #f0fdf4; border-left: 3px solid #22c55e; }
.step-toolCall .step-header { background: #f5f3ff; border-left: 3px solid #8b5cf6; }
.step-toolResult .step-header { background: #ecfdf5; border-left: 3px solid #10b981; }
.step-error .step-header { background: #fef2f2; border-left: 3px solid #dc2626; }

.step-toolResult.status-error .step-header { border-left-color: #ef4444; }

/* 配对 toolResult 缩进 */
.is-paired-result {
  margin-left: 20px;
  border-left: 2px dashed #d1d5db !important;
  border-radius: 0 6px 6px 0;
}

/* 高亮样式 */
.timeline-step.highlighted {
  box-shadow: 0 0 0 2px #3b82f6;
  transform: scale(1.01);
  transition: all 0.2s ease;
}

.timeline-step.highlighted .step-header {
  background: #eff6ff !important;
}

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

.tool-error-section {
  margin-bottom: 12px;
  padding: 10px;
  background: #fef2f2;
  border-radius: 4px;
  border-left: 3px solid #ef4444;
}

.tool-error-message {
  font-size: 12px;
  color: #991b1b;
  line-height: 1.5;
  word-break: break-word;
}

.tool-error-suggestion {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #fecaca;
}

.tool-error-suggestion .suggestion-label {
  font-size: 11px;
  color: #374151;
  margin-bottom: 4px;
}

.tool-error-suggestion ul {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #4b5563;
}

.tool-error-suggestion li {
  margin: 2px 0;
}

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
