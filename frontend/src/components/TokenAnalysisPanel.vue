<template>
  <section class="token-analysis">
    <div class="section-header">
      <h2>Token 分析</h2>
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
      <span>加载 Token 数据...</span>
    </div>

    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span>{{ error }}</span>
      <button @click="load" class="retry-btn">重试</button>
    </div>

    <template v-else>
      <!-- Summary Cards -->
      <div class="summary-cards">
        <div class="summary-card">
          <div class="card-icon">📥</div>
          <div class="card-content">
            <div class="card-label">Input</div>
            <div class="card-value">{{ formatNum(data.summary?.input) }}</div>
          </div>
        </div>
        <div class="summary-card">
          <div class="card-icon">📤</div>
          <div class="card-content">
            <div class="card-label">Output</div>
            <div class="card-value">{{ formatNum(data.summary?.output) }}</div>
          </div>
        </div>
        <div class="summary-card highlight">
          <div class="card-icon">💾</div>
          <div class="card-content">
            <div class="card-label">Cache Read</div>
            <div class="card-value">{{ formatNum(data.summary?.cacheRead) }}</div>
            <div class="card-sub">命中率 {{ formatPercent(data.summary?.cacheHitRate) }}</div>
          </div>
        </div>
        <div class="summary-card">
          <div class="card-icon">📝</div>
          <div class="card-content">
            <div class="card-label">Cache Write</div>
            <div class="card-value">{{ formatNum(data.summary?.cacheWrite) }}</div>
          </div>
        </div>
        <div class="summary-card cost">
          <div class="card-icon">💰</div>
          <div class="card-content">
            <div class="card-label">估算成本</div>
            <div class="card-value">${{ formatCost(data.cost?.total) }}</div>
            <div v-if="data.cost?.saved > 0" class="card-sub saved">节省 ${{ formatCost(data.cost?.saved) }}</div>
          </div>
        </div>
      </div>

      <!-- Trend Chart (for 20m/1h/24h range) -->
      <div v-if="data.trend && showTrend" class="trend-section">
        <h3>Token 消耗趋势</h3>
        <div class="trend-chart">
          <div class="trend-bars">
            <div
              v-for="(timestamp, i) in data.trend.timestamps"
              :key="i"
              class="trend-bar-group"
            >
              <div class="trend-bar input" :style="{ height: getBarHeight(data.trend.input[i], maxTrendValue) + '%' }">
                <span v-if="data.trend.input[i] > 0" class="bar-tooltip">In: {{ formatNum(data.trend.input[i]) }}</span>
              </div>
              <div class="trend-bar output" :style="{ height: getBarHeight(data.trend.output[i], maxTrendValue) + '%' }">
                <span v-if="data.trend.output[i] > 0" class="bar-tooltip">Out: {{ formatNum(data.trend.output[i]) }}</span>
              </div>
              <span class="trend-time">{{ formatTrendTime(timestamp) }}</span>
            </div>
          </div>
          <div class="trend-legend">
            <span class="legend-item"><span class="legend-color input"></span> Input</span>
            <span class="legend-item"><span class="legend-color output"></span> Output</span>
          </div>
        </div>
      </div>

      <!-- View Toggle -->
      <div class="view-toggle">
        <button :class="{ active: viewMode === 'table' }" @click="viewMode = 'table'">📊 表格</button>
        <button :class="{ active: viewMode === 'chart' }" @click="viewMode = 'chart'">📈 图表</button>
      </div>

      <!-- Table View -->
      <div v-if="viewMode === 'table'" class="by-agent-table">
        <table>
          <thead>
            <tr>
              <th>Agent</th>
              <th>Input</th>
              <th>Output</th>
              <th>Cache</th>
              <th>总计</th>
              <th>占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="agent in sortedAgents" :key="agent.agent">
              <td class="agent-name">{{ agent.agent }}</td>
              <td>{{ formatNum(agent.input) }}</td>
              <td>{{ formatNum(agent.output) }}</td>
              <td>{{ formatNum(agent.cacheRead + agent.cacheWrite) }}</td>
              <td class="total-col">{{ formatNum(agent.total) }}</td>
              <td>
                <div class="percent-bar">
                  <div class="percent-fill" :style="{ width: (agent.percent * 100) + '%' }"></div>
                  <span class="percent-text">{{ formatPercent(agent.percent) }}</span>
                </div>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td><strong>合计</strong></td>
              <td>{{ formatNum(data.summary?.input) }}</td>
              <td>{{ formatNum(data.summary?.output) }}</td>
              <td>{{ formatNum((data.summary?.cacheRead || 0) + (data.summary?.cacheWrite || 0)) }}</td>
              <td class="total-col"><strong>{{ formatNum(data.summary?.total) }}</strong></td>
              <td>100%</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <!-- Chart View -->
      <div v-else class="by-agent-chart">
        <h3>Token 消耗分布</h3>
        <div class="bar-chart">
          <div v-for="agent in sortedAgents" :key="agent.agent" class="bar-row">
            <div class="bar-label">{{ agent.agent }}</div>
            <div class="bar-container">
              <div class="bar" :style="{ width: (agent.percent * 100) + '%' }">
                <span class="bar-value">{{ formatNum(agent.total) }}</span>
              </div>
            </div>
            <div class="bar-percent">{{ formatPercent(agent.percent) }}</div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import type { TokenAnalysisData, AgentTokenData } from '../types/performance'

