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
      <span v-if="data?.status === 'no_sessions'" class="empty-message">
        该 Agent 是子代理，暂无独立会话记录
      </span>
      <span v-else>暂无会话记录</span>
      <div v-if="data?.message" class="empty-hint">
        {{ data.message }}
      </div>
    </div>

    <!-- 时序内容 -->
    <div v-else class="timeline-content">
      <!-- Session 信息 -->
      <div class="session-info" v-if="data.sessionId">
        <span class="session-id">Session: {{ data.sessionId.slice(0, 8) }}...</span>
        <span class="started-at" v-if="data.startedAt">
          开始: {{ formatTime(data.startedAt) }}
        </span>
      </div>

      <!-- 步骤列表 -->
      <div class="steps-list">
        <template v-for="(step, index) in data.steps" :key="step.id">
          <!-- 连接线 -->
          <TimelineConnector v-if="index > 0" />
          <!-- 步骤 -->
          <TimelineStepItem
            :step="step"
            :prevStep="data.steps[index - 1]"
            @toggle-collapse="toggleCollapse(index)"
          />
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
import type { TimelineResponse } from './types'
import TimelineStepItem from './TimelineStep.vue'
import TimelineConnector from './TimelineConnector.vue'

const props = defineProps<{
  agentId: string
  sessionKey?: string
  autoRefresh?: boolean
  refreshInterval?: number
}>()

const data = ref<TimelineResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

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
