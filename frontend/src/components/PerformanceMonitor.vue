<template>
  <div class="performance-monitor">
    <div class="header-row">
      <h2>性能监控</h2>
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

    <div class="charts-container">
      <!-- TPM 图表 - 上方 -->
      <div class="chart-card" data-type="tpm">
        <h3>TPM 趋势 (最近20分钟)</h3>
        <div class="chart-wrapper">
          <div class="chart-bars">
            <div 
              v-for="(value, index) in tpmHistory" 
              :key="`tpm-${index}`"
              class="chart-bar"
              :data-value="value"
            >
              <!-- 数字标签 - 始终显示在柱子上方 -->
              <span class="bar-value">{{ formatNumber(value) }}</span>

              <!-- 柱子本体 -->
              <div 
                class="bar-visual"
                :style="{ height: `${getBarHeight(value, maxTpm)}%` }"
              ></div>

              <!-- 时间标签 - 每个都显示 -->
              <span class="bar-time-label">
                {{ formatTimestamp(timestamps[index]) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- RPM 图表 - 下方 -->
      <div class="chart-card" data-type="rpm">
        <h3>RPM 趋势 (最近20分钟)</h3>
        <div class="chart-wrapper">
          <div class="chart-bars">
            <div 
              v-for="(value, index) in rpmHistory" 
              :key="`rpm-${index}`"
              class="chart-bar"
              :data-value="value"
            >
              <!-- 数字标签 - 始终显示在柱子上方 -->
              <span class="bar-value">{{ formatNumber(value) }}</span>

              <!-- 柱子本体 -->
              <div 
                class="bar-visual"
                :style="{ height: `${getBarHeight(value, maxRpm)}%` }"
              ></div>

              <!-- 时间标签 - 每个都显示 -->
              <span class="bar-time-label">
                {{ formatTimestamp(timestamps[index]) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="stats-summary">
      <h3>总计 (最近20分钟)</h3>
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

let monitorInterval: any = null

// 格式化数字（带单位）
function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  } else if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

// 格式化时间戳
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

// 计算柱子高度百分比
function getBarHeight(value: number, max: number): number {
  if (max === 0) return 0
  return Math.max((value / max) * 100, 5) // 最小高度 5%
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
  
  // 获取真实性能数据（固定为 20 分钟）
  try {
    const res = await fetch('/api/performance?range=20m')
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
  padding: 24px;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06);
  max-width: 1600px;
  margin: 0 auto;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

h2 {
  margin: 0;
  font-size: 1.3rem;
  font-weight: 600;
  color: #111827;
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
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  text-align: center;
}

.metric-label {
  font-size: 0.85rem;
  color: #6b7280;
  margin-bottom: 0.5rem;
}

.metric-value {
  font-size: 2rem;
  font-weight: 600;
  color: #111827;
  margin-bottom: 0.25rem;
}

.metric-unit {
  font-size: 0.75rem;
  color: #9ca3af;
  margin-bottom: 0.25rem;
}

.metric-desc {
  font-size: 0.7rem;
  color: #9ca3af;
  margin-top: 0.5rem;
}

/* 图表容器 - 上下排列 */
.charts-container {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  margin-bottom: 2rem;
}

.chart-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  padding: 20px;
  width: 100%;
}

.chart-card h3 {
  margin: 0 0 16px 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 8px;
}

.chart-wrapper {
  background: #f9fafb;
  border-radius: 8px;
  padding: 24px 20px;
  position: relative;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;  /* 柱子间距 */
  height: 280px;  /* 图表高度 - 增加，给数字标签更多空间 */
  padding-bottom: 40px;  /* 为时间标签预留空间 */
  position: relative;
  padding-top: 30px;  /* 为数字标签预留顶部空间 */
}

.chart-bar {
  flex: 1;
  min-width: 35px;  /* 最小宽度，确保数字可读 */
  max-width: 60px;  /* 最大宽度，避免过宽 */
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
}

/* 数字标签 - 始终显示在柱子上方 */
.bar-value {
  position: absolute;
  bottom: calc(100% + 8px);  /* 柱子顶部上方 8px */
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.85rem;  /* 13.6px */
  font-weight: 600;
  color: #374151;
  line-height: 1.2;
  white-space: nowrap;
  z-index: 10;
}

/* 柱子本体 */
.bar-visual {
  width: 100%;
  min-height: 4px;  /* 最小高度，确保零值也可见 */
  border-radius: 6px 6px 0 0;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.bar-visual:hover {
  filter: brightness(1.1);
  transform: scaleY(1.02);
  transform-origin: bottom;
}

/* TPM 图表柱子颜色 */
.chart-card[data-type="tpm"] .bar-visual {
  background: linear-gradient(to top, #3b82f6, #60a5fa);
}

/* RPM 图表柱子颜色 */
.chart-card[data-type="rpm"] .bar-visual {
  background: linear-gradient(to top, #10b981, #34d399);
}

/* 零值柱子 */
.chart-bar[data-value="0"] .bar-visual {
  background: #e5e7eb !important;
}

/* 时间标签 */
.bar-time-label {
  position: absolute;
  bottom: -30px;  /* 距离柱子底部 30px */
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.75rem;  /* 12px */
  color: #6b7280;  /* 稍微深一点，更清晰 */
  font-weight: 500;
  white-space: nowrap;
}

.stats-summary {
  padding-top: 1.5rem;
  border-top: 1px solid #e5e7eb;
}

.stats-summary h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  font-weight: 600;
  color: #111827;
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
  color: #6b7280;
}

.summary-value {
  font-size: 1.5rem;
  font-weight: 600;
  color: #111827;
}

.summary-unit {
  font-size: 0.75rem;
  color: #9ca3af;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .chart-bars {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .chart-bar {
    min-width: 40px;
    flex: 0 0 40px;
  }
}
</style>
