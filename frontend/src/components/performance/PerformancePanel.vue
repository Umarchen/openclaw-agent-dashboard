<template>
  <div class="performance-panel">
    <div class="panel-header">
      <h2>性能监控</h2>
      <div class="tab-switcher">
        <button
          :class="['tab-btn', { active: activeTab === 'tpm' }]"
          @click="activeTab = 'tpm'"
        >
          📊 TPM/RPM
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'token' }]"
          @click="activeTab = 'token'"
        >
          💰 Token 分析
        </button>
      </div>
    </div>

    <div class="panel-content">
      <PerformanceSection v-show="activeTab === 'tpm'" />
      <TokenAnalysisPanel v-show="activeTab === 'token'" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import PerformanceSection from './PerformanceSection.vue'
import TokenAnalysisPanel from '../TokenAnalysisPanel.vue'

const activeTab = ref<'tpm' | 'token'>('tpm')
</script>

<style scoped>
.performance-panel {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  flex-wrap: wrap;
  gap: 1rem;
}

.panel-header h2 {
  margin: 0;
  font-size: 1.3rem;
  color: #333;
}

.tab-switcher {
  display: flex;
  gap: 0.5rem;
}

.tab-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: white;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.tab-btn:hover {
  border-color: #4a9eff;
}

.tab-btn.active {
  background: #4a9eff;
  color: white;
  border-color: #4a9eff;
}

.panel-content {
  padding: 0;
}

/* 确保子组件没有额外的背景和圆角 */
.panel-content :deep(.performance-section),
.panel-content :deep(.token-analysis) {
  background: transparent;
  box-shadow: none;
  border-radius: 0;
  padding: 1.5rem;
  margin-bottom: 0;
}

/* 响应式 */
@media (max-width: 640px) {
  .panel-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .tab-switcher {
    width: 100%;
  }

  .tab-btn {
    flex: 1;
    justify-content: center;
  }
}
</style>
