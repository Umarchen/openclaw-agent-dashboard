<template>
  <div class="performance-monitor">
    <div class="header-row">
      <h2>性能监控</h2>
      <div class="time-selector">
        <label>时间范围：</label>
        <select v-model="selectedRange" @change="onRangeChange">
          <option value="20m">20分钟</option>
          <option value="1h">1小时</option>
        </select>
      </div>
    </div>
    
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">当前 TPM</div>
        <div class="metric-value">{{ currentTpm }}</div>
        <div class="metric-unit">Tokens/分钟</div>
        <div class="metric-desc">每分钟消耗的 Token 数</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">当前 RPM</div>
        <div class="metric-value">{{ currentRpm }}</div>
        <div class="metric-unit">Requests/分钟</div>
        <div class="metric-desc">每分钟 API 请求数</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">API 响应时间</div>
        <div class="metric-value">{{ apiLatency }}ms</div>
        <div class="metric-unit">毫秒</div>
        <div class="metric-desc">API 平均响应时间</div>
      </div>

      <div class="metric-card">
        <div class="metric-label">WebSocket 连接</div>
        <div class="metric-value">{{ connectionsCount }}</div>
        <div class="metric-unit">个</div>
        <div class="metric-desc">当前活跃连接数</div>
      </div>
    </div>

    <div class="charts-grid">
      <div class="chart-card">
        <h3>TPM 趋势 (最近{{ rangeLabel }})</h3>
        <div class="chart-placeholder">
          <div class="chart-bars">
            <div 
              v-for="(value, index) in tpmHistory" 
              :key="index"
              class="chart-bar"
              :style="{ height: `${getBarHeight(value, maxTpm)}%` }"
            >
              <span class="bar-value">{{ formatNumber(value) }}</span>
              <span class="bar-label">{{ formatTimestamp(timestamps[index]) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="chart-card">
        <h3>RPM 趋势 (最近{{ rangeLabel }})</h3>
        <div class="chart-placeholder">
          <div class="chart-bars">
            <div 
              v-for="(value, index) in rpmHistory" 
              :key="index"
              class="chart-bar"
              :style="{ height: `${getBarHeight(value, maxRpm)}%` }"
            >
              <span class="bar-value">{{ formatNumber(value) }}</span>
              <span class="bar-label">{{ formatTimestamp(timestamps[index]) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="stats-summary">
      <h3>总计 (最近{{ rangeLabel }})</h3>
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">总 Token:</span>
          <span class="summary-value">{{ formatNumber(totalTokens) }}</span>
          <span class="summary-unit">tokens</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">总请求:</span>
          <span class="summary-value">{{ formatNumber(totalRequests) }}</span>
          <span class="summary-unit">次</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

const connectionsCount = ref(0)
const apiLatency = ref(0)
const currentTpm = ref(0)
const currentRpm = ref(0)
const tpmHistory = ref<number[]>([])
const rpmHistory = ref<number[]>([])
const timestamps = ref<string[]>([])
const maxTpm = ref(100)
const maxRpm = ref(10)
const totalTokens = ref(0)
const totalRequests = ref(0)
const selectedRange = ref('20m')

let monitorInterval: any = null

const rangeLabel = computed(() => {
  return selectedRange.value === '1h' ? '1小时' : '20分钟'
})

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

function formatTimestamp(time: string): string {
  // 后端返回的是 HH:MM 格式（UTC时间）
  const [hours, minutes] = time.split(':').map(Number)
  const now = new Date()
  // 构造今天的UTC时间
  const utcDate = new Date(Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
    hours,
    minutes,
    0,
    0
  ))
  
  // 使用 toLocaleString 格式化为 Asia/Shanghai 时区
  return utcDate.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

function getBarHeight(value: number, max: number): number {
  if (max === 0) return 0
  return Math.max((value / max) * 100, 5) // 最小高度 5%
}

function onRangeChange() {
  // 时间范围改变时立即更新数据
  updateMetrics()
}

async function updateMetrics() {
  // 获取连接数
  try {
    const res = await fetch('/api/websocket/connections')
    const data = await res.json()
    connectionsCount.value = data.count || 0
  } catch (e) {
    console.error('获取连接数失败:', e)
  }

  // 测量 API 响应时间
  const startTime = Date.now()
  try {
    await fetch('/api/performance')
    apiLatency.value = Date.now() - startTime
  } catch (e) {
    console.error('测量 API 响应时间失败:', e)
  }
  
  // 获取真实性能数据（带时间范围参数）
  try {
    const res = await fetch(`/api/performance?range=${selectedRange.value}`)
    const data = await res.json()
    
    // 当前值
    currentTpm.value = data.current?.tpm || 0
    currentRpm.value = data.current?.rpm || 0
    
    // 历史数据
    tpmHistory.value = data.history?.tpm || []
    rpmHistory.value = data.history?.rpm || []
    timestamps.value = data.history?.timestamps || []
    
    // 总计
    totalTokens.value = data.total?.tokens || 0
    totalRequests.value = data.total?.requests || 0
    
    // 更新最大值
    if (tpmHistory.value.length > 0) {
      maxTpm.value = Math.max(...tpmHistory.value, 100)
    }
    if (rpmHistory.value.length > 0) {
      maxRpm.value = Math.max(...rpmHistory.value, 10)
    }
  } catch (e) {
    console.error('获取性能数据失败:', e)
  }
}

onMounted(() => {
  // 初始化
  updateMetrics()
  
  // 每 10 秒更新一次指标
  monitorInterval = setInterval(() => {
    updateMetrics()
  }, 10000)
})

onUnmounted(() => {
  if (monitorInterval) {
    clearInterval(monitorInterval)
  }
})
</script>

<style scoped>
.performance-monitor {
  padding: 1.5rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.time-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.time-selector label {
  font-size: 0.85rem;
  color: #666;
}

.time-selector select {
  padding: 0.5rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: white;
  font-size: 0.85rem;
  color: #333;
  cursor: pointer;
}

.time-selector select:focus {
  outline: none;
  border-color: #4a9eff;
}

h2 {
  margin: 0;
  font-size: 1.3rem;
  color: #333;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.metric-card {
  padding: 1.5rem;
  background: #f9fafb;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  text-align: center;
}

.metric-label {
  font-size: 0.85rem;
  color: #666;
  margin-bottom: 0.5rem;
}

.metric-value {
  font-size: 2rem;
  font-weight: 600;
  color: #333;
  margin-bottom: 0.25rem;
}

.metric-unit {
  font-size: 0.75rem;
  color: #999;
  margin-bottom: 0.25rem;
}

.metric-desc {
  font-size: 0.7rem;
  color: #999;
  margin-top: 0.5rem;
}

.charts-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.chart-card {
  background: white;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  padding: 1.5rem;
}

.chart-card h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: #666;
}

.chart-placeholder {
  background: #f9fafb;
  border-radius: 6px;
  padding: 1.5rem;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  height: 150px;
}

.chart-bar {
  flex: 1;
  background: linear-gradient(to top, #4a9eff, #6bb9ff);
  border-radius: 4px 4px 0 0;
  position: relative;
  min-height: 20px;
  transition: height 0.3s ease;
}

.bar-value {
  position: absolute;
  top: -25px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.7rem;
  color: #333;
  white-space: nowrap;
  font-weight: 500;
}

.bar-label {
  position: absolute;
  bottom: -25px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.65rem;
  color: #999;
  white-space: nowrap;
}

.stats-summary {
  padding-top: 1.5rem;
  border-top: 1px solid #e5e7eb;
}

.stats-summary h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: #666;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.summary-item {
  padding: 1rem;
  background: #f9fafb;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.summary-label {
  font-size: 0.85rem;
  color: #666;
}

.summary-value {
  font-size: 1.5rem;
  font-weight: 600;
  color: #333;
}

.summary-unit {
  font-size: 0.75rem;
  color: #999;
}
</style>
