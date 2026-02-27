<template>
  <div class="performance-section">
    <div class="section-header">
      <h2>性能数据</h2>
      <div class="time-range-selector">
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
            <div class="metric-value">{{ performanceData.current.latency }}</div>
            <div class="metric-unit">毫秒</div>
          </div>
          <div v-if="hasAlert('high_latency')" class="metric-alert">⚠️</div>
        </div>

        <div class="metric-card">
          <div class="metric-icon">📊</div>
          <div class="metric-content">
            <div class="metric-label">错误率</div>
            <div class="metric-value">{{ (performanceData.current.errorRate * 100).toFixed(1) }}%</div>
            <div class="metric-unit">Errors</div>
          </div>
          <div v-if="hasAlert('high_error_rate')" class="metric-alert">⚠️</div>
        </div>
      </div>

      <!-- Trend Charts -->
      <div class="charts-grid">
        <div class="chart-card">
          <h3>TPM 趋势</h3>
          <div class="chart-container">
            <div class="chart-bars">
              <div
                v-for="(point, index) in chartData"
                :key="index"
                class="chart-bar"
                :style="{ height: `${getBarHeight(point.tpm, maxValue('tpm'))}%` }"
                :title="`${formatTime(point.timestamp)}: ${formatNumber(point.tpm)} TPM`"
              >
                <span class="bar-value" v-if="shouldShowLabel(index)">{{ formatNumber(point.tpm) }}</span>
              </div>
            </div>
            <div class="chart-axis">
              <span v-for="(label, index) in timeLabels" :key="index" class="axis-label">
                {{ label }}
              </span>
            </div>
          </div>
        </div>

        <div class="chart-card">
          <h3>RPM 趋势</h3>
          <div class="chart-container">
            <div class="chart-bars rpm">
              <div
                v-for="(point, index) in chartData"
                :key="index"
                class="chart-bar"
                :style="{ height: `${getBarHeight(point.rpm, maxValue('rpm'))}%` }"
                :title="`${formatTime(point.timestamp)}: ${point.rpm} RPM`"
              >
                <span class="bar-value" v-if="shouldShowLabel(index)">{{ point.rpm }}</span>
              </div>
            </div>
            <div class="chart-axis">
              <span v-for="(label, index) in timeLabels" :key="index" class="axis-label">
                {{ label }}
              </span>
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
            <span class="summary-value">{{ performanceData.aggregates.avgLatency }}ms</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">最大 TPM</span>
            <span class="summary-value">{{ formatNumber(performanceData.aggregates.maxTpm) }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">最大延迟</span>
            <span class="summary-value">{{ performanceData.aggregates.maxLatency }}ms</span>
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
import { useRealtime, useThrottle } from '../../composables'
import type { PerformanceData, PerformanceMetric, PerformanceAlert, TimeRange } from '../../types'

const { connectionState, subscribe } = useRealtime()

const loading = ref(true)
const error = ref<string | null>(null)
const selectedRange = ref<TimeRange>('15m')
const alerts = ref<PerformanceAlert[]>([])

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
  { value: '20m' as TimeRange, label: '20分钟' },
  { value: '1h' as TimeRange, label: '1小时' }
]

// 根据时间范围获取数据点数
const dataPoints = computed(() => {
  switch (selectedRange.value) {
    case '20m': return 20
    case '1h': return 60
    default: return 20
  }
})

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

// 时间标签
const timeLabels = computed(() => {
  const data = chartData.value
  const step = Math.ceil(data.length / 6) // 显示 6 个时间标签
  return data
    .filter((_, i) => i % step === 0)
    .map(point => formatTime(point.timestamp))
})

function maxValue(metric: 'tpm' | 'rpm' | 'latency'): number {
  const values = chartData.value.map(p => p[metric])
  const max = Math.max(...values, 1)
  return max * 1.2 // 添加 20% 余量
}

function getBarHeight(value: number, max: number): number {
  return Math.max((value / max) * 100, 5)
}

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

function formatTime(timestamp: number | string | undefined): string {
  // 如果是字符串格式 'HH:MM'，直接返回
  if (typeof timestamp === 'string') {
    return timestamp
  }
  // 如果是无效的数字，返回默认值
  if (!timestamp || isNaN(Number(timestamp))) {
    return '--:--'
  }
  const date = new Date(timestamp)
  if (isNaN(date.getTime())) {
    return '--:--'
  }
  // UTC时间转本地时间
  const hours = date.getUTCHours()
  const minutes = date.getUTCMinutes()
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`
}

// 判断是否显示标签（避免重叠）
// 方案A：根据数据量间隔显示 - 少数据全显示，20个隔1个，60个隔4个
function shouldShowLabel(index: number): boolean {
  const total = chartData.value.length
  if (total <= 10) return true // 少数据：全部显示
  if (index === total - 1) return true // 始终显示最新数据点
  if (total <= 20) return index % 2 === 0 // 20个：隔1个显示（每2个显示1个）
  return index % 5 === 0 // 60个：隔4个显示（每5个显示1个）
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
    performanceData.value = {
      current: data.current || performanceData.value.current,
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
    
    // 检查告警
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

function handlePerformanceUpdate(data: unknown): void {
  const perfData = data as PerformanceData
  if (perfData.current) {
    performanceData.value = perfData
    checkAlerts()
  }
}

// 节流更新
const { throttledFn: throttledFetch } = useThrottle(fetchData, 5000)

let unsubscribe: (() => void) | null = null
let updateInterval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  fetchData()
  unsubscribe = subscribe('performance', handlePerformanceUpdate)
  
  // 定时更新
  updateInterval = setInterval(() => {
    throttledFetch()
  }, 10000)
})

onUnmounted(() => {
  if (unsubscribe) unsubscribe()
  if (updateInterval) clearInterval(updateInterval)
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

.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.chart-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 1.25rem;
}

.chart-card h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: #666;
}

.chart-container {
  height: 150px;
  display: flex;
  flex-direction: column;
}

.chart-bars {
  flex: 1;
  display: flex;
  align-items: flex-end;
  gap: 4px;
  padding-bottom: 1.5rem;
}

.chart-bar {
  flex: 1;
  background: linear-gradient(to top, #4a9eff, #6bb9ff);
  border-radius: 3px 3px 0 0;
  min-height: 8px;
  position: relative;
  transition: height 0.3s ease;
  cursor: pointer;
}

.chart-bars.delay .chart-bar {
  background: linear-gradient(to top, #22c55e, #4ade80);
}

.bar-value {
  position: absolute;
  top: -20px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.65rem;
  color: #6b7280;
  white-space: nowrap;
}

.chart-axis {
  display: flex;
  justify-content: space-between;
  padding-top: 0.5rem;
  border-top: 1px solid #e5e7eb;
}

.axis-label {
  font-size: 0.7rem;
  color: #94a3b8;
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
  
  .charts-grid {
    grid-template-columns: 1fr;
  }
}
</style>
