<template>
  <div class="chain-edge" :class="edgeClass">
    <svg width="60" height="20" viewBox="0 0 60 20">
      <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" :fill="arrowColor" />
        </marker>
      </defs>
      <line
        x1="0"
        y1="10"
        x2="50"
        y2="10"
        :stroke="lineColor"
        stroke-width="2"
        :stroke-dasharray="dashArray"
        marker-end="url(#arrowhead)"
      />
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ChainNodeStatus } from './types'

const props = defineProps<{
  fromStatus?: ChainNodeStatus
  toStatus?: ChainNodeStatus
}>()

const lineColor = computed(() => {
  if (props.toStatus === 'running') return '#3b82f6'
  if (props.toStatus === 'completed') return '#22c55e'
  if (props.toStatus === 'error') return '#ef4444'
  return '#9ca3af'
})

const arrowColor = computed(() => {
  return lineColor.value
})

const dashArray = computed(() => {
  if (props.toStatus === 'pending') return '4 4'
  return 'none'
})

const edgeClass = computed(() => {
  return {
    'edge-running': props.toStatus === 'running',
    'edge-completed': props.toStatus === 'completed',
    'edge-error': props.toStatus === 'error',
    'edge-pending': props.toStatus === 'pending'
  }
})
</script>

<style scoped>
.chain-edge {
  display: flex;
  align-items: center;
  margin: 0 4px;
}

.edge-running svg line {
  animation: pulse 1.5s infinite;
}

.edge-completed {
  opacity: 1;
}

.edge-pending {
  opacity: 0.5;
}

.edge-error {
  opacity: 0.8;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
