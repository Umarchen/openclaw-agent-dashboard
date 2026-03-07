<template>
  <section class="error-center">
    <div class="header">
      <h2>错误中心</h2>
      <div class="header-actions">
        <select v-model="selectedAgent" @change="loadData" class="filter-select">
          <option value="">全部 Agent</option>
          <option v-for="agent in agents" :key="agent.id" :value="agent.id">
            {{ agent.name }}
          </option>
        </select>
        <select v-model="selectedType" @change="loadData" class="filter-select">
          <option value="">全部类型</option>
          <option v-for="(info, type) in errorTypes" :key="type" :value="type">
            {{ info.label }}
          </option>
        </select>
        <button @click="loadData" class="refresh-btn">刷新</button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card total">
        <div class="stat-value">{{ stats.totalCount }}</div>
        <div class="stat-label">总错误数</div>
      </div>
      <div class="stat-card session">
        <div class="stat-value">{{ stats.sessionErrorCount }}</div>
        <div class="stat-label">Session 错误</div>
      </div>
      <div class="stat-card model">
        <div class="stat-value">{{ stats.modelFailureCount }}</div>
        <div class="stat-label">Model 错误</div>
      </div>
      <div class="stat-card" :class="healthyApiCount === apiStatus.length ? 'healthy' : 'warning'">
        <div class="stat-value">{{ healthyApiCount }}/{{ apiStatus.length }}</div>
        <div class="stat-label">API 健康</div>
      </div>
    </div>

    <!-- 趋势图 -->
    <div class="trend-section" v-if="stats.hourlyTrend?.length">
      <h3>24 小时错误趋势</h3>
      <div class="trend-chart">
        <div
          v-for="(item, i) in stats.hourlyTrend"
          :key="i"
          class="trend-bar"
          :style="{ height: getBarHeight(item.count) + '%' }"
          :title="`${item.hour}: ${item.count} 个错误`"
        >
          <span v-if="item.count > 0" class="bar-label">{{ item.count }}</span>
        </div>
      </div>
      <div class="trend-labels">
        <span v-for="(item, i) in stats.hourlyTrend" :key="i" class="trend-time">
          {{ i % 4 === 0 ? formatHour(item.hour) : '' }}
        </span>
      </div>
    </div>

    <!-- 错误类型分布 -->
    <div class="type-distribution" v-if="Object.keys(stats.byType || {}).length">
      <h3>错误类型分布</h3>
      <div class="type-bars">
        <div
          v-for="(info, type) in stats.byType"
          :key="type"
          class="type-bar-item"
        >
          <div class="type-bar-label">
            <span class="type-dot" :style="{ background: info.color }"></span>
            {{ info.label }}
          </div>
          <div class="type-bar-track">
            <div
              class="type-bar-fill"
              :style="{
                width: getTypePercent(info.count) + '%',
                background: info.color
              }"
            ></div>
          </div>
          <span class="type-count">{{ info.count }}</span>
        </div>
      </div>
    </div>

    <!-- API 状态 -->
    <div class="api-status-section" v-if="apiStatus.length">
      <h3>API 状态</h3>
      <div class="api-status-grid">
        <div
          v-for="api in apiStatus"
          :key="api.model"
          class="api-status-card"
          :class="`status-${api.status}`"
        >
          <div class="api-header">
            <span class="api-model">{{ api.model }}</span>
            <span class="api-provider">{{ api.provider }}</span>
          </div>
          <div class="api-status">
            <span class="status-dot" :class="`status-${api.status}`"></span>
            <span class="status-text">{{ getStatusText(api.status) }}</span>
          </div>
          <div v-if="api.lastError" class="api-last-error">
            <span class="error-type">{{ api.lastError.type }}</span>
            <span class="error-time">{{ formatTime(api.lastError.timestamp) }}</span>
          </div>
          <div v-if="api.errorCount > 0" class="api-error-count">
            错误: {{ api.errorCount }} 次
          </div>
        </div>
      </div>
    </div>

    <!-- 错误列表 -->
    <div class="error-lists">
      <!-- Session 错误 -->
      <div class="error-group">
        <h3>Session 错误 <span class="count-badge">{{ sessionErrors.length }}</span></h3>
        <div v-if="!sessionErrors.length" class="empty">暂无错误</div>
        <div v-else class="error-list">
          <div
            v-for="e in sessionErrors"
            :key="e.id"
            class="error-item"
            :class="`severity-${e.severity}`"
            @click="toggleDetail(e.id)"
          >
            <div class="error-main">
              <span class="error-agent">{{ getAgentName(e.agentId) }}</span>
              <span class="error-type" :style="{ color: getTypeColor(e.type) }">
                {{ e.typeLabel }}
              </span>
              <span class="error-msg">{{ truncate(e.message, 80) }}</span>
              <span class="error-time">{{ formatTime(e.timestamp) }}</span>
              <span class="expand-icon">{{ expandedId === e.id ? '▼' : '▶' }}</span>
            </div>
            <div v-if="expandedId === e.id" class="error-detail">
              <div class="detail-row">
                <span class="detail-label">时间:</span>
                <span>{{ e.datetime }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">完整信息:</span>
                <span class="detail-message">{{ e.fullMessage || e.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Model Failures -->
      <div class="error-group">
        <h3>Model Failures <span class="count-badge">{{ modelFailures.length }}</span></h3>
        <div v-if="!modelFailures.length" class="empty">暂无错误</div>
        <div v-else class="error-list">
          <div
            v-for="f in modelFailures"
            :key="f.id"
            class="error-item"
            :class="`severity-${f.severity}`"
            @click="toggleDetail(f.id)"
          >
            <div class="error-main">
              <span class="error-agent">{{ f.model }}</span>
              <span class="error-type" :style="{ color: getTypeColor(f.type) }">
                {{ f.typeLabel }}
              </span>
              <span class="error-msg">{{ truncate(f.message, 80) }}</span>
              <span class="error-time">{{ formatTime(f.timestamp) }}</span>
              <span class="expand-icon">{{ expandedId === f.id ? '▼' : '▶' }}</span>
            </div>
            <div v-if="expandedId === f.id" class="error-detail">
              <div class="detail-row">
                <span class="detail-label">时间:</span>
                <span>{{ f.datetime }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">完整信息:</span>
                <span class="detail-message">{{ f.fullMessage || f.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

interface SessionError {
  id: string
  source: string
  agentId: string
  type: string
  typeLabel: string
  severity: string
  message: string
  fullMessage: string
  timestamp: number
  datetime: string
}

interface ModelFailure {
  id: string
  source: string
  model: string
  type: string
  typeLabel: string
  severity: string
  message: string
  fullMessage: string
  timestamp: number
  datetime: string
}

interface ApiStatus {
  model: string
  provider: string
  status: string
  errorCount: number
  lastError?: { type: string; message: string; timestamp: number }
}

interface Stats {
  totalCount: number
  sessionErrorCount: number
  modelFailureCount: number
  byType: Record<string, { count: number; label: string; color: string }>
  byAgent: Record<string, { count: number; agentId: string }>
  hourlyTrend: Array<{ hour: string; count: number }>
}

const sessionErrors = ref<SessionError[]>([])
const modelFailures = ref<ModelFailure[]>([])
const apiStatus = ref<ApiStatus[]>([])
const stats = ref<Stats>({
  totalCount: 0,
  sessionErrorCount: 0,
  modelFailureCount: 0,
  byType: {},
  byAgent: {},
  hourlyTrend: []
})

const loading = ref(false)
const error = ref('')
const expandedId = ref<string | null>(null)
const selectedAgent = ref('')
const selectedType = ref('')
const agents = ref<Array<{ id: string; name: string }>>([])

const errorTypes: Record<string, { label: string; color: string }> = {
  'rate-limit': { label: 'Rate Limit', color: '#f59e0b' },
  'token-limit': { label: 'Token 超限', color: '#8b5cf6' },
  'timeout': { label: '超时', color: '#ef4444' },
  'auth': { label: '认证失败', color: '#dc2626' },
  'unknown': { label: '未知错误', color: '#6b7280' },
}

const healthyApiCount = computed(() => {
  return apiStatus.value.filter(a => a.status === 'healthy').length
})

const maxHourlyCount = computed(() => {
  return Math.max(...(stats.value.hourlyTrend?.map(h => h.count) || [1]), 1)
})

function getBarHeight(count: number): number {
  return (count / maxHourlyCount.value) * 100
}

function getTypePercent(count: number): number {
  const total = stats.value.totalCount || 1
  return (count / total) * 100
}

function getTypeColor(type: string): string {
  return errorTypes[type]?.color || '#6b7280'
}

function formatHour(hourStr: string): string {
  const match = hourStr.match(/(\d{2}):00/)
  return match ? match[1] + 'h' : ''
}

function formatTime(ts: number): string {
  if (!ts) return '-'
  const now = Date.now()
  const diff = now - ts
  const minutes = Math.floor(diff / 60000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  return `${Math.floor(hours / 24)}天前`
}

function truncate(str: string, len: number): string {
  if (!str) return '-'
  return str.length > len ? str.slice(0, len) + '...' : str
}

function getStatusText(status: string): string {
  const map: Record<string, string> = {
    'healthy': '正常',
    'degraded': '降级',
    'down': '异常'
  }
  return map[status] || '未知'
}

function getAgentName(agentId: string): string {
  const agent = agents.value.find(a => a.id === agentId)
  return agent ? agent.name : agentId
}

function toggleDetail(id: string): void {
  expandedId.value = expandedId.value === id ? null : id
}

async function loadAgents(): Promise<void> {
  try {
    const res = await fetch('/api/agents')
    if (res.ok) {
      const data = await res.json()
      agents.value = (Array.isArray(data) ? data : []).map((a: any) => ({
        id: a.id,
        name: a.name || a.id
      }))
    }
  } catch (e) {
    console.error('Failed to load agents:', e)
  }
}

async function loadData(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams()
    if (selectedAgent.value) params.set('agent', selectedAgent.value)
    if (selectedType.value) params.set('type', selectedType.value)

    // 并行请求
    const [summaryRes, statsRes] = await Promise.all([
      fetch(`/api/errors/summary?${params.toString()}`),
      fetch('/api/errors/stats')
    ])

    if (summaryRes.ok) {
      const data = await summaryRes.json()
      sessionErrors.value = data.sessionErrors || []
      modelFailures.value = data.modelFailures || []
      apiStatus.value = data.apiStatus || []
    }

    if (statsRes.ok) {
      stats.value = await statsRes.json()
    }
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadAgents()
  loadData()
})
</script>

<style scoped>
.error-center {
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.header h2 {
  margin: 0;
  font-size: 1.3rem;
  color: #333;
}

.header-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.filter-select {
  padding: 0.5rem 0.75rem;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: white;
  font-size: 0.9rem;
  min-width: 120px;
}

.refresh-btn {
  padding: 0.5rem 1rem;
  background: #4a9eff;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.9rem;
}

.refresh-btn:hover {
  background: #3a8eef;
}

/* 统计卡片 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-card {
  background: #f8fafc;
  border-radius: 8px;
  padding: 1rem;
  text-align: center;
  border: 1px solid #e2e8f0;
}

.stat-card.total {
  background: #fef2f2;
  border-color: #fecaca;
}

.stat-card.session {
  background: #fef3c7;
  border-color: #fde68a;
}

.stat-card.model {
  background: #ede9fe;
  border-color: #ddd6fe;
}

.stat-card.healthy {
  background: #d1fae5;
  border-color: #a7f3d0;
}

.stat-card.warning {
  background: #fef3c7;
  border-color: #fde68a;
}

.stat-value {
  font-size: 1.8rem;
  font-weight: 700;
  color: #1e293b;
}

.stat-label {
  font-size: 0.85rem;
  color: #64748b;
  margin-top: 0.25rem;
}

/* 趋势图 */
.trend-section {
  margin-bottom: 1.5rem;
}

.trend-section h3 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: #475569;
}

.trend-chart {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 80px;
  background: #f8fafc;
  border-radius: 6px;
  padding: 0.5rem;
}

.trend-bar {
  flex: 1;
  background: #cbd5e1;
  border-radius: 2px 2px 0 0;
  min-height: 4px;
  position: relative;
  transition: background 0.2s;
}

.trend-bar:hover {
  background: #ef4444;
}

.bar-label {
  position: absolute;
  top: -16px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.7rem;
  color: #64748b;
}

.trend-labels {
  display: flex;
  gap: 2px;
  margin-top: 0.25rem;
}

.trend-time {
  flex: 1;
  text-align: center;
  font-size: 0.7rem;
  color: #94a3b8;
}

/* 错误类型分布 */
.type-distribution {
  margin-bottom: 1.5rem;
}

.type-distribution h3 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: #475569;
}

.type-bars {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.type-bar-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.type-bar-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 100px;
  font-size: 0.85rem;
  color: #475569;
}

.type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.type-bar-track {
  flex: 1;
  height: 8px;
  background: #e2e8f0;
  border-radius: 4px;
  overflow: hidden;
}

.type-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s;
}

.type-count {
  min-width: 40px;
  text-align: right;
  font-size: 0.85rem;
  color: #64748b;
  font-weight: 500;
}

/* API 状态 */
.api-status-section {
  margin-bottom: 1.5rem;
}

.api-status-section h3 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: #475569;
}

.api-status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 0.75rem;
}

.api-status-card {
  padding: 0.75rem;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.api-status-card.status-healthy {
  background: #f0fdf4;
  border-color: #bbf7d0;
}

.api-status-card.status-degraded {
  background: #fffbeb;
  border-color: #fde68a;
}

.api-status-card.status-down {
  background: #fef2f2;
  border-color: #fecaca;
}

.api-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
}

.api-model {
  font-weight: 600;
  font-size: 0.9rem;
  color: #1e293b;
}

.api-provider {
  font-size: 0.8rem;
  color: #94a3b8;
}

.api-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.status-healthy {
  background: #22c55e;
}

.status-dot.status-degraded {
  background: #f59e0b;
}

.status-dot.status-down {
  background: #ef4444;
}

.status-text {
  font-size: 0.85rem;
  color: #64748b;
}

.api-last-error {
  margin-top: 0.5rem;
  font-size: 0.8rem;
  color: #dc2626;
  display: flex;
  justify-content: space-between;
}

.api-error-count {
  margin-top: 0.25rem;
  font-size: 0.8rem;
  color: #ef4444;
}

/* 错误列表 */
.error-lists {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 1.5rem;
}

.error-group h3 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.count-badge {
  background: #e2e8f0;
  color: #64748b;
  font-size: 0.75rem;
  padding: 0.125rem 0.5rem;
  border-radius: 10px;
  font-weight: 500;
}

.empty {
  color: #94a3b8;
  font-size: 0.9rem;
  padding: 1rem;
  text-align: center;
  background: #f8fafc;
  border-radius: 6px;
}

.error-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.error-item {
  background: #fef2f2;
  border-radius: 6px;
  border-left: 4px solid #ef4444;
  cursor: pointer;
  transition: box-shadow 0.2s;
}

.error-item:hover {
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.error-item.severity-warning {
  border-left-color: #f59e0b;
  background: #fffbeb;
}

.error-item.severity-critical {
  border-left-color: #dc2626;
  background: #fef2f2;
}

.error-main {
  display: grid;
  grid-template-columns: 80px 80px 1fr 70px 24px;
  gap: 0.5rem;
  align-items: center;
  padding: 0.75rem;
  font-size: 0.85rem;
}

.error-agent {
  font-weight: 500;
  color: #991b1b;
}

.error-type {
  font-weight: 500;
}

.error-msg {
  color: #7f1d1d;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error-time {
  color: #b91c1c;
  font-size: 0.8rem;
  text-align: right;
}

.expand-icon {
  color: #94a3b8;
  font-size: 0.7rem;
  text-align: center;
}

.error-detail {
  padding: 0.75rem;
  padding-top: 0;
  border-top: 1px solid #fecaca;
  margin: 0 0.75rem 0.75rem 0.75rem;
}

.detail-row {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-size: 0.85rem;
}

.detail-label {
  color: #64748b;
  min-width: 70px;
}

.detail-message {
  color: #1e293b;
  word-break: break-word;
}

/* 响应式 */
@media (max-width: 768px) {
  .header {
    flex-direction: column;
    align-items: flex-start;
  }

  .error-main {
    grid-template-columns: 1fr;
    gap: 0.25rem;
  }

  .error-lists {
    grid-template-columns: 1fr;
  }

  .api-status-grid {
    grid-template-columns: 1fr;
  }
}
</style>
