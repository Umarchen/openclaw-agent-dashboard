<template>
  <div class="panel-overlay" @click="$emit('close')">
    <div class="panel" @click.stop>
      <div class="header">
        <h2>{{ agent.name }}</h2>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>

      <div class="content">
        <div class="section">
          <h3>状态</h3>
          <div class="status-info">
            <span class="status-dot" :class="`status-${agent.status}`"></span>
            <span class="status-text">{{ statusText }}</span>
          </div>
        </div>

        <div v-if="agent.currentTask" class="section">
          <h3>当前任务</h3>
          <p>{{ agent.currentTask }}</p>
        </div>

        <div v-if="agent.lastActiveFormatted" class="section">
          <h3>最后活跃</h3>
          <p>{{ agent.lastActiveFormatted }}</p>
        </div>

        <div v-if="agent.error" class="section">
          <h3 class="error-title">错误信息</h3>
          <div class="error-info">
            <div class="error-type">{{ agent.error.type }}</div>
            <div class="error-message">{{ agent.error.message }}</div>
          </div>
        </div>

        <div class="section">
          <h3>最近活动</h3>
          <div class="activity-list">
            <div v-if="agent.status === 'working'" class="activity-item working">
              💼 正在执行任务...
            </div>
            <div v-else-if="agent.status === 'idle'" class="activity-item idle">
              😴 空闲中
            </div>
            <div v-else-if="agent.status === 'down'" class="activity-item down">
              ⚠️ 检测到错误
            </div>
          </div>
        </div>
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
  error?: {
    type: string
    message: string
    timestamp: number
  }
}

const props = defineProps<{
  agent: Agent
}>()

defineEmits<{
  close: []
}>()

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
.panel-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.panel {
  width: 500px;
  max-width: 90vw;
  max-height: 90vh;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  border-bottom: 1px solid #e5e7eb;
}

.header h2 {
  margin: 0;
  font-size: 1.5rem;
  color: #333;
}

.close-btn {
  font-size: 2rem;
  line-height: 1;
  background: none;
  border: none;
  cursor: pointer;
  color: #999;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  color: #333;
}

.content {
  padding: 1.5rem;
  overflow-y: auto;
}

.section {
  margin-bottom: 1.5rem;
}

.section:last-child {
  margin-bottom: 0;
}

.section h3 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: #666;
}

.status-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-dot {
  width: 12px;
  height: 12px;
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
  font-size: 1.1rem;
  color: #333;
  font-weight: 500;
}

.error-title {
  color: #dc2626;
}

.error-info {
  padding: 1rem;
  background: #fef2f2;
  border-radius: 6px;
  border-left: 4px solid #dc2626;
}

.error-type {
  font-weight: 600;
  color: #dc2626;
  margin-bottom: 0.5rem;
}

.error-message {
  font-size: 0.9rem;
  color: #666;
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.activity-item {
  padding: 0.75rem;
  border-radius: 6px;
  font-size: 0.9rem;
}

.activity-item.working {
  background: #fef3c7;
  color: #92400e;
}

.activity-item.idle {
  background: #d1fae5;
  color: #065f46;
}

.activity-item.down {
  background: #fee2e2;
  color: #991b1b;
}
</style>
