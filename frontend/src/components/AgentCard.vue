<template>
  <div class="agent-card" :class="`status-${agent.status}`" @click="$emit('click')">
    <div class="avatar">
      <span>{{ emoji }}</span>
    </div>
    <div class="info">
      <div class="name">{{ agent.name }}</div>
      <div class="status">
        <span class="status-dot" :class="`status-${agent.status}`"></span>
        <span class="status-text">{{ statusText }}</span>
      </div>
      <div v-if="agent.currentTask" class="task">
        任务: {{ agent.currentTask }}
      </div>
      <div v-if="agent.lastActiveFormatted" class="last-active">
        活跃: {{ agent.lastActiveFormatted }}
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
  font-size: 1.2rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
  color: #333;
}

.status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-dot.status-idle {
  background: #4ade80;
}

.status-dot.status-working {
  background: #fbbf24;
}

.status-dot.status-down {
  background: #ef4444;
}

.status-text {
  font-size: 0.9rem;
  color: #666;
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
</style>
