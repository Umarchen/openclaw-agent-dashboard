<template>
  <div class="error-analysis-view">
    <div class="header">
      <h3>🔍 错误分析</h3>
      <button class="refresh-btn" @click="loadAnalysis" :disabled="loading">
        {{ loading ? '分析中...' : '刷新' }}
      </button>
    </div>

    <!-- 当前 Agent 统计 -->
    <div v-if="summary" class="agent-summary">
      <div class="summary-card total">
        <span class="count">{{ summary.total || 0 }}</span>
        <span class="label">错误数</span>
      </div>
      <div class="summary-card critical" v-if="summary.bySeverity?.critical">
        <span class="count">{{ summary.bySeverity.critical }}</span>
        <span class="label">严重</span>
      </div>
      <div class="summary-card high" v-if="summary.bySeverity?.high">
        <span class="count">{{ summary.bySeverity.high }}</span>
        <span class="label">高</span>
      </div>
      <div class="summary-card medium" v-if="summary.bySeverity?.medium">
        <span class="count">{{ summary.bySeverity.medium }}</span>
        <span class="label">中</span>
      </div>
    </div>

    <div v-if="loading && !errors.length" class="loading-state">
      正在分析错误...
    </div>

    <div v-else-if="!errors.length" class="empty-state">
      ✅ 暂无错误记录
    </div>

    <!-- 错误列表 -->
    <div v-else class="errors-list">
      <div
        v-for="(error, idx) in errors"
        :key="idx"
        class="error-item"
        :class="`severity-${error.severity}`"
        @click="toggleError(idx)"
      >
        <div class="error-header">
          <span class="error-type" :style="{ color: error.severityColor }">
            {{ error.severityLabel }} - {{ error.errorTypeLabel }}
          </span>
          <div class="error-badges">
            <span v-if="error.isArchived" class="badge archived" title="已归档的子任务">📦 归档</span>
            <span v-if="error.provider" class="badge provider">{{ error.provider }}</span>
            <span v-if="error.model" class="badge model">{{ error.model }}</span>
          </div>
          <span class="error-time">{{ formatTime(error.timestamp) }}</span>
        </div>
        <div class="error-message">{{ truncate(error.rawMessage, 150) }}</div>

        <!-- 错误详情 -->
        <div v-if="expandedErrors.has(idx)" class="error-detail">
          <div class="detail-section">
            <h4>错误信息</h4>
            <pre class="error-full">{{ error.rawMessage || '无详细信息' }}</pre>
          </div>

          <div v-if="error.toolChain?.length" class="detail-section">
            <h4>工具调用链（错误前）</h4>
            <div class="tool-chain">
              <div v-for="(tool, tIdx) in error.toolChain" :key="tIdx" class="tool-item">
                <span class="tool-index">{{ tIdx + 1 }}</span>
                <span class="tool-name">{{ tool.toolName }}</span>
                <span class="tool-time">{{ formatTime(tool.timestamp) }}</span>
              </div>
            </div>
          </div>

          <div v-if="error.suggestions?.length" class="detail-section">
            <h4>修复建议</h4>
            <ul class="suggestions">
              <li v-for="(s, sIdx) in error.suggestions" :key="sIdx">{{ s }}</li>
            </ul>
          </div>

          <div class="detail-section meta">
            <span>Session: {{ error.sessionFile }}</span>
            <span>Turn: {{ error.turnIndex }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 按类型统计 -->
    <div v-if="summary?.byType && Object.keys(summary.byType).length > 0" class="type-summary">
      <h4>错误类型分布</h4>
      <div class="type-bars">
        <div v-for="(count, type) in summary.byType" :key="type" class="type-bar">
          <span class="type-label">{{ getTypeLabel(type as string) }}</span>
          <div class="bar-container">
            <div class="bar-fill" :style="{ width: getBarWidth(count, summary.total) }"></div>
          </div>
          <span class="type-count">{{ count }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'

interface ErrorSummary {
  total: number
  byType: Record<string, number>
  bySeverity: Record<string, number>
}

interface ErrorItem {
  turnIndex: number
  timestamp: number
  rawMessage: string
  errorType: string
  errorTypeLabel: string
  severity: string
  severityLabel: string
  severityColor: string
  suggestions: string[]
  toolChain?: any[]
  sessionFile: string
  isArchived?: boolean
  provider?: string
  model?: string
}

const props = defineProps<{
  agentId: string
}>()

const errors = ref<ErrorItem[]>([])
const summary = ref<ErrorSummary | null>(null)
const loading = ref(false)
const expandedErrors = ref(new Set<number>())

const typeLabels: Record<string, string> = {
  api_auth: 'API 认证',
  api_rate_limit: 'API 限流',
  api_model: '模型错误',
  timeout: '超时',
  permission: '权限错误',
  tool_error: '工具错误',
  subagent: '子任务错误',
  network: '网络错误',
  unknown: '未知',
}

function getTypeLabel(type: string): string {
  return typeLabels[type] || type
}

function formatTime(ts: number | undefined): string {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function truncate(s: string, max: number): string {
  if (!s || s.length <= max) return s || ''
  return s.slice(0, max) + '...'
}

function getBarWidth(count: number, total: number): string {
  if (!total) return '0%'
  return Math.round((count / total) * 100) + '%'
}

function toggleError(idx: number) {
  if (expandedErrors.value.has(idx)) {
    expandedErrors.value.delete(idx)
  } else {
    expandedErrors.value.add(idx)
  }
  expandedErrors.value = new Set(expandedErrors.value)
}

async function loadAnalysis() {
  if (!props.agentId) return

  loading.value = true
  try {
    const res = await fetch(`/api/error-analysis/${props.agentId}?session_limit=5`)
    if (res.ok) {
      const data = await res.json()
      errors.value = data.errors || []
      summary.value = data.summary || null
    }
  } catch (e) {
    console.error('Failed to load error analysis:', e)
  } finally {
    loading.value = false
  }
}

watch(() => props.agentId, () => {
  loadAnalysis()
}, { immediate: true })

onMounted(() => {
  loadAnalysis()
})
</script>

<style scoped>
.error-analysis-view {
  padding: 12px;
  max-height: 600px;
  overflow-y: auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.header h3 {
  margin: 0;
  font-size: 14px;
  color: #374151;
}

.refresh-btn {
  padding: 4px 12px;
  font-size: 12px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}

.refresh-btn:hover:not(:disabled) {
  background: #f3f4f6;
}

.refresh-btn:disabled {
  opacity: 0.5;
}

.agent-summary {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.summary-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px 16px;
  background: #f9fafb;
  border-radius: 8px;
  min-width: 70px;
}

.summary-card.total {
  background: #eff6ff;
}

.summary-card.total .count {
  color: #3b82f6;
}

.summary-card.critical {
  background: #fef2f2;
}

.summary-card.critical .count {
  color: #dc2626;
}

.summary-card.high {
  background: #fff7ed;
}

.summary-card.high .count {
  color: #f97316;
}

.summary-card.medium {
  background: #fffbeb;
}

.summary-card.medium .count {
  color: #f59e0b;
}

.summary-card .count {
  font-size: 20px;
  font-weight: 700;
}

.summary-card .label {
  font-size: 10px;
  color: #6b7280;
  margin-top: 2px;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: #6b7280;
}

.errors-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.error-item {
  padding: 10px;
  background: #fff;
  border-radius: 6px;
  border-left: 3px solid #e5e7eb;
  cursor: pointer;
}

.error-item.severity-critical {
  border-left-color: #dc2626;
  background: #fef2f2;
}

.error-item.severity-high {
  border-left-color: #f97316;
  background: #fff7ed;
}

.error-item.severity-medium {
  border-left-color: #f59e0b;
  background: #fffbeb;
}

.error-item.severity-low {
  border-left-color: #6b7280;
}

.error-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  flex-wrap: wrap;
  gap: 4px;
}

.error-type {
  font-weight: 600;
  font-size: 13px;
}

.error-badges {
  display: flex;
  gap: 4px;
}

.badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  background: #e5e7eb;
  color: #6b7280;
}

.badge.archived {
  background: #fef3c7;
  color: #92400e;
}

.badge.provider {
  background: #dbeafe;
  color: #1d4ed8;
}

.badge.model {
  background: #f3e8ff;
  color: #7c3aed;
  font-family: monospace;
}

.error-time {
  font-size: 11px;
  color: #9ca3af;
}

.error-message {
  font-size: 12px;
  color: #4b5563;
  line-height: 1.4;
}

.error-detail {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

.detail-section {
  margin-bottom: 12px;
}

.detail-section:last-child {
  margin-bottom: 0;
}

.detail-section h4 {
  margin: 0 0 8px 0;
  font-size: 12px;
  color: #374151;
}

.error-full {
  margin: 0;
  padding: 10px;
  background: #1f2937;
  color: #e5e7eb;
  border-radius: 6px;
  font-size: 11px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 150px;
}

.tool-chain {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #f3f4f6;
  border-radius: 4px;
  font-size: 12px;
}

.tool-index {
  width: 20px;
  height: 20px;
  background: #3b82f6;
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
}

.tool-name {
  flex: 1;
  font-family: monospace;
  color: #1f2937;
}

.tool-time {
  font-size: 10px;
  color: #9ca3af;
}

.suggestions {
  margin: 0;
  padding-left: 18px;
}

.suggestions li {
  margin: 6px 0;
  font-size: 12px;
  color: #4b5563;
}

.detail-section.meta {
  display: flex;
  gap: 16px;
  font-size: 10px;
  color: #9ca3af;
  font-family: monospace;
}

.type-summary {
  padding-top: 16px;
  border-top: 1px solid #e5e7eb;
}

.type-summary h4 {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: #374151;
}

.type-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.type-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.type-label {
  width: 80px;
  font-size: 11px;
  color: #6b7280;
}

.bar-container {
  flex: 1;
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: #3b82f6;
  border-radius: 4px;
  transition: width 0.3s;
}

.type-count {
  width: 30px;
  font-size: 11px;
  color: #374151;
  text-align: right;
}
</style>
