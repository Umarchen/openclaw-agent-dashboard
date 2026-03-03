<template>
  <div class="agent-config-panel">
    <div class="header">
      <h3>⚙️ Agent 配置</h3>
      <button class="refresh-btn" @click="loadConfig" :disabled="loading">
        {{ loading ? '加载中...' : '刷新' }}
      </button>
    </div>

    <div v-if="loading && !config" class="loading-state">
      加载配置...
    </div>

    <div v-else-if="error" class="error-state">
      {{ error }}
    </div>

    <div v-else-if="config" class="config-content">
      <!-- 基本信息 -->
      <div class="config-section">
        <h4>基本信息</h4>
        <div class="info-grid">
          <div class="info-item">
            <span class="label">ID</span>
            <span class="value monospace">{{ config.id }}</span>
          </div>
          <div class="info-item">
            <span class="label">名称</span>
            <span class="value">{{ config.name }}</span>
          </div>
          <div class="info-item full-width">
            <span class="label">工作区</span>
            <span class="value monospace">{{ config.workspace || '未设置' }}</span>
          </div>
          <div class="info-item">
            <span class="label">状态</span>
            <span class="value" :class="`status-${config.status}`">
              {{ statusLabel(config.status) }}
            </span>
          </div>
        </div>
      </div>

      <!-- 模型配置 -->
      <div class="config-section">
        <h4>模型配置</h4>

        <div class="model-config">
          <div class="model-field">
            <label>主模型 (Primary)</label>
            <div class="model-select-wrapper">
              <select v-model="selectedPrimary" :disabled="saving" class="model-select">
                <option value="">-- 选择模型 --</option>
                <optgroup v-for="group in modelGroups" :key="group.provider" :label="group.provider">
                  <option v-for="model in group.models" :key="model.id" :value="model.id">
                    {{ model.name }}
                  </option>
                </optgroup>
              </select>
              <span v-if="config.model?.primary" class="current-model">
                当前: {{ formatModelId(config.model.primary) }}
              </span>
            </div>
          </div>

          <div class="model-field">
            <label>备选模型 (Fallbacks)</label>
            <div class="fallbacks-list">
              <div v-for="(fb, idx) in selectedFallbacks" :key="idx" class="fallback-item">
                <select v-model="selectedFallbacks[idx]" :disabled="saving" class="model-select small">
                  <option value="">-- 选择 --</option>
                  <optgroup v-for="group in modelGroups" :key="group.provider" :label="group.provider">
                    <option v-for="model in group.models" :key="model.id" :value="model.id">
                      {{ model.name }}
                    </option>
                  </optgroup>
                </select>
                <button class="remove-btn" @click="removeFallback(idx)" :disabled="saving">×</button>
              </div>
              <button class="add-fallback-btn" @click="addFallback" :disabled="saving || selectedFallbacks.length >= 3">
                + 添加备选模型
              </button>
            </div>
          </div>

          <div class="model-actions">
            <button
              class="save-btn"
              @click="saveModelConfig"
              :disabled="saving || !hasModelChanges"
            >
              {{ saving ? '保存中...' : '保存修改' }}
            </button>
            <button class="reset-btn" @click="resetModelSelection" :disabled="saving">
              重置
            </button>
          </div>
        </div>
      </div>

      <!-- 描述 -->
      <div v-if="config.description" class="config-section">
        <h4>描述</h4>
        <p class="description-text">{{ config.description }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'

interface Model {
  id: string
  name: string
  provider: string
  contextWindow?: number
  maxTokens?: number
  reasoning?: boolean
}

interface ModelGroup {
  provider: string
  models: Model[]
}

interface AgentConfig {
  id: string
  name: string
  workspace?: string
  status: string
  model?: {
    primary: string
    fallbacks: string[]
  }
  description?: string
  systemPrompt?: string
  lastActiveAt?: number
}

const props = defineProps<{
  agentId: string
}>()

const config = ref<AgentConfig | null>(null)
const availableModels = ref<Model[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')

const selectedPrimary = ref('')
const selectedFallbacks = ref<string[]>([])

const modelGroups = computed<ModelGroup[]>(() => {
  const groups: Record<string, Model[]> = {}
  for (const model of availableModels.value) {
    if (!groups[model.provider]) {
      groups[model.provider] = []
    }
    groups[model.provider].push(model)
  }
  return Object.entries(groups).map(([provider, models]) => ({ provider, models }))
})

const hasModelChanges = computed(() => {
  if (!config.value?.model) return false
  const original = config.value.model
  return selectedPrimary.value !== original.primary ||
    JSON.stringify(selectedFallbacks.value.filter(f => f)) !== JSON.stringify(original.fallbacks || [])
})

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    idle: '空闲',
    working: '工作中',
    down: '异常',
  }
  return map[status] || status
}

function formatModelId(modelId: string): string {
  if (!modelId) return ''
  const parts = modelId.split('/')
  return parts.length > 1 ? parts[parts.length - 1] : modelId
}

