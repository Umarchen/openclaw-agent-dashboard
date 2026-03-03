<template>
  <section class="mechanism-tracking">
    <h2>机制追踪</h2>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else class="mechanism-grid">
      <div
        v-for="m in mechanisms"
        :key="m.agentId"
        class="mechanism-card"
      >
        <div class="card-header">{{ getAgentName(m.agentId) }}</div>
        <div class="card-body">
          <div class="mechanism-row">
            <span class="label">Memory:</span>
            <span class="value">
              <template v-for="(mem, i) in (m.memory || [])" :key="i">
                {{ mem.name }}<span v-if="!mem.missing" class="ok">✓</span>
                <span v-else class="missing">✗</span>
                <span v-if="i < (m.memory?.length || 0) - 1">, </span>
              </template>
              <span v-if="!m.memory?.length">-</span>
            </span>
          </div>
          <div class="mechanism-row">
            <span class="label">Skills:</span>
            <span class="value">
              {{ (m.skills || []).map((s: { name: string }) => s.name).join(', ') || '-' }}
            </span>
          </div>
          <div class="mechanism-row">
            <span class="label">Channel:</span>
            <span class="value">{{ m.channel || '-' }}</span>
          </div>
          <div class="mechanism-row">
            <span class="label">Heartbeat:</span>
            <span class="value">
              {{ m.heartbeat?.enabled ? `每 ${m.heartbeat.every || '?'} min` : '-' }}
            </span>
          </div>
          <div class="mechanism-row">
            <span class="label">Cron:</span>
            <span class="value">{{ m.cron?.count ?? 0 }} jobs</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const mechanisms = ref<Array<{
  agentId: string
  memory?: Array<{ name: string; path: string; missing: boolean }>
  skills?: Array<{ name: string }>
  channel?: string
  heartbeat?: { every?: number; enabled: boolean }
  cron?: { count: number }
}>>([])
const loading = ref(false)
const error = ref('')

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
    const res = await fetch('/api/mechanisms')
    if (res.ok) {
      mechanisms.value = await res.json()
    } else {
      mechanisms.value = []
      error.value = '加载失败'
    }
  } catch (e) {
    mechanisms.value = []
    error.value = String(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.mechanism-tracking {
  margin-bottom: 2rem;
}

.mechanism-tracking h2 {
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

.mechanism-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 1rem;
}

.mechanism-card {
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  overflow: hidden;
}

.card-header {
  padding: 0.75rem 1rem;
  background: #e2e8f0;
  font-weight: 600;
  color: #334155;
}

.card-body {
  padding: 1rem;
}

.mechanism-row {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
}

.mechanism-row:last-child {
  margin-bottom: 0;
}

.mechanism-row .label {
  min-width: 80px;
  color: #64748b;
}

.mechanism-row .value {
  flex: 1;
  word-break: break-word;
}

.mechanism-row .ok {
  color: #22c55e;
}

.mechanism-row .missing {
  color: #ef4444;
}
</style>
