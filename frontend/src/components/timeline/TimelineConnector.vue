<template>
  <div class="timeline-connector">
    <div class="connector-line"></div>
    <div class="connector-arrow">▼</div>
  </div>
</template>

<script setup lang="ts">
// 简单的连接线组件，无需逻辑
</script>

<style scoped>
.timeline-connector {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 0;
}

.connector-line {
  width: 2px;
  height: 8px;
  background: #d1d5db;
}

.connector-arrow {
  font-size: 8px;
  color: #9ca3af;
  line-height: 1;
}
</style>
