<template>
  <div class="api-status-card" :class="`status-${status.status}`">
    <div class="header">
      <div class="model">{{ status.model }}</div>
      <div class="provider">{{ status.provider }}</div>
    </div>
    <div class="status">
      <span class="status-dot" :class="`status-${status.status}`"></span>
      <span class="status-text">{{ statusText }}</span>
    </div>
    <div v-if="status.lastError" class="error">
      <div class="error-type">{{ status.lastError.type }}</div>
      <div class="error-time">{{ formatTime(status.lastError.timestamp) }}</div>
    </div>
    <div v-if="status.errorCount > 0" class="error-count">
      错误: {{ status.errorCount }} 次
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface ApiStatus {
  provider: string
  model: string
  status: 'healthy' | 'degraded' | 'down'
  lastError?: {
    type: string
    message: string
    timestamp: number
  }
  errorCount: number
}

const props = defineProps<{
  status: ApiStatus
}>()

const statusText = computed(() => {
  const statusMap = {
    'healthy': '正常',
    'degraded': '降级',
    'down': '异常'
  }
  return statusMap[props.status.status] || '未知'
})

function formatTime(timestamp: number): string {
  const now = Date.now()
  const diff = now - timestamp
  const minutes = Math.floor(diff / 60000)
  
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  return `${Math.floor(hours / 24)}天前`
}
</script>

<style scoped>
.api-status-card {
  padding: 1rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header {
  margin-bottom: 0.75rem;
}

.model {
  font-size: 1.1rem;
  font-weight: 600;
  color: #333;
}

.provider {
  font-size: 0.85rem;
  color: #888;
  margin-top: 0.25rem;
}

.status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-dot.status-healthy {
  background: #4ade80;
}

.status-dot.status-degraded {
  background: #fbbf24;
}

.status-dot.status-down {
  background: #ef4444;
}

.status-text {
  font-size: 0.9rem;
  color: #666;
}

.error {
  padding: 0.75rem;
  background: #fef2f2;
  border-radius: 4px;
  margin-bottom: 0.5rem;
}

.error-type {
  font-size: 0.85rem;
  color: #dc2626;
  font-weight: 500;
}

.error-time {
  font-size: 0.75rem;
  color: #999;
  margin-top: 0.25rem;
}

.error-count {
  font-size: 0.8rem;
  color: #dc2626;
}
</style>
