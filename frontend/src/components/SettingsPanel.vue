<template>
  <div class="settings-panel">
    <div class="header">
      <h2>设置</h2>
      <button class="close-btn" @click="$emit('close')">×</button>
    </div>

    <div class="content">
      <section>
        <h3>自动刷新</h3>
        <div class="setting-item">
          <label>刷新间隔（秒）</label>
          <input 
            type="number" 
            v-model.number="refreshInterval" 
            min="1" 
            max="300"
            @change="saveSettings"
          />
        </div>
        <div class="setting-item">
          <label>
            <input type="checkbox" v-model="autoRefreshEnabled" @change="saveSettings" />
            启用自动刷新
          </label>
        </div>
      </section>

      <section>
        <h3>显示选项</h3>
        <div class="setting-item">
          <label>
            <input type="checkbox" v-model="showTimestamps" @change="saveSettings" />
            显示时间戳
          </label>
        </div>
        <div class="setting-item">
          <label>
            <input type="checkbox" v-model="showTokens" @change="saveSettings" />
            显示 Token 消耗
          </label>
        </div>
      </section>

      <section>
        <h3>通知</h3>
        <div class="setting-item">
          <label>
            <input type="checkbox" v-model="notifyOnError" @change="saveSettings" />
            Agent 异常时通知
          </label>
        </div>
        <div class="setting-item">
          <label>
            <input type="checkbox" v-model="notifyOnComplete" @change="saveSettings" />
            任务完成时通知
          </label>
        </div>
      </section>

      <section>
        <h3>日志查看</h3>
        <div class="setting-item">
          <label>日志行数</label>
          <select v-model="logLines" @change="saveSettings">
            <option :value="50">50 行</option>
            <option :value="100">100 行</option>
            <option :value="200">200 行</option>
            <option :value="500">500 行</option>
          </select>
        </div>
        <div class="setting-item">
          <label>
            <input type="checkbox" v-model="autoScrollLog" @change="saveSettings" />
            自动滚动日志
          </label>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const emit = defineEmits<{
  close: []
}>()

const refreshInterval = ref(10)
const autoRefreshEnabled = ref(true)
const showTimestamps = ref(true)
const showTokens = ref(true)
const notifyOnError = ref(true)
const notifyOnComplete = ref(false)
const logLines = ref(100)
const autoScrollLog = ref(true)

function loadSettings() {
  const saved = localStorage.getItem('dashboard-settings')
  if (saved) {
    try {
      const settings = JSON.parse(saved)
      refreshInterval.value = settings.refreshInterval || 10
      autoRefreshEnabled.value = settings.autoRefreshEnabled !== false
      showTimestamps.value = settings.showTimestamps !== false
      showTokens.value = settings.showTokens !== false
      notifyOnError.value = settings.notifyOnError !== false
      notifyOnComplete.value = settings.notifyOnComplete || false
      logLines.value = settings.logLines || 100
      autoScrollLog.value = settings.autoScrollLog !== false
    } catch (e) {
      console.error('加载设置失败:', e)
    }
  }
}

function saveSettings() {
  const settings = {
    refreshInterval: refreshInterval.value,
    autoRefreshEnabled: autoRefreshEnabled.value,
    showTimestamps: showTimestamps.value,
    showTokens: showTokens.value,
    notifyOnError: notifyOnError.value,
    notifyOnComplete: notifyOnComplete.value,
    logLines: logLines.value,
    autoScrollLog: autoScrollLog.value
  }
  
  localStorage.setItem('dashboard-settings', JSON.stringify(settings))
  
  // 通知父组件
  emit('settings-changed', settings)
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.settings-panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 400px;
  background: white;
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  z-index: 1000;
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
  flex: 1;
  padding: 1.5rem;
  overflow-y: auto;
}

section {
  margin-bottom: 2rem;
}

section:last-child {
  margin-bottom: 0;
}

section h3 {
  margin: 0 0 1rem 0;
  font-size: 1.1rem;
  color: #333;
}

.setting-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 0;
  border-bottom: 1px solid #f3f4f6;
}

.setting-item:last-child {
  border-bottom: none;
}

.setting-item label {
  color: #666;
  font-size: 0.95rem;
}

.setting-item input[type="number"],
.setting-item select {
  padding: 0.5rem;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  width: 100px;
}

.setting-item input[type="checkbox"] {
  margin-right: 0.5rem;
}
</style>
