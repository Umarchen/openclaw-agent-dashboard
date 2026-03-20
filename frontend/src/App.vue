<template>
  <div id="app">
    <header>
      <h1>OpenClaw Agent Dashboard</h1>
      <div class="controls">
        <VersionDisplay />
        <button @click="refreshData">刷新</button>
        <button @click="showSettings = true">⚙️ 设置</button>
        <span class="connection-status" :class="connectionState.status">
          {{ connectionLabel }}
        </span>
      </div>
    </header>

    <main>
      <!-- 协作流程（主 Agent + 子 Agents 合并展示，含连线）-->
      <section class="collaboration-section">
        <CollaborationFlowWrapper
          :main-agent="mainAgent"
          :sub-agents="subAgents"
          :main-agent-id="mainAgentId"
          @agent-click="onAgentNodeClick"
        />
      </section>

      <!-- 任务状态展示区域 -->
      <section class="task-status-section">
        <TaskStatusSection />
      </section>

      <!-- 性能数据展示区域 (整合 TPM/Token) -->
      <section class="performance-section">
        <PerformancePanel />
      </section>

      <!-- 错误中心（含 API 状态） -->
      <section class="error-center-section">
        <ErrorCenterPanel />
      </section>
    </main>

    <!-- 设置面板 -->
    <SettingsPanel
      v-if="showSettings"
      @close="showSettings = false"
      @settings-changed="onSettingsChanged"
    />

    <!-- 详情面板 -->
    <AgentDetailPanel
      v-if="selectedAgent"
      :agent="selectedAgent"
      @close="selectedAgent = null"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, provide } from 'vue'
import AgentDetailPanel from './components/AgentDetailPanel.vue'
import SettingsPanel from './components/SettingsPanel.vue'

// 核心组件
import CollaborationFlowWrapper from './components/collaboration/CollaborationFlowWrapper.vue'
import TaskStatusSection from './components/tasks/TaskStatusSection.vue'
import PerformancePanel from './components/performance/PerformancePanel.vue'
import ErrorCenterPanel from './components/ErrorCenterPanel.vue'

// 版本显示组件
import VersionDisplay from './components/common/VersionDisplay.vue'

// 数据管理
import { getRealtimeManager, getStateManager, getEventDispatcher } from './managers'
import type { ConnectionState } from './types'

interface Agent {
  id: string
  name: string
  role: string
  status: 'idle' | 'working' | 'down'
  currentTask?: string
  lastActiveFormatted?: string
  error?: any
}

// 初始化管理器
const realtimeManager = getRealtimeManager()
const stateManager = getStateManager()
const eventDispatcher = getEventDispatcher()

// 提供给子组件使用
provide('realtimeManager', realtimeManager)
provide('stateManager', stateManager)
provide('eventDispatcher', eventDispatcher)

const agents = ref<Agent[]>([])
const selectedAgent = ref<Agent | null>(null)
const showSettings = ref(false)

// 连接状态
const connectionState = ref<ConnectionState>({
  status: 'disconnected',
  reconnectAttempts: 0
})

const connectionLabel = computed(() => {
  switch (connectionState.value.status) {
    case 'connected': return '已连接'
    case 'connecting': return '连接中...'
    case 'disconnected': return '未连接'
    case 'error': return '连接错误'
    default: return '未知'
  }
})

// 主 Agent
const mainAgent = ref<Agent | null>(null)
const mainAgentId = ref<string>('main')

// 子 Agents
const subAgents = ref<Agent[]>([])

