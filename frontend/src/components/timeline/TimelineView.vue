<template>
  <div class="timeline-view">
    <!-- 头部 -->
    <div class="timeline-header">
      <div class="header-left">
        <span class="title">📊 实时执行时序</span>
        <span class="agent-info" v-if="data">
          {{ data.agentName || data.agentId }}
          <span class="model" v-if="data.model">({{ data.model }})</span>
        </span>
      </div>
      <div class="header-right">
        <span class="status-badge" :class="`status-${statusClass}`">
          {{ statusLabel }}
        </span>
        <button class="refresh-btn" @click="refresh" :disabled="loading">
          {{ loading ? '加载中...' : '🔄 刷新' }}
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading && !data" class="loading-state">
      <div class="spinner"></div>
      <span>加载时序数据...</span>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!data || data.steps.length === 0" class="empty-state">
      <span class="empty-icon">📭</span>
      <span
        v-if="data?.status === 'no_sessions' && data?.isMainAgent"
        class="empty-message"
      >
        主 Agent 暂无会话记录
      </span>
      <span
        v-else-if="data?.status === 'no_sessions'"
        class="empty-message"
      >
        该 Agent 是子代理，暂无独立会话记录
      </span>
      <span v-else>暂无会话记录</span>
      <div v-if="data?.message" class="empty-hint">
        {{ data.message }}
      </div>
    </div>

    <!-- 时序内容 -->
    <div v-else class="timeline-content">
      <!-- 图例 -->
      <div class="timeline-legend">
        <span class="legend-item"><span class="legend-icon">👤</span> 用户/回传</span>
        <span class="legend-item"><span class="legend-icon">🧠</span> LLM 思考</span>
        <span class="legend-item"><span class="legend-icon">🤖</span> LLM 回复</span>
        <span class="legend-item"><span class="legend-icon">🔧</span> 工具调用</span>
        <span class="legend-item"><span class="legend-icon">✅</span> 工具成功</span>
        <span class="legend-item"><span class="legend-icon">❌</span> 工具失败</span>
        <span class="legend-item"><span class="legend-icon">⚠️</span> 错误</span>
      </div>
      <!-- Session 信息 -->
      <div class="session-info" v-if="data.sessionId">
        <span class="session-id">Session: {{ data.sessionId.slice(0, 8) }}...</span>
        <span class="started-at" v-if="data.startedAt">
          开始: {{ formatTime(data.startedAt) }}
        </span>
      </div>

      <!-- 步骤列表 -->
      <div class="steps-list">
        <!-- 轮次分组模式 -->
        <template v-if="useRoundMode">
          <template v-for="(item, index) in renderItems" :key="item.type === 'round' ? (item.data as any).id : (item.data as any).id">
            <TimelineConnector v-if="index > 0" />
            <!-- 轮次 -->
            <TimelineRound
              v-if="item.type === 'round'"
              :round="(item.data as any)"
              :steps="data.steps"
              :highlightedPair="highlightedPair"
              @highlight-pair="handleHighlightPair"
            />
            <!-- 独立步骤（如 toolResult） -->
            <template v-else>
              <!-- 工具执行分隔标签 -->
              <div class="tool-execution-label" v-if="(item.data as any).type === 'toolResult'">
                <span class="label-line"></span>
                <span class="label-text">⚡ 工具执行</span>
                <span class="label-line"></span>
              </div>
              <!-- 连接线（如果 toolResult 有配对的 toolCall） -->
              <TimelineToolLink
                v-if="(item.data as any).type === 'toolResult' && (item.data as any).pairedToolCallId"
                :isError="(item.data as any).toolResultStatus === 'error'"
                :isActive="highlightedPair?.resultId === (item.data as any).id"
                :executionTime="(item.data as any).executionTime"
              />
              <TimelineStepItem
                :step="(item.data as any)"
                :highlightedPair="highlightedPair"
                @toggle-collapse="toggleStepCollapse((item.data as any).id)"
                @highlight-pair="handleHighlightPair"
              />
            </template>
          </template>
        </template>

        <!-- 传统列表模式（无轮次分组时回退） -->
        <template v-else>
          <template v-for="(step, index) in data.steps" :key="step.id">
            <TimelineConnector v-if="index > 0" />
            <TimelineToolLink
              v-if="step.type === 'toolResult' && step.pairedToolCallId"
              :isError="step.toolResultStatus === 'error'"
              :isActive="highlightedPair?.resultId === step.id"
              :executionTime="step.executionTime"
            />
            <TimelineStepItem
              :step="step"
              :prevStep="data.steps[index - 1]"
              :highlightedPair="highlightedPair"
              @toggle-collapse="toggleCollapse(index)"
              @highlight-pair="handleHighlightPair"
            />
          </template>
        </template>
      </div>

      <!-- 统计汇总 -->
      <div class="timeline-footer">
        <div class="stats-grid">
          <div class="stat-item">
            <span class="stat-label">总耗时</span>
            <span class="stat-value">{{ formatDuration(data.stats.totalDuration) }}</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">Token</span>
            <span class="stat-value">
              {{ formatNumber(data.stats.totalInputTokens) }} / {{ formatNumber(data.stats.totalOutputTokens) }}
            </span>
          </div>
          <div class="stat-item">
            <span class="stat-label">工具调用</span>
            <span class="stat-value">{{ data.stats.toolCallCount }} 次</span>
          </div>
          <div class="stat-item">
            <span class="stat-label">步骤数</span>
            <span class="stat-value">{{ data.stats.stepCount }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import type { TimelineResponse, TimelineStep } from './types'
import TimelineStepItem from './TimelineStep.vue'
import TimelineConnector from './TimelineConnector.vue'
import TimelineRound from './TimelineRound.vue'
import TimelineToolLink from './TimelineToolLink.vue'

const props = defineProps<{
  agentId: string
  sessionKey?: string
  autoRefresh?: boolean
  refreshInterval?: number
}>()

const data = ref<TimelineResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

// 高亮配对状态
const highlightedPair = ref<{ callId: string; resultId: string } | null>(null)

const statusClass = computed(() => {
  if (!data.value) return 'empty'
  return data.value.status
})

const statusLabel = computed(() => {
  const labels: Record<string, string> = {
    running: '🔄 进行中',
    completed: '✅ 已完成',
    error: '❌ 出错',
    empty: '空',
    no_sessions: '无会话'
  }
  return labels[statusClass.value] || '未知'
})

// 是否启用轮次分组模式
const useRoundMode = computed(() => {
  return data.value?.roundMode && data.value.rounds && data.value.rounds.length > 0
})

// stepId -> 轮次（避免对每个 step 做 rounds.find）
const stepIdToRound = computed(() => {
  const m = new Map<string, { id: string; stepIds: string[]; [k: string]: unknown }>()
  if (!data.value?.rounds) return m
  for (const r of data.value.rounds) {
    for (const id of r.stepIds) {
      m.set(id, r)
    }
  }
  return m
})

// 获取不属于任何轮次的步骤（如 toolResult）
const standaloneSteps = computed(() => {
  if (!data.value || !useRoundMode.value) return []

  const roundStepIds = new Set<string>()
  data.value.rounds.forEach(round => {
    round.stepIds.forEach(id => roundStepIds.add(id))
  })

  return data.value.steps.filter(step => !roundStepIds.has(step.id))
})

// 构建渲染项列表（轮次或独立步骤）
const renderItems = computed(() => {
  if (!data.value || !useRoundMode.value) return []

  const items: Array<{ type: 'round' | 'step', data: unknown }> = []
  const renderedStepIds = new Set<string>()

  // 遍历所有步骤，按顺序构建渲染项
  for (const step of data.value.steps) {
    // 如果已经在某个轮次中渲染过，跳过
    if (renderedStepIds.has(step.id)) continue

    const round = stepIdToRound.value.get(step.id)

    if (round) {
      // 渲染整个轮次
      items.push({ type: 'round', data: round })
      round.stepIds.forEach(id => renderedStepIds.add(id))
    } else {
      // 独立步骤（如 toolResult）
      items.push({ type: 'step', data: step })
      renderedStepIds.add(step.id)
    }
  }

  return items
})

async function refresh() {
  if (!props.agentId) return
  loading.value = true
  error.value = null

  try {
    let url = `/api/timeline/${props.agentId}?limit=100`
    if (props.sessionKey) {
      url += `&session_key=${encodeURIComponent(props.sessionKey)}`
    }

    const res = await fetch(url)
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`)
    }
    data.value = await res.json()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
    console.error('Timeline load error:', e)
  } finally {
    loading.value = false
  }
}

function toggleCollapse(index: number) {
  if (data.value && data.value.steps[index]) {
    data.value.steps[index].collapsed = !data.value.steps[index].collapsed
  }
}

function toggleStepCollapse(stepId: string) {
  if (data.value) {
    const step = data.value.steps.find(s => s.id === stepId)
    if (step) {
      step.collapsed = !step.collapsed
    }
  }
}

function handleHighlightPair(pair: { callId: string; resultId: string }) {
  highlightedPair.value = pair
  // 3秒后取消高亮
  setTimeout(() => {
    highlightedPair.value = null
  }, 3000)
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

function formatNumber(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

// 初始加载
onMounted(refresh)

// 监听 agentId 变化
watch(() => props.agentId, refresh)

// 自动刷新
let refreshTimer: ReturnType<typeof setInterval> | null = null
watch([() => props.autoRefresh, () => props.refreshInterval], ([auto, interval]) => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
  if (auto && interval && interval > 0) {
    refreshTimer = setInterval(refresh, interval * 1000)
  }
}, { immediate: true })
</script>

<style scoped>
.timeline-view {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  font-weight: 600;
  font-size: 14px;
  color: #374151;
}

.agent-info {
  font-size: 13px;
  color: #6b7280;
}

.agent-info .model {
  color: #9ca3af;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-badge {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
}

.status-badge.status-running {
  background: #fef3c7;
  color: #92400e;
}

.status-badge.status-completed {
  background: #d1fae5;
  color: #065f46;
}

.status-badge.status-error {
  background: #fee2e2;
  color: #991b1b;
}

.status-badge.status-no_sessions {
  background: #f3f4f6;
  color: #6b7280;
}

.refresh-btn {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: #374151;
}

.refresh-btn:hover:not(:disabled) {
  background: #f3f4f6;
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
  color: #6b7280;
  gap: 12px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #e5e7eb;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 32px;
}

.empty-message {
  font-size: 14px;
  color: #374151;
  font-weight: 500;
}

.empty-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
  text-align: center;
  max-width: 280px;
  line-height: 1.5;
}

.timeline-content {
  padding: 16px;
}

.timeline-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 20px;
  font-size: 11px;
  color: #6b7280;
  margin-bottom: 12px;
  padding: 8px 10px;
  background: #f9fafb;
  border-radius: 6px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.legend-icon {
  font-size: 12px;
}

.session-info {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #9ca3af;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px dashed #e5e7eb;
}

.steps-list {
  display: flex;
  flex-direction: column;
}

.tool-execution-label {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
  padding: 0 4px;
}

.tool-execution-label .label-line {
  flex: 1;
  height: 1px;
  background: #e5e7eb;
}

.tool-execution-label .label-text {
  font-size: 11px;
  color: #9ca3af;
  white-space: nowrap;
}

.timeline-footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px;
  background: #f9fafb;
  border-radius: 6px;
}

.stat-label {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 4px;
}

.stat-value {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}
</style>
