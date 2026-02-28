<template>
  <div class="collaboration-box">
    <div class="collaboration-box-header">
      <h2>协作流程</h2>
      <span class="collaboration-hint">展示主 Agent 与子 Agents 的协作关系</span>
    </div>
    <div class="collaboration-box-body">
      <CollaborationFlowSection
        v-show="!capturedError"
        :main-agent="mainAgent"
        :sub-agents="subAgents"
        @agent-click="$emit('agent-click', $event)"
      />
      <div v-show="capturedError" class="collaboration-error-fallback">
        <p class="fallback-title">协作流程加载失败</p>
        <p class="fallback-reason">{{ capturedError }}</p>
        <button @click="capturedError = null">重试</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import CollaborationFlowSection from './CollaborationFlowSection.vue'

defineProps<{
  mainAgent?: unknown
  subAgents?: unknown[]
}>()

defineEmits<{
  'agent-click': [node: unknown]
}>()

const capturedError = ref<string | null>(null)

onErrorCaptured((err) => {
  capturedError.value = err instanceof Error ? err.message : String(err)
  return false
})
</script>

<style scoped>
.collaboration-box {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.collaboration-box-header {
  padding: 1rem 1.5rem;
  border-bottom: 2px solid #e2e8f0;
  background: #f8fafc;
}

.collaboration-box-header h2 {
  margin: 0 0 0.25rem 0;
  font-size: 1.3rem;
  color: #1e293b;
}

.collaboration-hint {
  font-size: 0.85rem;
  color: #64748b;
}

.collaboration-box-body {
  padding: 1rem 1.5rem;
  min-height: 600px;
}

.collaboration-error-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 500px;
  gap: 1rem;
  color: #64748b;
}

.fallback-title {
  margin: 0;
  font-size: 1.1rem;
  color: #334155;
}

.fallback-reason {
  margin: 0;
  font-size: 0.9rem;
  color: #ef4444;
  max-width: 400px;
  text-align: center;
}

.collaboration-error-fallback button {
  padding: 0.5rem 1rem;
  background: #4a9eff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.collaboration-error-fallback button:hover {
  background: #3a8eef;
}
</style>