async function loadConfig() {
  loading.value = true
  error.value = ''
  try {
    const [configRes, modelsRes] = await Promise.all([
      fetch(`/api/agent-config/${props.agentId}`),
      fetch('/api/available-models'),
    ])

    if (configRes.ok) {
      config.value = await configRes.json()
      // 初始化选择
      if (config.value?.model) {
        selectedPrimary.value = config.value.model.primary || ''
        selectedFallbacks.value = [...(config.value.model.fallbacks || [])]
      }
    } else {
      error.value = '加载配置失败'
    }

    if (modelsRes.ok) {
      const data = await modelsRes.json()
      availableModels.value = data.models || []
    }
  } catch (e) {
    error.value = '加载失败: ' + (e as Error).message
  } finally {
    loading.value = false
  }
}

function addFallback() {
  if (selectedFallbacks.value.length < 3) {
    selectedFallbacks.value.push('')
  }
}

function removeFallback(idx: number) {
  selectedFallbacks.value.splice(idx, 1)
}

function resetModelSelection() {
  if (config.value?.model) {
    selectedPrimary.value = config.value.model.primary || ''
    selectedFallbacks.value = [...(config.value.model.fallbacks || [])]
  }
}

async function saveModelConfig() {
  if (!hasModelChanges.value) return

  saving.value = true
  try {
    const res = await fetch(`/api/agent-config/${props.agentId}/model`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        primary: selectedPrimary.value || null,
        fallbacks: selectedFallbacks.value.filter(f => f) || null,
      }),
    })

    if (res.ok) {
      const data = await res.json()
      if (config.value && data.model) {
        config.value.model = data.model
      }
      alert('模型配置已保存！重启 Agent 后生效。')
    } else {
      const errData = await res.json()
      alert('保存失败: ' + (errData.detail || '未知错误'))
    }
  } catch (e) {
    alert('保存失败: ' + (e as Error).message)
  } finally {
    saving.value = false
  }
}

watch(() => props.agentId, () => {
  loadConfig()
}, { immediate: true })

onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.agent-config-panel {
  padding: 12px;
  max-height: 500px;
  overflow-y: auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.header h3 {
  margin: 0;
  font-size: 14px;
  color: #374151;
}

.refresh-btn {
  padding: 4px 12px;
  font-size: 12px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}

.refresh-btn:hover:not(:disabled) {
  background: #f3f4f6;
}

.refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-state,
.error-state {
  text-align: center;
  padding: 40px 20px;
  color: #6b7280;
}

.error-state {
  color: #dc2626;
}

.config-section {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e5e7eb;
}

.config-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.config-section h4 {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: #374151;
  font-weight: 600;
}

.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.info-item.full-width {
  grid-column: 1 / -1;
}

.info-item .label {
  font-size: 11px;
  color: #6b7280;
}

.info-item .value {
  font-size: 13px;
  color: #1f2937;
}

.info-item .value.monospace {
  font-family: monospace;
  font-size: 12px;
  word-break: break-all;
}

.info-item .value.status-idle {
  color: #22c55e;
}

.info-item .value.status-working {
  color: #f59e0b;
}

.info-item .value.status-down {
  color: #ef4444;
}

.model-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.model-field label {
  display: block;
  font-size: 12px;
  color: #374151;
  margin-bottom: 6px;
  font-weight: 500;
}

.model-select-wrapper {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.model-select {
  width: 100%;
  padding: 8px 10px;
  font-size: 13px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}

.model-select:focus {
  outline: none;
  border-color: #3b82f6;
}

.model-select:disabled {
  background: #f3f4f6;
  cursor: not-allowed;
}

.model-select.small {
  padding: 6px 8px;
  font-size: 12px;
}

.current-model {
  font-size: 11px;
  color: #6b7280;
}

.fallbacks-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fallback-item {
  display: flex;
  gap: 8px;
  align-items: center;
}

.fallback-item .model-select {
  flex: 1;
}

.remove-btn {
  width: 28px;
  height: 28px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 16px;
  color: #6b7280;
  display: flex;
  align-items: center;
  justify-content: center;
}

.remove-btn:hover:not(:disabled) {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #dc2626;
}

.add-fallback-btn {
  padding: 6px 12px;
  font-size: 12px;
  border: 1px dashed #d1d5db;
  border-radius: 4px;
  background: #f9fafb;
  cursor: pointer;
  color: #6b7280;
}

.add-fallback-btn:hover:not(:disabled) {
  border-color: #3b82f6;
  color: #3b82f6;
}

.add-fallback-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.model-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.save-btn {
  padding: 8px 16px;
  font-size: 13px;
  border: none;
  border-radius: 6px;
  background: #3b82f6;
  color: #fff;
  cursor: pointer;
  font-weight: 500;
}

.save-btn:hover:not(:disabled) {
  background: #2563eb;
}

.save-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.reset-btn {
  padding: 8px 16px;
  font-size: 13px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  color: #6b7280;
}

.reset-btn:hover:not(:disabled) {
  background: #f3f4f6;
}

.description-text {
  margin: 0;
  font-size: 13px;
  color: #4b5563;
  line-height: 1.5;
  white-space: pre-wrap;
}
</style>
