<template>
  <div
    class="chain-node"
    :class="[`status-${node.status}`, { selected: isSelected }]"
    @click="$emit('click')"
  >
    <!-- 状态图标 -->
    <div class="node-icon">{{ statusIcon }}</div>

    <!-- Agent 信息 -->
    <div class="node-info">
      <div class="node-name">{{ node.agentName }}</div>
      <div class="node-role">{{ node.role }}</div>
    </div>

    <!-- 状态标签 -->
    <div class="node-status">{{ statusLabel }}</div>

    <!-- 时间信息 -->
    <div class="node-time" v-if="node.startedAt">
      {{ formatDuration(node.duration) }}
    </div>

    <!-- 进度指示器 -->
    <div class="node-progress" v-if="node.status === 'running'">
      <div class="progress-spinner"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChainNode } from './types'
import { nodeStatusConfig } from './types'

const props = defineProps<{
  node: ChainNode
  isSelected?: boolean
}>()

defineEmits<{
  click: []
}>()

const statusIcon = computed(() => {
  return nodeStatusConfig[props.node.status]?.icon || '📄'
})

const statusLabel = computed(() => {
  return nodeStatusConfig[props.node.status]?.label || props.node.status
})

function formatDuration(ms: number | undefined): string {
  if (!ms) return ''
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}
</script>

<style scoped>
.chain-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 16px;
  min-width: 120px;
  background: #fff;
  border-radius: 8px;
  border: 2px solid #e5e7eb;
  cursor: pointer;
  transition: all 0.2s;
}

.chain-node:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.chain-node.selected {
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.3);
}

.chain-node.status-pending {
  border-color: #9ca3af;
  background: #f9fafb;
}

.chain-node.status-running {
  border-color: #3b82f6;
  background: #eff6ff;
  animation: pulse 2s infinite;
}

.chain-node.status-completed {
  border-color: #22c55e;
  background: #f0fdf4;
}

.chain-node.status-error {
  border-color: #ef4444;
  background: #fef2f2;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.node-icon {
  font-size: 24px;
  margin-bottom: 8px;
}

.node-info {
  text-align: center;
}

.node-name {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
  margin-bottom: 4px;
}

.node-role {
  font-size: 11px;
  color: #6b7280;
}

.node-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  margin-top: 8px;
}

.status-pending .node-status { background: #f3f4f6; color: #6b7280; }
.status-running .node-status { background: #dbeafe; color: #1e40af; }
.status-completed .node-status { background: #d1fae5; color: #065f46; }
.status-error .node-status { background: #fee2e2; color: #991b1b; }

.node-time {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 8px;
}

.node-progress {
  margin-top: 8px;
}

.progress-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #e5e7eb;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
