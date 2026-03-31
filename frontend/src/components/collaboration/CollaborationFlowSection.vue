<template>
  <div class="collaboration-flow-section">
    <div class="section-header">
      <h2>协作流程</h2>
      <div class="header-right">
        <div v-if="agentNodes.length > 0" class="flow-legend flow-legend-inline">
          <div v-for="aid in legendAgentIds" :key="aid" class="legend-item">
            <span class="legend-dot" :style="{ background: getAgentColor(aid) }"></span>
            <span class="legend-name">{{ getAgentName(aid) }}</span>
          </div>
        </div>
        <div class="connection-indicator" :class="connectionState.status">
          <span class="indicator-dot"></span>
          <span class="indicator-text">{{ connectionLabel }}</span>
        </div>
      </div>
    </div>

    <div class="flow-container" ref="flowContainerRef">
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <span>加载中...</span>
      </div>

      <div v-else-if="error" class="error-state">
        <span class="error-icon">⚠️</span>
        <span>{{ error }}</span>
        <button @click="refreshData" class="retry-btn">重试</button>
      </div>

      <div v-else-if="nodes.length === 0" class="empty-state">
        <span class="empty-icon">📭</span>
        <span>暂无协作数据</span>
      </div>

      <!-- 主布局：Agent区 + 模型面板 -->
      <div v-else class="flow-layout">
        <!-- Agent 树形布局区 -->
        <div class="agent-area" ref="agentAreaRef">
          <!-- 按层级渲染 -->
          <div v-for="(levelAgents, level) in agentsByLevel" :key="level" class="level-section">
            <!-- 层级标签 -->
            <div class="level-header">
              <span class="level-badge">L{{ level }}</span>
              <span class="level-title">{{ getLevelTitle(Number(level)) }}</span>
            </div>
            <!-- 该层的 Agent 卡片 -->
            <div class="level-cards">
              <div
                v-for="node in levelAgents"
                :key="node.id"
                class="agent-card-wrapper"
                :class="{
                  'main-agent': node.id === computedMainAgentId,
                  'active': isActiveNode(node),
                  [`status-${node.status}`]: true
                }"
                :style="{ '--agent-color': getAgentColor(node.id) }"
                :ref="el => setAgentRef(node.id, el)"
                @click="emit('agent-click', node)"
              >
                <AgentCard
                  :agent="getAgentForNode(node)"
                  :model-info="getModelInfoForNode(node)"
                  :is-main="node.id === computedMainAgentId"
                  :current-task="node.currentTask"
                  :error="node.error"
                  :stuck-warning="node.stuckWarning"
                  :hierarchy-depth="getAgentDepth(node.id)"
                  :agent-color="getAgentColor(node.id)"
                  :sub-status="node.subStatus"
                  :current-action="node.currentAction"
                  :tool-name="node.toolName"
                  :waiting-for="node.waitingFor"
                  :agent-tasks="getAgentActiveTasks(node.id)"
                />
              </div>
            </div>
          </div>

          <!-- 连线 SVG 层 -->
          <svg class="edges-svg" ref="edgesSvgRef">
            <defs>
              <linearGradient id="lightGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" style="stop-color:#4a9eff;stop-opacity:0.2" />
                <stop offset="50%" style="stop-color:#4a9eff;stop-opacity:1" />
                <stop offset="100%" style="stop-color:#4a9eff;stop-opacity:0.2" />
              </linearGradient>
            </defs>
            <g v-for="edge in delegateEdges" :key="edge.id">
              <path
                :d="getEdgePath(edge)"
                class="edge-path"
                :class="{ active: isActiveEdge(edge) }"
                stroke="#4a9eff"
                stroke-width="2"
                fill="none"
              />
              <circle
                v-if="isActiveEdge(edge)"
                r="5"
                fill="url(#lightGradient)"
              >
                <animateMotion :dur="'2s'" repeatCount="1" rotate="0">
                  <mpath :href="`#edge-${edge.id}`" />
                </animateMotion>
              </circle>
            </g>
          </svg>
        </div>

        <!-- 右侧模型面板 -->
        <div class="model-panel" v-if="modelNodes.length > 0">
          <div class="model-panel-header" @click="modelPanelExpanded = !modelPanelExpanded">
            <span class="model-panel-title">🧠 模型</span>
            <span class="model-toggle-icon">{{ modelPanelExpanded ? '▼' : '▶' }}</span>
          </div>
          <div class="model-panel-body" v-show="modelPanelExpanded">
            <div
              v-for="modelNode in modelNodes"
              :key="modelNode.id"
              class="model-card"
              :class="{ active: isModelActive(modelNode) }"
            >
              <div class="model-name">{{ modelNode.name }}</div>
              <div class="model-dots">
                <span
                  v-for="call in getCallsForModelNode(modelNode).slice(0, 8)"
                  :key="call.id"
                  class="model-dot"
                  :style="{ background: getAgentColor(call.agentId) }"
                  :title="`${getAgentName(call.agentId)} @ ${call.model || 'unknown'}`"
                  @click.stop="selectedCall = call"
                />
              </div>
              <div class="model-count">{{ getCallsForModelNode(modelNode).length }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 调用详情弹窗 -->
    <div v-if="selectedCall" class="call-detail-overlay" @click.self="selectedCall = null">
      <div class="call-detail-modal">
        <div class="call-detail-header">
          <h3>调用详情</h3>
          <button class="close-btn" @click="selectedCall = null">×</button>
        </div>
        <div class="call-detail-body">
          <div class="call-detail-row">
            <span class="label">Agent</span>
            <span class="value">{{ selectedCall.agentId }}</span>
          </div>
          <div class="call-detail-row">
            <span class="label">模型</span>
            <span class="value">{{ selectedCall.model }}</span>
          </div>
          <div class="call-detail-row">
            <span class="label">时间</span>
            <span class="value">{{ selectedCall.time }}</span>
          </div>
          <div class="call-detail-row">
            <span class="label">Tokens</span>
            <span class="value">{{ selectedCall.tokens }}</span>
          </div>
          <div class="call-detail-row trigger">
            <span class="label">触发</span>
            <div class="value">{{ selectedCall.trigger?.replace(/^【完成回传】/, '') }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRealtime } from '../../composables'
import AgentCard from '../AgentCard.vue'
import type { CollaborationNode, CollaborationEdge, CollaborationFlow, CollaborationDynamic, ModelCall, AgentDisplayStatus, ActiveTask } from '../../types'

/** 与后端 WS 周期（约 1s）同量级，状态与 activePath 更快对齐 */
const DYNAMIC_POLL_INTERVAL_MS = 1500

interface AgentForCard {
  name: string
  status: 'idle' | 'working' | 'down'
  currentTask?: string
  lastActiveFormatted?: string
}

interface TaskInfo {
  id: string
  name: string
  status: 'working' | 'completed' | 'failed' | 'pending'
  time?: string
}

const props = defineProps<{
  mainAgent?: AgentForCard & { id?: string } | null
  subAgents?: (AgentForCard & { id?: string })[]
  mainAgentId?: string
}>()

const emit = defineEmits<{
  'agent-click': [node: CollaborationNode]
}>()

const { connectionState, subscribe } = useRealtime()

const nodes = ref<CollaborationNode[]>([])
const edges = ref<CollaborationEdge[]>([])
const activePath = ref<string[]>([])
const agentModels = ref<Record<string, { primary?: string; fallbacks?: string[] }>>({})
const recentCalls = ref<ModelCall[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const selectedCall = ref<ModelCall | null>(null)
const hierarchy = ref<Record<string, string[]>>({})
const depths = ref<Record<string, number>>({})
const backendMainAgentId = ref<string>('')
const modelPanelExpanded = ref(true)
const agentActiveTasks = ref<Record<string, ActiveTask[]>>({})

// DOM refs
const agentAreaRef = ref<HTMLElement | null>(null)
const edgesSvgRef = ref<SVGSVGElement | null>(null)
const agentRefs = ref<Record<string, HTMLElement | null>>({})

function setAgentRef(id: string, el: unknown) {
  if (el) agentRefs.value[id] = el as HTMLElement
}

// 计算主 Agent ID
const computedMainAgentId = computed(() => {
  if (props.mainAgentId) return props.mainAgentId
  if (backendMainAgentId.value) return backendMainAgentId.value
  return 'main'
})

// Agent / Model 节点
const agentNodes = computed(() => nodes.value.filter(n => n.type === 'agent'))
const modelNodes = computed(() => nodes.value.filter(n => n.type === 'model'))
const delegateEdges = computed(() => edges.value.filter(e => e.type === 'delegates'))

// 按层级分组（注意：v-for 中 (value, key) 顺序）
const agentsByLevel = computed(() => {
  const byDepth: Record<number, CollaborationNode[]> = {}
  for (const node of agentNodes.value) {
    const d = getAgentDepth(node.id)
    if (!byDepth[d]) byDepth[d] = []
    byDepth[d].push(node)
  }
  // 按 depth 排序返回
  const sorted: Record<number, CollaborationNode[]> = {}
  Object.keys(byDepth)
    .map(Number)
    .sort((a, b) => a - b)
    .forEach(d => { sorted[d] = byDepth[d] })
  return sorted
})

// 层级标题
function getLevelTitle(level: number): string {
  if (level === 0) return '主控'
  if (level === 1) return '一级子代理'
  return `${level}级子代理`
}

// Agent 颜色
const AGENT_COLORS: Record<string, string> = {
  'analyst-agent': '#10b981',
  'architect-agent': '#f59e0b',
  'devops-agent': '#8b5cf6',
  'test-agent': '#ec4899',
  'frontend-agent': '#06b6d4',
  'backend-agent': '#f43f5e'
}

function getAgentColor(agentId: string): string {
  if (agentId === computedMainAgentId.value) return '#4a9eff'
  return AGENT_COLORS[agentId] || '#64748b'
}

// 图例
const legendAgentIds = computed(() => agentNodes.value.map(n => n.id).filter(Boolean))

const connectionLabel = computed(() => {
  const labels: Record<string, string> = {
    connected: '已连接',
    connecting: '连接中...',
    disconnected: '未连接',
    error: '连接错误'
  }
  return labels[connectionState.value.status] || '未知'
})

// 获取 Agent 层级深度
function getAgentDepth(agentId: string): number {
  // 主 agent depth=0，其他默认 depth=1
  if (agentId === computedMainAgentId.value) {
    return depths.value[agentId] ?? 0
  }
  return depths.value[agentId] ?? 1
}

function getAgentName(agentId: string): string {
  const node = agentNodes.value.find(n => n.id === agentId)
  return node?.name || agentId
}

function getAgentForNode(node: CollaborationNode): AgentForCard {
  const statusMap = (s: string): 'idle' | 'working' | 'down' =>
    s === 'error' ? 'down' : (s as 'idle' | 'working')

  const fromProps = node.id === computedMainAgentId.value
    ? props.mainAgent
    : props.subAgents?.find(a => a.id === node.id)

  if (fromProps && node.type === 'agent') {
    // 状态以协作 /dynamic 刷新的 node 为准（与 agentStatuses、连线同源），避免仅跟 WS agents 延迟不一致
    const collabTasks = getAgentActiveTasks(node.id)
    let taskLine: string | undefined
    const liveIdle = node.status === 'idle' || node.status === 'error'
    // 空闲/异常时不展示「当前任务」，也不回退 props（避免 agents 通道晚一拍仍带旧 currentTask）
    if (!liveIdle) {
      if (collabTasks?.length === 1) taskLine = collabTasks[0].name
      else if (collabTasks && collabTasks.length > 1) taskLine = `${collabTasks.length} 个任务进行中`
    }
    const fallbackTask = liveIdle ? undefined : fromProps.currentTask
    return {
      name: fromProps.name,
      status: statusMap(node.status),
      currentTask: taskLine ?? fallbackTask,
      lastActiveFormatted: fromProps.lastActiveFormatted
    }
  }
  if (fromProps) {
    return {
      name: fromProps.name,
      status: fromProps.status,
      currentTask: fromProps.currentTask,
      lastActiveFormatted: fromProps.lastActiveFormatted
    }
  }
  return { name: node.name, status: statusMap(node.status) }
}

function getModelInfoForNode(node: CollaborationNode): { primary?: string; fallbacks?: string[] } | undefined {
  if (node.type !== 'agent') return undefined
  return agentModels.value[node.id]
}

function getAgentActiveTasks(agentId: string): ActiveTask[] | undefined {
  return agentActiveTasks.value[agentId]
}

function getAgentTasks(agentId: string): TaskInfo[] {
  const tasks = nodes.value.filter(n => n.type === 'task')
  const taskEdges = edges.value.filter(e => e.type === 'calls' && e.source === agentId)
  return taskEdges.map(edge => {
    const taskNode = tasks.find(t => t.id === edge.target)
    if (!taskNode) return null
    return {
      id: taskNode.id,
      name: taskNode.name,
      status: taskNode.status === 'working' ? 'working' :
              taskNode.status === 'completed' ? 'completed' :
              taskNode.status === 'error' ? 'failed' : 'pending',
      time: taskNode.timestamp ? new Date(taskNode.timestamp).toLocaleTimeString() : undefined
    }
  }).filter(Boolean) as TaskInfo[]
}

function isActiveNode(node: CollaborationNode): boolean {
  return activePath.value.includes(node.id)
}

function isActiveEdge(edge: CollaborationEdge): boolean {
  return activePath.value.includes(edge.source) && activePath.value.includes(edge.target)
}

// 计算连线路径
function getEdgePath(edge: CollaborationEdge): string {
  const sourceEl = agentRefs.value[edge.source]
  const targetEl = agentRefs.value[edge.target]
  const areaEl = agentAreaRef.value

  if (!sourceEl || !targetEl || !areaEl) return ''

  const areaRect = areaEl.getBoundingClientRect()
  const sourceRect = sourceEl.getBoundingClientRect()
  const targetRect = targetEl.getBoundingClientRect()

  // 相对于 agent-area 的坐标
  const x1 = sourceRect.left - areaRect.left + sourceRect.width / 2
  const y1 = sourceRect.top - areaRect.top + sourceRect.height
  const x2 = targetRect.left - areaRect.left + targetRect.width / 2
  const y2 = targetRect.top - areaRect.top

  const cy = (y1 + y2) / 2
  return `M ${x1} ${y1} C ${x1} ${cy}, ${x2} ${cy}, ${x2} ${y2}`
}

// 更新 SVG 尺寸和连线
function updateEdges() {
  nextTick(() => {
    if (!agentAreaRef.value || !edgesSvgRef.value) return
    const rect = agentAreaRef.value.getBoundingClientRect()
    edgesSvgRef.value.setAttribute('width', String(rect.width))
    edgesSvgRef.value.setAttribute('height', String(rect.height))
  })
}

// 模型相关
const callsPerModel = computed(() => {
  const map: Record<string, ModelCall[]> = {}
  for (const c of recentCalls.value) {
    const mid = c.model || '(unknown)'
    if (!map[mid]) map[mid] = []
    map[mid].push(c)
  }
  return map
})

function getCallsForModelNode(node: CollaborationNode): ModelCall[] {
  const modelId = (node.metadata as { modelId?: string })?.modelId || ''
  const short = modelId.split('/').pop() || modelId
  return callsPerModel.value[modelId] || callsPerModel.value[short] || []
}

function isModelActive(node: CollaborationNode): boolean {
  return getCallsForModelNode(node).length > 0
}

async function fetchData(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const response = await fetch('/api/collaboration')
    if (!response.ok) throw new Error('Failed to fetch collaboration data')
    const data: CollaborationFlow = await response.json()
    nodes.value = data.nodes || []
    edges.value = data.edges || []
    activePath.value = data.activePath || []
    agentModels.value = data.agentModels || {}
    recentCalls.value = data.recentCalls || []
    if (data.hierarchy) hierarchy.value = data.hierarchy
    if (data.depths) depths.value = data.depths
    if (data.mainAgentId) backendMainAgentId.value = data.mainAgentId
    if (data.agentActiveTasks) agentActiveTasks.value = data.agentActiveTasks

    nextTick(updateEdges)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function refreshData(): void {
  fetchData()
}

function handleCollaborationUpdate(data: unknown): void {
  const flow = data as CollaborationFlow
  nodes.value = flow.nodes || []
  edges.value = flow.edges || []
  activePath.value = flow.activePath || []
  agentModels.value = flow.agentModels || {}
  recentCalls.value = flow.recentCalls || []
  if (flow.hierarchy) hierarchy.value = flow.hierarchy
  if (flow.depths) depths.value = flow.depths
  if (flow.mainAgentId) backendMainAgentId.value = flow.mainAgentId
  if (flow.agentActiveTasks) agentActiveTasks.value = flow.agentActiveTasks
  nextTick(updateEdges)
}

function handleCollaborationDynamicUpdate(dyn: CollaborationDynamic): void {
  activePath.value = dyn.activePath || []
  recentCalls.value = dyn.recentCalls || []
  if (dyn.agentActiveTasks) agentActiveTasks.value = dyn.agentActiveTasks
  const agentNodesLocal = nodes.value.filter(n => n.type === 'agent')
  for (const node of agentNodesLocal) {
    if (node.id && dyn.agentStatuses && dyn.agentStatuses[node.id] !== undefined) {
      node.status = dyn.agentStatuses[node.id] as CollaborationNode['status']
    }
    // 更新详细状态 (TR5)
    if (node.id && dyn.agentDynamicStatuses && dyn.agentDynamicStatuses[node.id]) {
      const dynStatus = dyn.agentDynamicStatuses[node.id]
      node.subStatus = dynStatus.subStatus
      node.currentAction = dynStatus.currentAction
      node.toolName = dynStatus.toolName
      node.waitingFor = dynStatus.waitingFor
    }
    // 更新显示状态 (TR9-1：基于时间阈值)
    if (node.id && dyn.agentDisplayStatuses && dyn.agentDisplayStatuses[node.id]) {
      const displayStatus = dyn.agentDisplayStatuses[node.id]
      node.currentAction = displayStatus.display
      // 存储 duration 和 alert 到 metadata
      if (!node.metadata) node.metadata = {}
      node.metadata = {
        ...node.metadata,
        duration: displayStatus.duration,
        alert: displayStatus.alert
      }
      // 设置 alert 标志用于 UI 警告样式
      if (displayStatus.alert) {
        node.stuckWarning = {
          isStuck: true,
          idleSeconds: displayStatus.duration,
          lastUpdate: Date.now(),
          reason: 'self_busy',
          reasonDetail: displayStatus.display
        }
      } else {
        // 清除警告
        if (node.stuckWarning && !node.stuckWaitingForChildAgent) {
          node.stuckWarning = undefined
        }
      }
    }
  }
  const taskIdsBefore = new Set(nodes.value.filter(n => n.type === 'task').map(n => n.id))
  const taskIdsAfter = new Set((dyn.taskNodes || []).map(n => n.id))
  const topologyChanged = taskIdsBefore.size !== taskIdsAfter.size ||
    [...taskIdsAfter].some(id => !taskIdsBefore.has(id))
  if (topologyChanged) {
    const modelNodesLocal = nodes.value.filter(n => n.type === 'model')
    const delegateEdgesLocal = edges.value.filter(e => e.type === 'delegates')
    nodes.value = [...agentNodesLocal, ...(dyn.taskNodes || []), ...modelNodesLocal]
    edges.value = [...delegateEdgesLocal, ...(dyn.taskEdges || [])]
    nextTick(updateEdges)
  } else {
    const taskNodeMap = new Map((dyn.taskNodes || []).map(n => [n.id, n]))
    for (const t of nodes.value.filter(n => n.type === 'task')) {
      const updated = taskNodeMap.get(t.id)
      if (updated) {
        t.status = updated.status
        t.name = updated.name
        if (updated.timestamp) t.timestamp = updated.timestamp
      }
    }
  }
}

async function fetchDynamicData(): Promise<void> {
  if (loading.value || nodes.value.length === 0) return
  try {
    const res = await fetch('/api/collaboration/dynamic')
    if (!res.ok) return
    const data: CollaborationDynamic = await res.json()
    handleCollaborationDynamicUpdate(data)
  } catch {
    // 静默失败
  }
}

let unsubscribe: (() => void) | null = null
let dynamicPollTimer: ReturnType<typeof setInterval> | null = null

watch([agentNodes, modelPanelExpanded], () => {
  nextTick(updateEdges)
})

onMounted(() => {
  fetchData()
  unsubscribe = subscribe('collaboration', handleCollaborationUpdate)
  dynamicPollTimer = setInterval(fetchDynamicData, DYNAMIC_POLL_INTERVAL_MS)
  window.addEventListener('resize', updateEdges)
})

onUnmounted(() => {
  if (unsubscribe) unsubscribe()
  if (dynamicPollTimer) clearInterval(dynamicPollTimer)
  window.removeEventListener('resize', updateEdges)
})
</script>

<style scoped>
.collaboration-flow-section {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  padding: 1.5rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.section-header .header-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.section-header h2 {
  margin: 0;
  font-size: 1.3rem;
  color: #333;
}

.connection-indicator {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
  padding: 0.25rem 0.6rem;
  border-radius: 12px;
  background: #f1f5f9;
}

.connection-indicator.connected { background: #dcfce7; color: #166534; }
.connection-indicator.connecting { background: #fef3c7; color: #92400e; }
.connection-indicator.disconnected,
.connection-indicator.error { background: #fee2e2; color: #991b1b; }

.indicator-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.connection-indicator.connecting .indicator-dot {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.flow-container {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fafbfc;
  min-height: 480px;
  position: relative;
  overflow: auto;
}

.loading-state, .error-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 280px;
  gap: 0.75rem;
  color: #6b7280;
}

.spinner {
  width: 28px;
  height: 28px;
  border: 3px solid #e5e7eb;
  border-top-color: #4a9eff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.retry-btn {
  padding: 0.4rem 0.8rem;
  background: #4a9eff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
}

/* 主布局 */
.flow-layout {
  display: flex;
  min-height: 460px;
}

/* Agent 区域 */
.agent-area {
  flex: 1;
  position: relative;
  padding: 1rem 1rem 2rem 0.5rem;
  min-width: 300px;
}

/* 层级区块 - 建立堆叠上下文，确保卡片在连线 SVG 之上 */
.level-section {
  margin-bottom: 1.5rem;
  position: relative;
  z-index: 1;
}

/* L0 主控层：与子 agent 拉开距离 */
.level-section:first-child {
  margin-bottom: 2.5rem;
  z-index: 2;
}

.level-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  padding-left: 0.5rem;
}

.level-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 20px;
  background: #e0e7ff;
  color: #4338ca;
  font-size: 0.65rem;
  font-weight: 700;
  border-radius: 4px;
}

.level-title {
  font-size: 0.75rem;
  color: #64748b;
  font-weight: 500;
}

/* L0 层（主 agent）- 居中 */
.level-cards {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  justify-content: center;
  padding: 0.5rem;
}

/* L0 层卡片容器 - 移除固定高度 */
.level-section:first-child .level-cards {
  min-height: auto;
  padding-bottom: 1rem;
}

/* 子 agent 层级 - 使用 grid 均匀分布 */
.level-section:not(:first-child) .level-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  max-width: 900px;
  margin: 0 auto;
}

/* Agent 卡片 - z-index 确保在连线 SVG 之上 */
.agent-card-wrapper {
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  border-radius: 12px;
  position: relative;
  z-index: 1;
  overflow: hidden;
}

/* 主 agent 卡片 - 更大 */
.level-section:first-child .agent-card-wrapper.main-agent {
  width: 320px;
  max-width: 100%;
}

.agent-card-wrapper:hover {
  transform: translateY(-2px);
}

.agent-card-wrapper.active {
  box-shadow: 0 0 0 3px rgba(74, 158, 255, 0.25);
}

/* 卡片左侧颜色条 - 用于区分不同 agent，与主框圆角对齐 */
.agent-card-wrapper::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 4px 0 0 4px;
  background: var(--agent-color, #64748b);
  z-index: 1;
}

/* 连线 SVG - 置于最上层才能可见（level-section 为块级覆盖整区，z-index 低会被完全遮挡） */
.edges-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 5;
}

.edge-path {
  fill: none;
  stroke: #4a9eff;
  stroke-width: 2;
}

.edge-path.active {
  stroke-width: 2.5;
  stroke-dasharray: 6 4;
  animation: flowAnim 1s linear infinite;
}

@keyframes flowAnim {
  to { stroke-dashoffset: -10; }
}

/* 模型面板 */
.model-panel {
  width: 150px;
  min-width: 120px;
  border-left: 1px solid #e5e7eb;
  background: #f8fafc;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}

.model-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.6rem;
  background: #f1f5f9;
  border-bottom: 1px solid #e5e7eb;
  cursor: pointer;
}

.model-panel-title {
  font-size: 0.7rem;
  font-weight: 600;
  color: #475569;
}

.model-toggle-icon {
  font-size: 0.6rem;
  color: #94a3b8;
}

.model-panel-body {
  flex: 1;
  padding: 0.4rem;
  overflow-y: auto;
}

.model-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 5px;
  padding: 0.4rem 0.5rem;
  margin-bottom: 0.4rem;
}

.model-card.active {
  border-color: #f97316;
}

.model-name {
  font-size: 0.65rem;
  font-weight: 600;
  font-family: ui-monospace, monospace;
  color: #334155;
  margin-bottom: 0.25rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.model-dots {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  margin-bottom: 0.2rem;
}

.model-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  cursor: pointer;
}

.model-dot:hover {
  transform: scale(1.3);
}

.model-count {
  font-size: 0.55rem;
  color: #94a3b8;
}

/* 图例 - 移至标题行，避免遮挡 agent 卡片 */
.flow-legend.flow-legend-inline {
  position: static;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.25rem 0.5rem;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  font-size: 0.7rem;
  color: #475569;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f8fafc;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 3px;
}

.legend-name {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

/* 调用详情弹窗 */
.call-detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.call-detail-modal {
  background: white;
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  min-width: 300px;
  max-width: 90%;
}

.call-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.6rem 0.9rem;
  border-bottom: 1px solid #e5e7eb;
}

.call-detail-header h3 {
  margin: 0;
  font-size: 0.9rem;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
  color: #6b7280;
  line-height: 1;
}

.call-detail-body {
  padding: 0.6rem 0.9rem;
}

.call-detail-row {
  display: flex;
  gap: 0.6rem;
  margin-bottom: 0.4rem;
}

.call-detail-row .label {
  color: #6b7280;
  min-width: 45px;
  font-size: 0.8rem;
}

.call-detail-row .value {
  color: #333;
  font-size: 0.8rem;
  word-break: break-word;
}

.call-detail-row.trigger .value {
  font-size: 0.75rem;
}

/* 响应式适配 */
@media (max-width: 1280px) {
  .level-section:first-child .agent-card-wrapper.main-agent {
    width: 280px;
  }

  .level-section:not(:first-child) .level-cards {
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  }

  .model-panel {
    width: 130px;
  }
}

@media (max-width: 1024px) {
  .flow-layout {
    flex-direction: column;
  }

  .model-panel {
    width: 100%;
    border-left: none;
    border-top: 1px solid #e5e7eb;
    max-height: 200px;
  }

  .model-panel-body {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .model-card {
    flex: 1;
    min-width: 120px;
    margin-bottom: 0;
  }
}
</style>
