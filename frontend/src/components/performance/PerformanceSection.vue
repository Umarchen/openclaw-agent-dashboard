<template>
  <div class="performance-section">
    <div class="section-header">
      <h2>性能数据</h2>
      <div v-if="timeRanges.length > 1" class="time-range-selector">
        <button
          v-for="range in timeRanges"
          :key="range.value"
          :class="['range-btn', { active: selectedRange === range.value }]"
          @click="selectedRange = range.value"
        >
          {{ range.label }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>加载性能数据...</span>
    </div>

    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span>{{ error }}</span>
      <button @click="refreshData" class="retry-btn">重试</button>
    </div>

    <template v-else>
      <!-- Metric Cards -->
      <div class="metrics-grid">
        <div class="metric-card">
          <div class="metric-icon">⚡</div>
          <div class="metric-content">
            <div class="metric-label">TPM</div>
            <div class="metric-value">{{ formatNumber(performanceData.current.tpm) }}</div>
            <div class="metric-unit">Tokens/分钟</div>
          </div>
          <div v-if="hasAlert('high_tpm')" class="metric-alert">⚠️</div>
        </div>

        <div class="metric-card">
          <div class="metric-icon">🔄</div>
          <div class="metric-content">
            <div class="metric-label">RPM</div>
            <div class="metric-value">{{ formatNumber(performanceData.current.rpm) }}</div>
            <div class="metric-unit">Requests/分钟</div>
          </div>
        </div>

        <div class="metric-card">
          <div class="metric-icon">⏱️</div>
          <div class="metric-content">
            <div class="metric-label">延迟</div>
            <div class="metric-value">{{ formatLatency(performanceData.current.latency) }}</div>
            <div class="metric-unit">毫秒</div>
          </div>
          <div v-if="hasAlert('high_latency')" class="metric-alert">⚠️</div>
        </div>

        <div class="metric-card">
          <div class="metric-icon">📊</div>
          <div class="metric-content">
            <div class="metric-label">错误率</div>
            <div class="metric-value">{{ formatErrorRate(performanceData.current.errorRate) }}</div>
            <div class="metric-unit">Errors</div>
          </div>
          <div v-if="hasAlert('high_error_rate')" class="metric-alert">⚠️</div>
        </div>
      </div>

      <!-- Trend Charts - 上下排列 -->
      <div class="charts-stack">
        <div class="chart-card">
          <div class="chart-header">
            <h3>TPM 趋势</h3>
            <span class="chart-datetime">{{ formatDateTime(chartDisplayTime) }}</span>
          </div>
          <div class="chart-container">
            <div class="chart-bars">
              <div
                v-for="(point, index) in chartData"
                :key="index"
                class="chart-bar clickable"
                :style="{ height: `${getBarHeight(point.tpm, maxValue('tpm'))}%` }"
                :title="`${formatTime(point.timestamp)}: ${formatNumber(point.tpm)} TPM - 点击查看详情`"
                @click="showBarDetail(point, 'tpm')"
              >
                <span class="bar-value">{{ formatNumber(point.tpm) }}</span>
                <span class="bar-time-label">{{ formatTime(point.timestamp) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="chart-card">
          <div class="chart-header">
            <h3>RPM 趋势</h3>
            <span class="chart-datetime">{{ formatDateTime(chartDisplayTime) }}</span>
          </div>
          <div class="chart-container">
            <div class="chart-bars rpm">
              <div
                v-for="(point, index) in chartData"
                :key="index"
                class="chart-bar clickable"
                :style="{ height: `${getBarHeight(point.rpm, maxValue('rpm'))}%` }"
                :title="`${formatTime(point.timestamp)}: ${point.rpm} RPM - 点击查看调用详情`"
                @click="showBarDetail(point, 'rpm')"
              >
                <span class="bar-value">{{ point.rpm }}</span>
                <span class="bar-time-label">{{ formatTime(point.timestamp) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Summary -->
      <div class="summary-section">
        <h3>统计摘要</h3>
        <div class="summary-grid">
          <div class="summary-item">
            <span class="summary-label">平均 TPM</span>
            <span class="summary-value">{{ formatNumber(performanceData.aggregates.avgTpm) }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">平均延迟</span>
            <span class="summary-value">{{ formatLatency(performanceData.aggregates.avgLatency) }}ms</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">最大 TPM</span>
            <span class="summary-value">{{ formatNumber(performanceData.aggregates.maxTpm) }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">最大延迟</span>
            <span class="summary-value">{{ formatLatency(performanceData.aggregates.maxLatency) }}ms</span>
          </div>
          <div class="summary-item highlight">
            <span class="summary-label">总 Token</span>
            <span class="summary-value">{{ formatNumber(performanceData.aggregates.totalTokens) }}</span>
          </div>
          <div class="summary-item highlight">
            <span class="summary-label">总请求</span>
            <span class="summary-value">{{ formatNumber(performanceData.aggregates.totalRequests) }}</span>
          </div>
        </div>
      </div>

      <!-- 柱体详情弹窗 -->
      <div v-if="detailModalVisible" class="detail-modal-overlay" @click.self="detailModalVisible = false">
        <div class="detail-modal">
          <div class="detail-modal-header">
            <h3>{{ detailModalTitle }}</h3>
            <button class="close-btn" @click="detailModalVisible = false">×</button>
          </div>
          <div class="detail-modal-body">
            <div v-if="detailLoading" class="detail-loading">加载详情...</div>
            <div v-else-if="detailData?.calls?.length" class="detail-calls">
              <div class="detail-summary">
                {{ detailData.totalCalls }} 次调用 · {{ formatNumber(detailData.totalTokens) }} Tokens
              </div>
              <div v-if="detailData.calls.some((c: { trigger?: string }) => c.trigger?.startsWith('【完成回传】'))" class="detail-call-hint">
                <span class="hint-badge">完成回传</span>
                <span class="hint-text">此时间戳为子任务完成后的回传时间，不是派发时间</span>
              </div>
              <div v-for="(call, i) in detailData.calls" :key="i" class="detail-call-item">
                <div class="call-header">
                  <span class="call-agent">{{ call.agentId }}</span>
                  <span class="call-time">{{ call.time }}</span>
                  <span class="call-tokens">{{ formatNumber(call.tokens) }} tokens</span>
                </div>
                <div class="call-trigger" :title="call.trigger">
                  <span v-if="call.trigger?.startsWith('【完成回传】')" class="call-trigger-badge">完成回传</span>
                  {{ call.trigger?.replace(/^【完成回传】/, '') }}
                </div>
                <div v-if="call.model" class="call-meta">模型: {{ call.model }}</div>
              </div>
            </div>
            <div v-else class="detail-empty">该时段无调用记录</div>
          </div>
        </div>
      </div>

      <!-- Alerts Panel -->
      <div v-if="alerts.length > 0" class="alerts-panel">
        <h3>⚠️ 性能告警</h3>
        <div class="alerts-list">
          <div
            v-for="alert in alerts"
            :key="alert.id"
            class="alert-item"
            :class="alert.type"
          >
            <span class="alert-message">{{ alert.message }}</span>
            <span class="alert-value">{{ alert.value }} (阈值: {{ alert.threshold }})</span>
            <span class="alert-time">{{ formatTime(alert.timestamp) }}</span>
            <button class="ack-btn" @click="acknowledgeAlert(alert.id)">确认</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRealtime } from '../../composables'
import type { PerformanceData, PerformanceMetric, PerformanceAlert, TimeRange } from '../../types'

const { connectionState, subscribe } = useRealtime()

const loading = ref(true)
const error = ref<string | null>(null)
const selectedRange = ref<TimeRange>('20m')
const alerts = ref<PerformanceAlert[]>([])

// 柱体详情弹窗
const detailModalVisible = ref(false)
const detailLoading = ref(false)
const detailData = ref<{ minute: string; calls: Array<{ agentId: string; sessionId: string; model: string; tokens: number; trigger: string; time: string }>; totalCalls: number; totalTokens: number } | null>(null)
const detailModalTitle = ref('')

// 默认性能数据
const performanceData = ref<PerformanceData>({
  current: {
    timestamp: Date.now(),
    tpm: 0,
    rpm: 0,
    latency: 0,
    errorRate: 0
  },
  history: [],
  aggregates: {
    avgTpm: 0,
    avgLatency: 0,
    totalTokens: 0,
    totalRequests: 0,
    maxTpm: 0,
    maxLatency: 0
  }
})

const timeRanges = [
  { value: '20m' as TimeRange, label: '20分钟' }
]

// 根据时间范围获取数据点数（固定20分钟）
const dataPoints = computed(() => 20)

// 图表数据
const chartData = computed(() => {
  const history = performanceData.value.history
  const points = dataPoints.value

  // 如果历史数据不够，用数据填充
  if (history.length === 0) {
    return Array.from({ length: points }, (_, i) => ({
      timestamp: Date.now() - (points - i - 1) * 60000,
      tpm: 0,
      rpm: 0,
      latency: 0,
      errorRate: 0
    }))
  }

  // 如果历史数据不够，填充 0
  const data = [...history]
  while (data.length < points) {
    const lastTimestamp = data[data.length - 1]?.timestamp || Date.now()
    data.unshift({
      timestamp: lastTimestamp - 60000,
      tpm: 0,
      rpm: 0,
      latency: 0,
      errorRate: 0
    })
  }

  return data.slice(-points)
})

function maxValue(metric: 'tpm' | 'rpm' | 'latency'): number {
  const values = chartData.value.map(p => p[metric])
  const max = Math.max(...values, 1)
  return max * 1.2 // 添加 20% 余量
}

function getBarHeight(value: number, max: number): number {
  return Math.max((value / max) * 100, 5)
}

function formatLatency(val: number | undefined): string {
  if (val === undefined || val === null || isNaN(Number(val))) return '--'
  const n = Number(val)
  return n >= 0 ? String(Math.round(n)) : '--'
}

function formatErrorRate(val: number | undefined): string {
  if (val === undefined || val === null || isNaN(Number(val))) return '0.0'
  const n = Number(val)
  return (Math.max(0, Math.min(1, n)) * 100).toFixed(1) + '%'
}

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

// 图表右上角时间：仅在数据更新时刷新，避免每秒重渲染导致页面抖动
const chartDisplayTime = ref(Date.now())

function formatDateTime(timestamp: number | string | undefined): string {
  const ts = timestamp ?? Date.now()
  const num = typeof ts === 'number' ? ts : Number(ts)
  if (isNaN(num)) return new Date().toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
  // 若为秒级时间戳（10位），转为毫秒
  const ms = num < 1e12 ? num * 1000 : num
  const date = new Date(ms)
  if (isNaN(date.getTime())) return new Date().toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  })
}

function formatTime(timestamp: number | string | undefined): string {
  // 无效值
  if (timestamp === undefined || timestamp === null) {
    return '--:--'
  }
  // 字符串格式 'HH:MM'（兼容旧数据）- 按 UTC 解析后转本地
  if (typeof timestamp === 'string') {
    const parts = timestamp.split(':').map(Number)
    if (parts.length >= 2) {
      const now = new Date()
      const utcDate = new Date(Date.UTC(
        now.getUTCFullYear(),
        now.getUTCMonth(),
        now.getUTCDate(),
        parts[0],
        parts[1],
        0,
        0
      ))
      return utcDate.toLocaleString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      })
    }
    return timestamp
  }
  // 数字时间戳 - 使用本地时区
  const ts = Number(timestamp)
  if (isNaN(ts)) return '--:--'
  const date = new Date(ts)
  if (isNaN(date.getTime())) return '--:--'
  return date.toLocaleString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

function hasAlert(type: string): boolean {
  return alerts.value.some(a => a.type === type && !a.acknowledged)
}

function acknowledgeAlert(id: string): void {
  const alert = alerts.value.find(a => a.id === id)
  if (alert) {
    alert.acknowledged = true
  }
}

async function fetchData(): Promise<void> {
  loading.value = true
  error.value = null
  
  try {
    const response = await fetch(`/api/performance?range=${selectedRange.value}`)
    if (!response.ok) throw new Error('Failed to fetch performance data')
    
    const data = await response.json()
    const prev = performanceData.value.current
    const curr = data.current || {}
    performanceData.value = {
      current: {
        timestamp: curr.timestamp ?? prev.timestamp,
        tpm: curr.tpm ?? 0,
        rpm: curr.rpm ?? 0,
        latency: curr.latency ?? prev.latency ?? 0,
        errorRate: typeof curr.errorRate === 'number' ? curr.errorRate : (prev.errorRate ?? 0)
      },
      history: data.history?.tpm?.map((tpm: number, i: number) => ({
        timestamp: data.history.timestamps?.[i] || Date.now() - i * 60000,
        tpm,
        rpm: data.history.rpm?.[i] || 0,
        latency: 0,
        errorRate: 0
      })) || [],
      aggregates: data.total ? {
        avgTpm: data.current?.tpm || 0,
        avgLatency: 0,
        totalTokens: data.total.tokens || 0,
        totalRequests: data.total.requests || 0,
        maxTpm: Math.max(...(data.history?.tpm || [0])),
        maxLatency: 0
      } : performanceData.value.aggregates
    }
    chartDisplayTime.value = Date.now()
    checkAlerts()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function checkAlerts(): void {
  const { current } = performanceData.value
  
  // TPM 告警阈值
  if (current.tpm > 100000) {
    alerts.value.push({
      id: `high_tpm_${Date.now()}`,
      type: 'high_tpm',
      message: 'TPM 过高',
      value: current.tpm,
      threshold: 100000,
      timestamp: Date.now(),
      acknowledged: false
    })
  }
  
  // 延迟告警阈值
  if (current.latency > 5000) {
    alerts.value.push({
      id: `high_latency_${Date.now()}`,
      type: 'high_latency',
      message: 'API 延迟过高',
      value: current.latency,
      threshold: 5000,
      timestamp: Date.now(),
      acknowledged: false
    })
  }
  
  // 保留最近 10 条告警
  alerts.value = alerts.value.slice(-10)
}

function refreshData(): void {
  fetchData()
}

async function showBarDetail(point: { timestamp: number | string; tpm?: number; rpm?: number }, type: 'tpm' | 'rpm'): Promise<void> {
  let tsMs: number
  if (typeof point.timestamp === 'number') {
    tsMs = point.timestamp < 1e12 ? point.timestamp * 1000 : point.timestamp
  } else if (typeof point.timestamp === 'string') {
    // 后端可能返回 "HH:MM" 格式（UTC），需按 UTC 解析
    const parts = point.timestamp.split(':').map(Number)
    if (parts.length >= 2) {
      const now = new Date()
      let utcDate = now.getUTCDate()
      const slotMins = parts[0] * 60 + parts[1]
      const nowMins = now.getUTCHours() * 60 + now.getUTCMinutes()
      // 若 slot 时间大于当前时间（如 23:50 vs 00:10），说明是前一天
      if (slotMins > nowMins + 10) {
        utcDate -= 1
      }
      const d = new Date(Date.UTC(
        now.getUTCFullYear(),
        now.getUTCMonth(),
        utcDate,
        parts[0],
        parts[1],
        0,
        0
      ))
      tsMs = d.getTime()
    } else {
      return
    }
  } else {
    return
  }
  detailModalVisible.value = true
  detailModalTitle.value = `${formatTime(point.timestamp)} 调用详情 (${type.toUpperCase()})`
  detailData.value = null
  detailLoading.value = true
  try {
    const res = await fetch(`/api/performance/details?timestamp=${tsMs}`)
    const data = await res.json()
    if (!res.ok) {
      detailData.value = { minute: formatTime(point.timestamp), calls: [], totalCalls: 0, totalTokens: 0 }
    } else {
      detailData.value = data
      detailModalTitle.value = `${data.minute || formatTime(point.timestamp)} 调用详情`
    }
  } catch (e) {
    detailData.value = { minute: formatTime(point.timestamp), calls: [], totalCalls: 0, totalTokens: 0 }
  } finally {
    detailLoading.value = false
  }
}

function handlePerformanceUpdate(data: unknown): void {
  const raw = data as { current?: object; history?: { tpm?: number[]; rpm?: number[]; timestamps?: number[] }; total?: { tokens?: number; requests?: number } }
  if (!raw?.current) return
  const prev = performanceData.value.current
  const curr = raw.current as Record<string, unknown>
  performanceData.value = {
    current: {
      timestamp: (curr.timestamp as number) ?? prev.timestamp,
      tpm: (curr.tpm as number) ?? 0,
      rpm: (curr.rpm as number) ?? 0,
      latency: (curr.latency as number) ?? prev.latency ?? 0,
      errorRate: typeof curr.errorRate === 'number' ? curr.errorRate : (prev.errorRate ?? 0)
    },
    history: raw.history?.tpm?.map((tpm: number, i: number) => ({
      timestamp: raw.history?.timestamps?.[i] ?? Date.now() - i * 60000,
      tpm,
      rpm: raw.history?.rpm?.[i] ?? 0,
      latency: 0,
      errorRate: 0
    })) ?? [],
    aggregates: raw.total ? {
      avgTpm: (curr.tpm as number) ?? 0,
      avgLatency: 0,
      totalTokens: raw.total.tokens ?? 0,
      totalRequests: raw.total.requests ?? 0,
      maxTpm: Math.max(...(raw.history?.tpm ?? [0])),
      maxLatency: 0
    } : performanceData.value.aggregates
  }
  chartDisplayTime.value = Date.now()
  checkAlerts()
}

// 节流更新
let unsubscribe: (() => void) | null = null

onMounted(() => {
  fetchData()
  unsubscribe = subscribe('performance', handlePerformanceUpdate)
})

onUnmounted(() => {
  if (unsubscribe) unsubscribe()
})

// 时间范围变化时重新获取数据
watch(selectedRange, () => {
  fetchData()
})
</script>

<style scoped>
.performance-section {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 1.5rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.section-header h2 {
  margin: 0;
  font-size: 1.3rem;
  color: #333;
}

.time-range-selector {
  display: flex;
  gap: 0.5rem;
}

.range-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: white;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.range-btn:hover {
  border-color: #4a9eff;
}

.range-btn.active {
  background: #4a9eff;
  color: white;
  border-color: #4a9eff;
}

.loading-state,
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  gap: 1rem;
  color: #6b7280;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e5e7eb;
  border-top-color: #4a9eff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.retry-btn {
  padding: 0.5rem 1rem;
  background: #4a9eff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.metric-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.25rem;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  position: relative;
}

.metric-icon {
  font-size: 2rem;
}

.metric-content {
  flex: 1;
}

.metric-label {
  font-size: 0.8rem;
  color: #6b7280;
  margin-bottom: 0.25rem;
}

.metric-value {
  font-size: 1.75rem;
  font-weight: 600;
  color: #333;
}

.metric-unit {
  font-size: 0.75rem;
  color: #94a3b8;
}

.metric-alert {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  font-size: 1.25rem;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.charts-stack {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.chart-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 1.25rem;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.chart-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #666;
}

.chart-datetime {
  font-size: 0.8rem;
  color: #94a3b8;
}

.chart-container {
  height: 200px;
  display: flex;
  flex-direction: column;
}

.chart-bars {
  flex: 1;
  display: flex;
  align-items: flex-end;
  gap: 6px;
  padding-bottom: 36px;
  padding-top: 28px;
  overflow-x: auto;
  min-width: 0;
}

.chart-bar {
  flex: 1;
  min-width: 28px;
  background: linear-gradient(to top, #4a9eff, #6bb9ff);
  border-radius: 3px 3px 0 0;
  min-height: 8px;
  position: relative;
  transition: height 0.3s ease;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.chart-bars.rpm .chart-bar {
  background: linear-gradient(to top, #10b981, #34d399);
}

.bar-value {
  position: absolute;
  top: -22px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.65rem;
  color: #6b7280;
  white-space: nowrap;
}

.bar-time-label {
  position: absolute;
  bottom: -30px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.7rem;
  color: #6b7280;
  white-space: nowrap;
}

.summary-section {
  padding-top: 1.5rem;
  border-top: 1px solid #e5e7eb;
  margin-bottom: 1.5rem;
}

.summary-section h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: #666;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 1rem;
  background: #f9fafb;
  border-radius: 6px;
}

.summary-item.highlight {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
}

.summary-label {
  font-size: 0.8rem;
  color: #6b7280;
}

.summary-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: #333;
}

.chart-bar.clickable {
  cursor: pointer;
}
.chart-bar.clickable:hover {
  opacity: 0.9;
}

.detail-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.detail-modal {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  max-width: 560px;
  width: 90%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}
.detail-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #e5e7eb;
}
.detail-modal-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #333;
}
.detail-modal-header .close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #6b7280;
  line-height: 1;
  padding: 0 0.25rem;
}
.detail-modal-header .close-btn:hover {
  color: #333;
}
.detail-modal-body {
  padding: 1rem 1.25rem;
  overflow-y: auto;
}
.detail-loading {
  text-align: center;
  padding: 2rem;
  color: #6b7280;
}
.detail-summary {
  font-size: 0.9rem;
  color: #6b7280;
  margin-bottom: 1rem;
}
.detail-calls {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.detail-call-hint {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: #eff6ff;
  border: 1px solid #93c5fd;
  border-radius: 6px;
  margin-bottom: 0.75rem;
}
.detail-call-hint .hint-badge {
  font-size: 0.8rem;
  font-weight: 600;
  color: #1d4ed8;
  padding: 0.15rem 0.5rem;
  background: #dbeafe;
  border-radius: 4px;
}
.detail-call-hint .hint-text {
  font-size: 0.8rem;
  color: #1e40af;
}

.detail-call-item {
  padding: 0.75rem 1rem;
  background: #f9fafb;
  border-radius: 8px;
  border-left: 3px solid #4a9eff;
}
.detail-call-item .call-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.35rem;
}
.detail-call-item .call-agent {
  font-weight: 600;
  color: #333;
}
.detail-call-item .call-time {
  font-size: 0.8rem;
  color: #6b7280;
}
.detail-call-item .call-tokens {
  font-size: 0.8rem;
  color: #10b981;
  margin-left: auto;
}
.detail-call-item .call-trigger {
  font-size: 0.85rem;
  color: #555;
  word-break: break-word;
  margin-top: 0.25rem;
  white-space: pre-wrap;
}
.detail-call-item .call-trigger-badge {
  display: inline-block;
  font-size: 0.75rem;
  font-weight: 600;
  color: #1d4ed8;
  padding: 0.1rem 0.4rem;
  background: #dbeafe;
  border-radius: 4px;
  margin-right: 0.35rem;
}
.detail-call-item .call-meta {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-top: 0.25rem;
}
.detail-empty {
  text-align: center;
  padding: 2rem;
  color: #9ca3af;
}

.alerts-panel {
  background: #fef3c7;
  border: 1px solid #fcd34d;
  border-radius: 8px;
  padding: 1rem;
}

.alerts-panel h3 {
  margin: 0 0 0.75rem 0;
  font-size: 0.95rem;
  color: #92400e;
}

.alerts-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem;
  background: white;
  border-radius: 6px;
  font-size: 0.85rem;
}

.alert-message {
  flex: 1;
  color: #333;
}

.alert-value {
  color: #6b7280;
}

.alert-time {
  font-size: 0.75rem;
  color: #94a3b8;
}

.ack-btn {
  padding: 0.25rem 0.75rem;
  background: #4a9eff;
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 0.75rem;
  cursor: pointer;
}

.ack-btn:hover {
  background: #3a8eef;
}

/* 响应式 */
@media (max-width: 640px) {
  .section-header {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .time-range-selector {
    width: 100%;
    justify-content: space-between;
  }
  
  .range-btn {
    flex: 1;
    text-align: center;
    padding: 0.5rem;
    font-size: 0.75rem;
  }
  
  .metrics-grid {
    grid-template-columns: 1fr 1fr;
  }
  
}
</style>
