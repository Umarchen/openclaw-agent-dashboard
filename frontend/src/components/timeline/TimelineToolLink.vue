<template>
  <div class="tool-link" :class="{ 'link-error': isError, 'link-active': isActive }">
    <div class="link-line">
      <span class="link-dot top"></span>
      <span class="link-connector"></span>
      <span class="link-dot bottom"></span>
    </div>
    <span class="link-time" v-if="executionTime">{{ formatDuration(executionTime) }}</span>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  isError?: boolean
  isActive?: boolean
  executionTime?: number
}>()

function formatDuration(ms: number): string {
  if (!ms) return ''
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}
</script>

<style scoped>
.tool-link {
  display: flex;
  align-items: center;
  padding: 4px 0 4px 28px;
  position: relative;
}

.link-line {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: absolute;
  left: 12px;
  top: 0;
  bottom: 0;
}

.link-connector {
  width: 2px;
  flex: 1;
  background: linear-gradient(to bottom, #94a3b8 0%, #94a3b8 50%, transparent 50%);
  background-size: 2px 8px;
  min-height: 20px;
}

.link-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
  border: 2px solid #fff;
  box-shadow: 0 0 0 1px #e5e7eb;
}

.link-dot.bottom {
  position: absolute;
  bottom: 0;
}

.link-time {
  font-size: 10px;
  color: #64748b;
  background: #f8fafc;
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: 8px;
  border: 1px solid #e5e7eb;
}

/* 错误状态 */
.link-error .link-connector {
  background: linear-gradient(to bottom, #ef4444 0%, #ef4444 50%, transparent 50%);
  background-size: 2px 8px;
}

.link-error .link-dot {
  background: #ef4444;
}

.link-error .link-time {
  color: #dc2626;
  background: #fef2f2;
  border-color: #fecaca;
}

/* 高亮状态 */
.link-active .link-connector {
  background: linear-gradient(to bottom, #3b82f6 0%, #3b82f6 50%, transparent 50%);
  background-size: 2px 8px;
}

.link-active .link-dot {
  background: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
}

.link-active .link-time {
  color: #2563eb;
  background: #eff6ff;
  border-color: #bfdbfe;
}
</style>
