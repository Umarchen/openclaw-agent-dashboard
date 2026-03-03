<template>
  <section class="token-analysis">
    <h2>Token 分析</h2>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else class="token-content">
      <div class="token-summary">
        <div class="summary-row">
          <span class="label">总 Input:</span>
          <span class="value">{{ formatNum(data.total?.input) }}</span>
        </div>
        <div class="summary-row">
          <span class="label">总 Output:</span>
          <span class="value">{{ formatNum(data.total?.output) }}</span>
        </div>
        <div class="summary-row">
          <span class="label">Cache Read:</span>
          <span class="value">{{ formatNum(data.total?.cacheRead) }}</span>
        </div>
        <div class="summary-row">
          <span class="label">Cache Write:</span>
          <span class="value">{{ formatNum(data.total?.cacheWrite) }}</span>
        </div>
      </div>
      <div class="by-agent">
        <h3>按 Agent</h3>
        <div
          v-for="(agentData, agentId) in data.byAgent"
          :key="agentId"
          class="agent-token-row"
        >
          <span class="agent-name">{{ getAgentName(agentId) }}</span>
          <span class="agent-stats">
            in {{ formatNum(agentData.input) }} / out {{ formatNum(agentData.output) }}
            <span v-if="agentData.cacheRead">(cache {{ formatNum(agentData.cacheRead) }})</span>
          </span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const data = ref<{
  byAgent: Record<string, { input: number; output: number; cacheRead: number; cacheWrite: number }>
  total: { input: number; output: number; cacheRead: number; cacheWrite: number }
}>({ byAgent: {}, total: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } })
const loading = ref(false)
const error = ref('')

function formatNum(n: number | undefined) {
  if (n == null) return '0'
  return n.toLocaleString()
}

function getAgentName(agentId: string) {
  const names: Record<string, string> = {
    main: '主 Agent',
    'analyst-agent': '分析师',
    'architect-agent': '架构师',
    'devops-agent': 'DevOps'
  }
  return names[agentId] || agentId
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetch('/api/tokens/analysis')
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
</script>

<style scoped>
.token-analysis {
  margin-bottom: 2rem;
}

.token-analysis h2 {
  margin-bottom: 1rem;
  color: #333;
}

.loading, .error {
  color: #666;
  font-size: 0.9rem;
}

.error {
  color: #dc2626;
}

.token-summary {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 1rem;
  margin-bottom: 1.5rem;
  padding: 1rem;
  background: #f8fafc;
  border-radius: 8px;
}

.summary-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-row .label {
  font-size: 0.85rem;
  color: #64748b;
}

.summary-row .value {
  font-weight: 600;
  color: #334155;
}

.by-agent h3 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: #475569;
}

.agent-token-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid #e2e8f0;
  font-size: 0.9rem;
}

.agent-token-row:last-child {
  border-bottom: none;
}

.agent-name {
  font-weight: 500;
  color: #334155;
}

.agent-stats {
  color: #64748b;
}
</style>
