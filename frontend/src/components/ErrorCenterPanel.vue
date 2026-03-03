<template>
  <section class="error-center">
    <h2>错误中心</h2>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else class="error-content">
      <div class="error-group">
        <h3>Session 错误</h3>
        <div v-if="!data.sessionErrors?.length" class="empty">暂无</div>
        <div v-else class="error-list">
          <div
            v-for="(e, i) in data.sessionErrors"
            :key="`s-${i}`"
            class="error-item"
          >
            <span class="error-agent">{{ getAgentName(e.agentId) }}</span>
            <span class="error-type">{{ e.type }}</span>
            <span class="error-msg">{{ e.message }}</span>
            <span class="error-time">{{ formatTime(e.timestamp) }}</span>
          </div>
        </div>
      </div>
      <div class="error-group">
        <h3>Model Failures</h3>
        <div v-if="!data.modelFailures?.length" class="empty">暂无</div>
        <div v-else class="error-list">
          <div
            v-for="(f, i) in data.modelFailures"
            :key="`f-${i}`"
            class="error-item"
          >
            <span class="error-agent">{{ f.model }}</span>
            <span class="error-type">{{ f.errorType }}</span>
            <span class="error-msg">{{ f.message }}</span>
            <span class="error-time">{{ formatTime(f.timestamp) }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const data = ref<{
  sessionErrors: Array<{ agentId: string; type: string; message: string; timestamp: number }>
  modelFailures: Array<{ model: string; errorType: string; message: string; timestamp: number }>
}>({ sessionErrors: [], modelFailures: [] })
const loading = ref(false)
const error = ref('')

function formatTime(ts: number) {
  if (!ts) return '-'
  const d = new Date(ts)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
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
    const res = await fetch('/api/errors?limit=20')
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
.error-center {
  margin-bottom: 2rem;
}

.error-center h2 {
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

.error-group {
  margin-bottom: 1.5rem;
}

.error-group h3 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: #475569;
}

.empty {
  color: #94a3b8;
  font-size: 0.9rem;
}

.error-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.error-item {
  display: grid;
  grid-template-columns: 90px 90px 1fr 80px;
  gap: 0.75rem;
  align-items: start;
  padding: 0.75rem;
  background: #fef2f2;
  border-radius: 6px;
  border-left: 4px solid #dc2626;
  font-size: 0.9rem;
}

.error-agent, .error-type {
  font-weight: 500;
  color: #991b1b;
}

.error-msg {
  color: #7f1d1d;
  word-break: break-word;
}

.error-time {
  color: #b91c1c;
  font-size: 0.85rem;
}
</style>