async function refreshData() {
  try {
    const [agentsRes, configRes] = await Promise.all([
      fetch('/api/agents'),
      fetch('/api/config').catch(() => null)
    ])
    const agentsData = await agentsRes.json()
    agents.value = Array.isArray(agentsData) ? agentsData : []
    if (configRes?.ok) {
      const cfg = await configRes.json()
      mainAgentId.value = (cfg && cfg.mainAgentId) || 'main'
    }
    const agentsList = Array.isArray(agents.value) ? agents.value : []
    const main = agentsList.find((a: { id?: string }) => a.id === mainAgentId.value)
    if (main) mainAgent.value = main
    subAgents.value = agentsList.filter((a: { id?: string }) => a.id !== mainAgentId.value)
  } catch (error) {
    console.error('刷新数据失败:', error)
  }
}

function showAgentDetail(agent: Agent) {
  selectedAgent.value = agent
}

function onAgentNodeClick(node: { id: string; name: string; status: string }) {
  const agent = node.id === mainAgentId.value ? mainAgent.value : subAgents.value.find(a => a.id === node.id)
  if (agent) {
    showAgentDetail(agent)
  } else {
    // 协作流程中的 Agent 可能尚未在 /api/agents 中，用节点信息构造
    showAgentDetail({
      id: node.id,
      name: node.name,
      role: node.id === mainAgentId.value ? '主 Agent' : '子 Agent',
      status: (node.status === 'error' ? 'down' : node.status) as 'idle' | 'working' | 'down'
    })
  }
}

function onSettingsChanged(_settings: any) {
  refreshData()
}

// 监听连接状态变化
function handleConnectionStateChange(state: ConnectionState) {
  connectionState.value = state
}

let unsubState: (() => void) | null = null
let unsubAgents: (() => void) | null = null

onMounted(() => {
  refreshData()
  realtimeManager.connect()
  unsubState = realtimeManager.onStateChange(handleConnectionStateChange)
  unsubAgents = realtimeManager.subscribe('agents', (data: unknown) => {
    if (Array.isArray(data)) {
      agents.value = data as Agent[]
      const main = (data as Agent[]).find(a => a.id === mainAgentId.value)
      mainAgent.value = main || null
      subAgents.value = (data as Agent[]).filter(a => a.id !== mainAgentId.value)
    }
  })
})

onUnmounted(() => {
  unsubState?.()
  unsubAgents?.()
  realtimeManager.disconnect()
})
</script>

<style>
/* 全局样式变量 */
:root {
  --color-primary: #4a9eff;
  --color-success: #22c55e;
  --color-warning: #f59e0b;
  --color-error: #ef4444;
  
  --status-idle: #94a3b8;
  --status-active: #4a9eff;
  --status-completed: #22c55e;
  --status-error: #ef4444;
  
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --spacing-xl: 2rem;
  
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 2px 8px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 4px 16px rgba(0, 0, 0, 0.15);
}
</style>

<style scoped>
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: #1a1a2e;
  color: white;
  flex-wrap: wrap;
  gap: 1rem;
}

header h1 {
  margin: 0;
  font-size: 1.5rem;
}

.controls {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

button {
  padding: 0.5rem 1rem;
  background: #4a9eff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

button:hover {
  background: #3a8eef;
}

.connection-status {
  font-size: 0.85rem;
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  background: #2d3748;
}

.connection-status.connected {
  background: #22c55e;
}

.connection-status.connecting {
  background: #f59e0b;
}

.connection-status.disconnected,
.connection-status.error {
  background: #ef4444;
}

main {
  padding: 2rem;
  max-width: 1600px;
  margin: 0 auto;
}

.collaboration-section {
  margin-bottom: 2rem;
  min-height: 400px;
  /* 确保协作流程方框始终可见 */
}

.task-status-section {
  margin-bottom: 2rem;
}




.performance-section {
  margin-bottom: 2rem;
}

.error-center-section {
  margin-bottom: 2rem;
}

h2 {
  margin-bottom: 1rem;
  color: #333;
}

/* 响应式布局 */
@media (max-width: 1024px) {
  main {
    padding: 1rem;
  }

  header {
    padding: 1rem;
  }
}

@media (max-width: 640px) {
  header h1 {
    font-size: 1.2rem;
  }
  
  .controls {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
