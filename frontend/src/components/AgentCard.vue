<template>
  <div class="agent-card" :class="`status-${agent.status}`" @click="$emit('click')">
    <div class="avatar">
      <span>{{ emoji }}</span>
    </div>
    <div class="info">
      <div class="name">{{ agent.name }}</div>
      <div class="status-pill" :class="`status-${agent.status}`">
        <span class="status-dot" :class="`status-${agent.status}`"></span>
        <span class="status-text">{{ statusText }}</span>
      </div>
      <div v-if="agent.currentTask" class="task">
        任务: {{ agent.currentTask }}
      </div>
      <div v-if="agent.lastActiveFormatted" class="last-active">
        活跃: {{ agent.lastActiveFormatted }}
      </div>
      <div v-if="modelInfo && (modelInfo.primary || modelInfo.fallbacks?.length)" class="model-info">
        <span class="model-primary">{{ shortModelId(modelInfo.primary || '') || '—' }}</span>
        <span v-if="modelInfo.fallbacks?.length" class="model-fallbacks">
          → {{ modelInfo.fallbacks.map(shortModelId).join(', ') }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Agent {
  name: string
  status: 'idle' | 'working' | 'down'
  currentTask?: string
  lastActiveFormatted?: string
}

const props = defineProps<{
  agent: Agent
  modelInfo?: { primary?: string; fallbacks?: string[] }
}>()

defineEmits<{
  click: []
}>()

const emoji = computed(() => {
  const name = props.agent.name.toLowerCase()
  if (name.includes('pm') || name.includes('project')) return '👨‍💼'
  if (name.includes('analyst')) return '📊'
  if (name.includes('architect')) return '🏗️'
  if (name.includes('dev')) return '💻'
  if (name.includes('qa') || name.includes('test')) return '🧪'
  return '🤖'
})

const statusText = computed(() => {
  const statusMap = {
    'idle': '空闲',
    'working': '工作中',
    'down': '异常'
  }
  return statusMap[props.agent.status] || '未知'
})

function shortModelId(id: string): string {
  const parts = id.split('/')
  return parts[parts.length - 1] || id
}
</script>

<style scoped>
.agent-card {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}

.agent-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.avatar {
  font-size: 3rem;
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.info {
  flex: 1;
}

.name {
  font-size: 1.125rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  margin-bottom: 0.5rem;
  color: #333;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 500;
  margin-bottom: 0.5rem;
}

.status-pill.status-idle {
  background: #dcfce7;
  color: #166534;
}

.status-pill.status-working {
  background: #dbeafe;
  color: #1d4ed8;
}

.status-pill.status-down {
  background: #fee2e2;
  color: #991b1b;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot.status-idle {
  background: #22c55e;
}

.status-dot.status-working {
  background: #3b82f6;
}

.status-dot.status-down {
  background: #ef4444;
}

.status-text {
  font-size: inherit;
  color: inherit;
}

.task {
  font-size: 0.85rem;
  color: #888;
  margin-bottom: 0.25rem;
}

.last-active {
  font-size: 0.85rem;
  color: #999;
}

.model-info {
  font-size: 0.8rem;
  color: #64748b;
  margin-top: 0.35rem;
  font-family: ui-monospace, 'Cascadia Code', 'SF Mono', monospace;
}

.model-primary {
  font-weight: 500;
  color: #475569;
}

.model-fallbacks {
  margin-left: 0.25rem;
  color: #94a3b8;
}
</style>