const data = ref<TokenAnalysisData>({
  summary: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0, cacheHitRate: 0 },
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0, saved: 0, savedPercent: 0 },
  byAgent: [],
  trend: null
})
const loading = ref(false)
const error = ref('')
const viewMode = ref<'table' | 'chart'>('table')
const selectedRange = ref<string>('all')

const timeRanges = [
  { value: 'all', label: '全部' },
  { value: '24h', label: '24小时' },
  { value: '1h', label: '1小时' },
  { value: '20m', label: '20分钟' }
]

const showTrend = computed(() => selectedRange.value !== 'all' && data.value.trend)

const maxTrendValue = computed(() => {
  if (!data.value.trend) return 1
  const allValues = [...data.value.trend.input, ...data.value.trend.output]
  return Math.max(...allValues, 1)
})

const sortedAgents = computed(() => {
  return [...(data.value.byAgent || [])].sort((a, b) => b.total - a.total)
})

function getBarHeight(value: number, max: number): number {
  return Math.max((value / max) * 100, 2)
}

function formatTrendTime(timestamp: number): string {
  const date = new Date(timestamp)
  if (selectedRange.value === '24h') {
    return date.toLocaleString('zh-CN', { hour: '2-digit', hour12: false }) + ':00'
  }
  return date.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function formatNum(n: number | undefined) {
  if (n == null) return '0'
  if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K'
  return n.toLocaleString()
}

function formatPercent(n: number | undefined) {
  if (n == null) return '0%'
  return (n * 100).toFixed(1) + '%'
}

function formatCost(n: number | undefined) {
  if (n == null) return '0.00'
  if (n >= 1) return n.toFixed(2)
  return n.toFixed(4)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch(`/api/tokens/analysis?range=${selectedRange.value}`)
    if (res.ok) {
      data.value = await res.json()
    } else {
      error.value = '加载失败'
    }
  } catch (e) {
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)

watch(selectedRange, load)
</script>

<style scoped>
.token-analysis {
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

.error-icon {
  font-size: 2rem;
}

/* Summary Cards */
.summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.summary-card {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.summary-card.highlight {
  background: #f0fdf4;
  border-color: #86efac;
}

.summary-card.cost {
  background: linear-gradient(135deg, #fefce8 0%, #fef9c3 100%);
  border-color: #fde047;
}

.card-icon {
  font-size: 1.5rem;
}

.card-content {
  flex: 1;
}

.card-label {
  font-size: 0.8rem;
  color: #6b7280;
  margin-bottom: 0.25rem;
}

.card-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: #333;
}

.card-sub {
  font-size: 0.75rem;
  color: #6b7280;
  margin-top: 0.25rem;
}

.card-sub.saved {
  color: #16a34a;
  font-weight: 500;
}

/* Trend Section */
.trend-section {
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.trend-section h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: #666;
}

.trend-chart {
  position: relative;
}

.trend-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 120px;
  padding-bottom: 30px;
}

.trend-bar-group {
  flex: 1;
  display: flex;
  align-items: flex-end;
  gap: 1px;
  min-width: 20px;
  position: relative;
}

.trend-bar {
  flex: 1;
  min-width: 8px;
  border-radius: 2px 2px 0 0;
  min-height: 2px;
  position: relative;
  transition: height 0.3s ease;
}

.trend-bar.input {
  background: linear-gradient(to top, #4a9eff, #6bb9ff);
}

.trend-bar.output {
  background: linear-gradient(to top, #f59e0b, #fbbf24);
}

.bar-tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: #333;
  color: white;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.7rem;
  white-space: nowrap;
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
}

.trend-bar:hover .bar-tooltip {
  opacity: 1;
}

.trend-time {
  position: absolute;
  bottom: -25px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.65rem;
  color: #6b7280;
  white-space: nowrap;
}

.trend-legend {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  margin-top: 0.5rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: #6b7280;
}

.legend-color {
  width: 12px;
  height: 12px;
  border-radius: 2px;
}

.legend-color.input {
  background: #4a9eff;
}

.legend-color.output {
  background: #f59e0b;
}

/* View Toggle */
.view-toggle {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.view-toggle button {
  padding: 0.5rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: white;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.view-toggle button:hover {
  border-color: #4a9eff;
}

.view-toggle button.active {
  background: #4a9eff;
  color: white;
  border-color: #4a9eff;
}

/* Table View */
.by-agent-table {
  overflow-x: auto;
}

.by-agent-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.by-agent-table th,
.by-agent-table td {
  padding: 0.75rem;
  text-align: left;
  border-bottom: 1px solid #e5e7eb;
}

.by-agent-table th {
  background: #f9fafb;
  font-weight: 600;
  color: #6b7280;
  font-size: 0.8rem;
  text-transform: uppercase;
}

.by-agent-table tfoot td {
  background: #f9fafb;
  font-weight: 500;
}

.agent-name {
  font-weight: 500;
  color: #333;
}

.total-col {
  font-weight: 600;
  color: #4a9eff;
}

.percent-bar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.percent-fill {
  height: 8px;
  background: #4a9eff;
  border-radius: 4px;
  min-width: 4px;
}

.percent-text {
  font-size: 0.8rem;
  color: #6b7280;
  white-space: nowrap;
}

/* Chart View */
.by-agent-chart h3 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: #666;
}

.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.bar-label {
  width: 120px;
  font-size: 0.85rem;
  font-weight: 500;
  color: #333;
  flex-shrink: 0;
}

.bar-container {
  flex: 1;
  height: 24px;
  background: #f3f4f6;
  border-radius: 4px;
  overflow: hidden;
}

.bar {
  height: 100%;
  background: linear-gradient(90deg, #4a9eff, #6bb9ff);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding-right: 0.5rem;
  min-width: fit-content;
}

.bar-value {
  font-size: 0.75rem;
  color: white;
  font-weight: 500;
  white-space: nowrap;
}

.bar-percent {
  width: 50px;
  font-size: 0.8rem;
  color: #6b7280;
  text-align: right;
}

/* Responsive */
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

  .summary-cards {
    grid-template-columns: 1fr 1fr;
  }

  .bar-label {
    width: 80px;
    font-size: 0.75rem;
  }

  .bar-percent {
    width: 40px;
  }
}
</style>
