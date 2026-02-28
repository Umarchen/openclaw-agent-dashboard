<template>
  <div class="collaboration-flow-section">
    <div class="section-header">
      <h2>协作流程</h2>
      <div class="connection-indicator" :class="connectionState.status">
        <span class="indicator-dot"></span>
        <span class="indicator-text">{{ connectionLabel }}</span>
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

      <div v-else class="flow-canvas" :style="canvasStyle">
        <!-- Edges -->
        <svg class="edges-layer" :width="canvasWidth" :height="canvasHeight">
          <defs>
            <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="currentColor" />
            </marker>
            <linearGradient id="lightGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" style="stop-color:#4a9eff;stop-opacity:0.2" />
              <stop offset="50%" style="stop-color:#4a9eff;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#4a9eff;stop-opacity:0.2" />
            </linearGradient>
            <linearGradient v-for="(color, aid) in AGENT_COLORS" :key="aid" :id="`lightGradient-${aid}`" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" :style="`stop-color:${color};stop-opacity:0.2`" />
              <stop offset="50%" :style="`stop-color:${color};stop-opacity:1`" />
              <stop offset="100%" :style="`stop-color:${color};stop-opacity:0.2`" />
            </linearGradient>
            <linearGradient id="lightGradient-default" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" style="stop-color:#64748b;stop-opacity:0.2" />
              <stop offset="50%" style="stop-color:#64748b;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#64748b;stop-opacity:0.2" />
            </linearGradient>
          </defs>
          <g v-for="edge in visibleEdges" :key="edge.id">
            <path
              :id="`edge-path-${edge.id}`"
              :d="getEdgePath(edge)"
              class="edge-path"
              :class="{ active: isActiveEdge(edge) || (edge.type === 'model' && hasActiveCallsOnModelEdge(edge)) }"
              :stroke="getEdgeStrokeColor(edge)"
              :style="{ color: getEdgeStrokeColor(edge) }"
              fill="none"
              stroke-linecap="round"
              marker-end="url(#arrowhead)"
            />
            <!-- 委托边光球：用 mpath 引用同一条路径，确保沿线运动 -->
            <circle
              v-if="edge.type === 'delegates' && isActiveEdge(edge)"
              r="8"
              class="light-ball"
              fill="url(#lightGradient)"
            >
              <animateMotion
                :dur="getAnimationDuration(edge)"
                repeatCount="1"
                rotate="0"
              >
                <mpath :href="`#edge-path-${edge.id}`" />
              </animateMotion>
            </circle>
            <!-- 模型边光球：用 mpath 引用同一条路径 -->
            <circle
              v-if="edge.type === 'model' && hasActiveCallsOnModelEdge(edge)"
              r="8"
              class="light-ball"
              :fill="`url(#lightGradient-${AGENT_COLORS[edge.source] ? edge.source : 'default'})`"
            >
              <animateMotion
                dur="2.5s"
                repeatCount="1"
                rotate="0"
              >
                <mpath :href="`#edge-path-${edge.id}`" />
              </animateMotion>
            </circle>
            <text v-if="edge.label && edge.type !== 'model'" :x="getEdgeLabelX(edge)" :y="getEdgeLabelY(edge)" class="edge-label">
              {{ edge.label }}
            </text>
          </g>
        </svg>

        <!-- Nodes: Agent 用 AgentCard 样式，任务/工具用小卡片 -->
        <template v-for="node in nodes" :key="node.id">
          <!-- Agent 节点：主 Agent 和子 Agents 使用 AgentCard 格式 -->
          <div
            v-if="node.type === 'agent'"
            class="flow-node agent-card-wrapper"
            :class="[`status-${node.status}`, { active: isActiveNode(node), 'main-agent': node.id === 'main' }]"
            :style="getNodeStyle(node)"
          >
            <AgentCard
              :agent="getAgentForNode(node)"
              :model-info="getModelInfoForNode(node)"
              @click="emit('agent-click', node)"
            />
          </div>
          <!-- 模型节点（可折叠） -->
          <div
            v-else-if="node.type === 'model' && modelPanelExpanded"
            class="flow-node model-node"
            :style="getNodeStyle(node)"
          >
            <div class="model-name">{{ node.name }}</div>
            <div class="model-bar">
              <div
                v-for="(call, idx) in getCallsForModelNode(node)"
                :key="call.id"
                class="call-bead"
                :style="{ background: getAgentColor(call.agentId) }"
                :title="`${call.agentId} @ ${call.time}`"
                @click.stop="selectedCall = call"
              />
            </div>
          </div>
          <!-- 任务/工具节点 -->
          <div
            v-else
            class="flow-node"
            :class="[`type-${node.type}`, `status-${node.status}`, { active: isActiveNode(node) }]"
            :style="getNodeStyle(node)"
            @mouseenter="hoveredNode = node.id"
            @mouseleave="hoveredNode = null"
          >
            <div class="node-icon">{{ getNodeIcon(node) }}</div>
            <div class="node-name">{{ node.name }}</div>
            <div class="node-status">{{ getNodeStatusLabel(node.status) }}</div>
            <div v-if="hoveredNode === node.id" class="node-tooltip">
              <div class="tooltip-row">
                <span class="tooltip-label">类型:</span>
                <span class="tooltip-value">{{ node.type }}</span>
              </div>
              <div class="tooltip-row">
                <span class="tooltip-label">状态:</span>
                <span class="tooltip-value">{{ getNodeStatusLabel(node.status) }}</span>
              </div>
              <div v-if="node.timestamp" class="tooltip-row">
                <span class="tooltip-label">更新:</span>
                <span class="tooltip-value">{{ formatTime(node.timestamp) }}</span>
              </div>
            </div>
          </div>
        </template>
      </div>

      <!-- 浮动图例：仅展示当前视图中的 Agent -->
      <div v-if="nodes.length > 0" class="flow-legend flow-legend-floating">
        <div v-for="aid in legendAgentIds" :key="aid" class="legend-item">
          <span class="legend-dot" :style="{ background: getAgentColor(aid) }"></span>
          <span>{{ getAgentName(aid) }}</span>
        </div>
        <div class="legend-item">
          <span class="legend-dot active"></span>
          <span>活跃</span>
        </div>
      </div>

      <!-- 模型区折叠切换 -->
      <div
        v-if="nodes.length > 0 && hasModelNodes"
        class="model-panel-toggle"
        @click="modelPanelExpanded = !modelPanelExpanded"
      >
        <span class="toggle-text">{{ modelPanelExpanded ? '收起模型' : '展开模型' }}</span>
        <span class="toggle-icon">{{ modelPanelExpanded ? '▼' : '▶' }}</span>
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
          <div v-if="selectedCall.trigger?.startsWith('【完成回传】')" class="call-detail-row trigger-type-badge">
            <span class="trigger-badge">完成回传</span>
            <span class="trigger-badge-desc">此时间戳为子任务完成后的回传时间，不是派发时间。因果顺序：派发 → 子Agent执行 → 完成回传</span>
          </div>
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
            <div class="value">
              <span>{{ selectedCall.trigger?.replace(/^【完成回传】/, '') }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRealtime } from '../../composables'
import AgentCard from '../AgentCard.vue'
import type { CollaborationNode, CollaborationEdge, CollaborationFlow, CollaborationDynamic, ModelCall } from '../../types'

const DYNAMIC_POLL_INTERVAL_MS = 5000

interface AgentForCard {
  name: string
  status: 'idle' | 'working' | 'down'
  currentTask?: string
  lastActiveFormatted?: string
}

const props = defineProps<{
  mainAgent?: AgentForCard & { id?: string } | null
  subAgents?: (AgentForCard & { id?: string })[]
}>()

const emit = defineEmits<{
  'agent-click': [node: CollaborationNode]
}>()

const { connectionState, subscribe, connect } = useRealtime()

const nodes = ref<CollaborationNode[]>([])
const edges = ref<CollaborationEdge[]>([])
const activePath = ref<string[]>([])
const agentModels = ref<Record<string, { primary?: string; fallbacks?: string[] }>>({})
const recentCalls = ref<ModelCall[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const hoveredNode = ref<string | null>(null)
const flowContainerRef = ref<HTMLElement | null>(null)
const selectedCall = ref<ModelCall | null>(null)

// 节点尺寸常量
const agentNodeWidth = 300
const agentNodeHeight = 140
const taskNodeWidth = 160
const taskNodeHeight = 90
const modelNodeWidth = 140
const modelNodeHeight = 80
const margin = 80
const minCanvasWidth = 900
const minCanvasHeight = 600

// Agent 光球颜色（按 agentId 区分）
const AGENT_COLORS: Record<string, string> = {
  main: '#4a9eff',
  'analyst-agent': '#10b981',
  'architect-agent': '#f59e0b',
  'devops-agent': '#8b5cf6'
}
function getAgentColor(agentId: string): string {
  return AGENT_COLORS[agentId] || '#64748b'
}

// 图例：仅展示当前视图中的 Agent
const legendAgentIds = computed(() => {
  return nodes.value.filter(n => n.type === 'agent').map(n => n.id).filter(Boolean)
})

// 是否有模型节点（用于显示折叠面板）
const hasModelNodes = computed(() => nodes.value.some(n => n.type === 'model'))

// 模型区是否展开
const modelPanelExpanded = ref(true)

// 可见边：折叠时隐藏模型边
const visibleEdges = computed(() => {
  if (modelPanelExpanded.value) return edges.value
  return edges.value.filter(e => e.type !== 'model')
})

// 动态画布尺寸：根据节点数量计算
const layoutMetrics = computed(() => {
  const mainNodes = nodes.value.filter(n => n.type === 'agent' || n.type === 'task' || n.type === 'tool')
  const modelNodes = nodes.value.filter(n => n.type === 'model')
  const subAgentCount = mainNodes.filter(n => n.type === 'agent' && n.id !== 'main').length
  const taskCount = mainNodes.filter(n => n.type === 'task').length
  const toolCount = mainNodes.filter(n => n.type === 'tool').length

  const rowGap = 120
  const agentColGap = Math.max(80, 150 - subAgentCount * 10)
  const taskColGap = Math.max(60, 120 - taskCount * 8)
  const toolColGap = Math.max(60, 120 - toolCount * 8)

  const mainAreaWidth = Math.max(
    minCanvasWidth - margin * 2,
    subAgentCount * agentNodeWidth + Math.max(0, subAgentCount - 1) * agentColGap,
    taskCount * taskNodeWidth + Math.max(0, taskCount - 1) * taskColGap,
    toolCount * taskNodeWidth + Math.max(0, toolCount - 1) * toolColGap
  )

  const mainAreaHeight = margin * 2 + agentNodeHeight + rowGap + agentNodeHeight + rowGap
    + (taskCount > 0 ? taskNodeHeight + rowGap : 0)
    + (toolCount > 0 ? taskNodeHeight + rowGap : 0)

  const modelRows = modelNodes.length
  const modelPanelHeight = modelPanelExpanded.value && modelRows > 0
    ? margin + modelRows * (modelNodeHeight + 16) + margin
    : 0

  const canvasWidth = Math.max(minCanvasWidth, mainAreaWidth + margin * 2)
  const canvasHeight = Math.max(minCanvasHeight, mainAreaHeight + modelPanelHeight)

  return {
    canvasWidth,
    canvasHeight,
    mainAreaWidth,
    rowGap,
    agentColGap,
    taskColGap,
    toolColGap
  }
})

const canvasWidth = computed(() => layoutMetrics.value.canvasWidth)
const canvasHeight = computed(() => layoutMetrics.value.canvasHeight)

function getAgentName(agentId: string): string {
  const node = nodes.value.find(n => n.id === agentId)
  return node?.name || agentId
}

// 边颜色：模型降级用橙色，其余用灰色/蓝色
function getEdgeStrokeColor(edge: CollaborationEdge): string {
  if (edge.metadata && (edge.metadata as { isFallback?: boolean }).isFallback) return '#f97316'
  const isActive = isActiveEdge(edge) || (edge.type === 'model' && hasActiveCallsOnModelEdge(edge))
  return isActive ? '#4a9eff' : '#94a3b8'
}

const canvasStyle = computed(() => ({
  width: `${canvasWidth.value}px`,
  height: `${canvasHeight.value}px`,
  minWidth: `${minCanvasWidth}px`
}))

const connectionLabel = computed(() => {
  switch (connectionState.value.status) {
    case 'connected':
      return '已连接'
    case 'connecting':
      return '连接中...'
    case 'disconnected':
      return '未连接'
    case 'error':
      return '连接错误'
    default:
      return '未知'
  }
})

// 获取节点尺寸
function getNodeWidth(node: CollaborationNode): number {
  if (node.type === 'agent') return agentNodeWidth
  if (node.type === 'model') return modelNodeWidth
  return taskNodeWidth
}
function getNodeHeight(node: CollaborationNode): number {
  if (node.type === 'agent') return agentNodeHeight
  if (node.type === 'model') return modelNodeHeight
  return taskNodeHeight
}

// 将协作节点转为 AgentCard 所需的 agent 格式
function getAgentForNode(node: CollaborationNode): AgentForCard {
  const statusMap = (s: string): 'idle' | 'working' | 'down' =>
    s === 'error' ? 'down' : (s as 'idle' | 'working')
  if (node.type !== 'agent') {
    return { name: node.name, status: statusMap(node.status) }
  }
  const fromProps = node.id === 'main'
    ? props.mainAgent
    : props.subAgents?.find(a => a.id === node.id)
  if (fromProps) {
    return {
      name: fromProps.name,
      status: fromProps.status,
      currentTask: fromProps.currentTask,
      lastActiveFormatted: fromProps.lastActiveFormatted
    }
  }
  return {
    name: node.name,
    status: statusMap(node.status)
  }
}

function getModelInfoForNode(node: CollaborationNode): { primary?: string; fallbacks?: string[] } | undefined {
  if (node.type !== 'agent') return undefined
  const models = agentModels.value
  if (!models || typeof models !== 'object' || Array.isArray(models)) return undefined
  return models[node.id]
}

// 自动布局 - 主区域流式排列，模型区整合在底部
function autoLayoutNodes(nodeList: CollaborationNode[]): void {
  const mainNode = nodeList.find(n => n.id === 'main')
  const subAgentNodes = nodeList.filter(n => n.type === 'agent' && n.id !== 'main')
  const taskNodes = nodeList.filter(n => n.type === 'task')
  const toolNodes = nodeList.filter(n => n.type === 'tool')
  const modelNodes = nodeList.filter(n => n.type === 'model')

  const rowGap = 120
  const agentColGap = Math.max(80, 150 - subAgentNodes.length * 10)
  const taskColGap = Math.max(60, 120 - taskNodes.length * 8)
  const toolColGap = Math.max(60, 120 - toolNodes.length * 8)

  const mainAreaWidth = Math.max(
    minCanvasWidth - margin * 2,
    subAgentNodes.length * agentNodeWidth + Math.max(0, subAgentNodes.length - 1) * agentColGap,
    taskNodes.length * taskNodeWidth + Math.max(0, taskNodes.length - 1) * taskColGap,
    toolNodes.length * taskNodeWidth + Math.max(0, toolNodes.length - 1) * toolColGap
  )

  // 第 1 行：主 Agent 居中
  const row1Y = margin
  if (mainNode) {
    mainNode.position = {
      x: (mainAreaWidth - agentNodeWidth) / 2 + margin,
      y: row1Y
    }
  }

  // 第 2 行：子 Agents 横向排列居中
  const row2Y = row1Y + agentNodeHeight + rowGap
  const subAgentsTotalW = subAgentNodes.length * agentNodeWidth + Math.max(0, subAgentNodes.length - 1) * agentColGap
  const subAgentsStartX = (mainAreaWidth - subAgentsTotalW) / 2 + margin
  subAgentNodes.forEach((node, i) => {
    node.position = {
      x: subAgentsStartX + i * (agentNodeWidth + agentColGap),
      y: row2Y
    }
  })

  // 第 3 行：任务节点居中
  const row3Y = row2Y + agentNodeHeight + rowGap
  const taskTotalW = taskNodes.length * taskNodeWidth + Math.max(0, taskNodes.length - 1) * taskColGap
  const taskStartX = (mainAreaWidth - taskTotalW) / 2 + margin
  taskNodes.forEach((node, i) => {
    node.position = {
      x: taskStartX + i * (taskNodeWidth + taskColGap),
      y: row3Y
    }
  })

  // 第 4 行：工具节点居中
  const row4Y = row3Y + (taskNodes.length > 0 ? taskNodeHeight + rowGap : 0)
  const toolTotalW = toolNodes.length * taskNodeWidth + Math.max(0, toolNodes.length - 1) * toolColGap
  const toolStartX = (mainAreaWidth - toolTotalW) / 2 + margin
  toolNodes.forEach((node, i) => {
    node.position = {
      x: toolStartX + i * (taskNodeWidth + toolColGap),
      y: row4Y
    }
  })

  // 模型区：整合在底部，横向排列，居中（仅当 modelPanelExpanded 时布局）
  if (modelPanelExpanded.value && modelNodes.length > 0) {
    const modelAreaY = row4Y + (toolNodes.length > 0 ? taskNodeHeight + rowGap : 0) + margin
    const modelGap = 16
    const modelTotalW = modelNodes.length * modelNodeWidth + Math.max(0, modelNodes.length - 1) * modelGap
    const modelStartX = Math.max(margin, (mainAreaWidth + margin * 2 - modelTotalW) / 2)
    modelNodes.forEach((node, i) => {
      node.position = {
        x: modelStartX + i * (modelNodeWidth + modelGap),
        y: modelAreaY
      }
    })
  } else {
    modelNodes.forEach(node => {
      node.position = { x: 0, y: 0 }
    })
  }
}

function getNodeStyle(node: CollaborationNode): Record<string, string> {
  const pos = node.position || { x: 0, y: 0 }
  const w = getNodeWidth(node)
  const h = getNodeHeight(node)
  return {
    left: `${pos.x}px`,
    top: `${pos.y}px`,
    width: `${w}px`,
    height: `${h}px`
  }
}

function getNodeIcon(node: CollaborationNode): string {
  switch (node.type) {
    case 'agent': return '🤖'
    case 'task': return '📋'
    case 'tool': return '🔧'
    case 'model': return '🧠'
    default: return '📍'
  }
}

function getNodeStatusLabel(status: string): string {
  // 符合 PRD: Agent 状态 空闲/工作中/异常
  const labels: Record<string, string> = {
    idle: '空闲',
    working: '工作中',
    active: '工作中',  // 兼容
    completed: '完成',
    error: '异常'
  }
  return labels[status] || status
}

function isActiveNode(node: CollaborationNode): boolean {
  return activePath.value.includes(node.id)
}

function isActiveEdge(edge: CollaborationEdge): boolean {
  return activePath.value.includes(edge.source) && activePath.value.includes(edge.target)
}

function getEdgePath(edge: CollaborationEdge): string {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  
  if (!source?.position || !target?.position) return ''
  
  const sw = getNodeWidth(source)
  const sh = getNodeHeight(source)
  const tw = getNodeWidth(target)
  const th = getNodeHeight(target)
  
  // 垂直连接：source 在上方 -> 从 source 底部中心到 target 顶部中心
  const isVertical = target.position.y > source.position.y + sh / 2
  if (isVertical) {
    const x1 = source.position.x + sw / 2
    const y1 = source.position.y + sh
    const x2 = target.position.x + tw / 2
    const y2 = target.position.y
    const cy = (y1 + y2) / 2
    return `M ${x1} ${y1} C ${x1} ${cy}, ${x2} ${cy}, ${x2} ${y2}`
  }
  
  // 水平连接：source 在左侧
  const x1 = source.position.x + sw
  const y1 = source.position.y + sh / 2
  const x2 = target.position.x
  const y2 = target.position.y + th / 2
  const cx = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`
}

function getEdgeLabelX(edge: CollaborationEdge): number {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  
  if (!source?.position || !target?.position) return 0
  const sw = getNodeWidth(source)
  const tw = getNodeWidth(target)
  const isVertical = target.position.y > source.position.y + getNodeHeight(source) / 2
  if (isVertical) {
    return (source.position.x + sw / 2 + target.position.x + tw / 2) / 2
  }
  return (source.position.x + sw + target.position.x) / 2
}

function getEdgeLabelY(edge: CollaborationEdge): number {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  
  if (!source?.position || !target?.position) return 0
  const sh = getNodeHeight(source)
  const isVertical = target.position.y > source.position.y + sh / 2
  if (isVertical) {
    return (source.position.y + sh + target.position.y) / 2 - 10
  }
  return (source.position.y + target.position.y) / 2 + sh / 2 - 10
}

function getLightBallX(edge: CollaborationEdge): number {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  if (!source?.position || !target?.position) return 0
  const sw = getNodeWidth(source)
  const isVertical = target.position.y > source.position.y + getNodeHeight(source) / 2
  return isVertical ? source.position.x + sw / 2 : source.position.x + sw
}

function getLightBallY(edge: CollaborationEdge): number {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  if (!source?.position || !target?.position) return 0
  const sh = getNodeHeight(source)
  const isVertical = target.position.y > source.position.y + sh / 2
  return isVertical ? source.position.y + sh : source.position.y + sh / 2
}

function getAnimationDuration(edge: CollaborationEdge): string {
  return edge.type === 'delegates' ? '3s' : '2s'
}

// 按模型分组的调用（用于模型侧光球串）
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

// 模型 ID 转节点 ID
function modelIdToNodeId(modelId: string): string {
  return `model-${modelId.replace('/', '-')}`
}

// 判断 agent->model 边是否有活跃调用（显示光球）
function hasActiveCallsOnModelEdge(edge: CollaborationEdge): boolean {
  if (edge.type !== 'model') return false
  const modelId = edge.label || ''
  const short = modelId.split('/').pop() || modelId
  const calls = callsPerModel.value[modelId] || callsPerModel.value[short] || []
  return calls.some(c => c.agentId === edge.source)
}

function getAgentColorForEdge(edge: CollaborationEdge): string {
  return getAgentColor(edge.source)
}

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString()
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
    
    autoLayoutNodes(nodes.value)
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
  autoLayoutNodes(nodes.value)
}

function handleCollaborationDynamicUpdate(dyn: CollaborationDynamic): void {
  activePath.value = dyn.activePath || []
  recentCalls.value = dyn.recentCalls || []

  const agentNodes = nodes.value.filter(n => n.type === 'agent')
  const modelNodes = nodes.value.filter(n => n.type === 'model')
  const toolNodes = nodes.value.filter(n => n.type === 'tool')
  const taskIdsBefore = new Set(nodes.value.filter(n => n.type === 'task').map(n => n.id))
  const taskIdsAfter = new Set((dyn.taskNodes || []).map(n => n.id))

  const topologyChanged = taskIdsBefore.size !== taskIdsAfter.size ||
    [...taskIdsAfter].some(id => !taskIdsBefore.has(id))

  for (const node of agentNodes) {
    if (node.id && dyn.agentStatuses && dyn.agentStatuses[node.id] !== undefined) {
      node.status = dyn.agentStatuses[node.id] as CollaborationNode['status']
    }
  }

  const delegatesEdges = edges.value.filter(e => e.type === 'delegates')
  const modelEdges = edges.value.filter(e => e.type === 'model')
  const taskEdges = dyn.taskEdges || []

  if (topologyChanged) {
    nodes.value = [...agentNodes, ...(dyn.taskNodes || []), ...toolNodes, ...modelNodes]
    edges.value = [...delegatesEdges, ...taskEdges, ...modelEdges]
    autoLayoutNodes(nodes.value)
  } else {
    const taskNodeMap = new Map((dyn.taskNodes || []).map(n => [n.id, n]))
    const currentTasks = nodes.value.filter(n => n.type === 'task')
    for (const t of currentTasks) {
      const updated = taskNodeMap.get(t.id)
      if (updated) {
        t.status = updated.status
        t.name = updated.name
        if (updated.timestamp) t.timestamp = updated.timestamp
      }
    }
    edges.value = [...delegatesEdges, ...taskEdges, ...modelEdges]
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

watch(modelPanelExpanded, () => {
  autoLayoutNodes(nodes.value)
})

onMounted(() => {
  fetchData()
  unsubscribe = subscribe('collaboration', handleCollaborationUpdate)
  dynamicPollTimer = setInterval(fetchDynamicData, DYNAMIC_POLL_INTERVAL_MS)
})

onUnmounted(() => {
  if (unsubscribe) unsubscribe()
  if (dynamicPollTimer) {
    clearInterval(dynamicPollTimer)
    dynamicPollTimer = null
  }
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
  gap: 0.75rem;
}

.section-header h2 {
  margin: 0;
  font-size: 1.3rem;
  color: #333;
}

.connection-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  background: #f1f5f9;
}

.connection-indicator.connected {
  background: #dcfce7;
  color: #166534;
}

.connection-indicator.connecting {
  background: #fef3c7;
  color: #92400e;
}

.connection-indicator.disconnected,
.connection-indicator.error {
  background: #fee2e2;
  color: #991b1b;
}

.indicator-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.connection-indicator.connecting .indicator-dot {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.2); }
}

.flow-container {
  overflow: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
  min-height: 520px;
  position: relative;
}

/* 模型区折叠切换 */
.model-panel-toggle {
  position: absolute;
  bottom: 1rem;
  right: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.8rem;
  color: #64748b;
  z-index: 15;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.model-panel-toggle:hover {
  background: #f8fafc;
  border-color: #4a9eff;
  color: #4a9eff;
}

.toggle-text {
  font-weight: 500;
}

.toggle-icon {
  font-size: 0.7rem;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  gap: 1rem;
  color: #6b7280;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e5e7eb;
  border-top-color: #4a9eff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.error-icon,
.empty-icon {
  font-size: 2rem;
}

.retry-btn {
  padding: 0.5rem 1rem;
  background: #4a9eff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.retry-btn:hover {
  background: #3a8eef;
}

.flow-canvas {
  position: relative;
  margin: 1rem;
  min-width: 800px;
}

.flow-canvas::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  width: 1400px;
  height: 100%;
  background: linear-gradient(90deg,
    rgba(74, 158, 255, 0.03) 0%,
    transparent 45%,
    rgba(139, 92, 246, 0.03) 100%);
  pointer-events: none;
  border-radius: 8px;
}

.edges-layer {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
}

.edge-path {
  fill: none;
  stroke-width: 2;
  transition: stroke 0.3s ease;
}

.edge-path.active {
  stroke-width: 2.5;
  stroke-dasharray: 8 4;
  animation: flow 1.2s linear infinite;
}

@keyframes flow {
  to { stroke-dashoffset: -12; }
}

.edge-label {
  font-size: 10px;
  fill: #6b7280;
  text-anchor: middle;
}

.flow-node {
  position: absolute;
  background: white;
  border: 2px solid #e5e7eb;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  margin: 2px;
}

.flow-node:hover {
  border-color: #4a9eff;
  box-shadow: 0 4px 12px rgba(74, 158, 255, 0.2);
}

.flow-node.clickable {
  cursor: pointer;
}

/* Agent 节点使用 AgentCard 样式，铺满容器 */
.flow-node.agent-card-wrapper {
  padding: 0;
  overflow: visible;
}

.flow-node.agent-card-wrapper :deep(.agent-card) {
  width: 100%;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
}

.flow-node.agent-card-wrapper.main-agent {
  transform: scale(1.08);
  transform-origin: center center;
  z-index: 2;
}

.flow-node.agent-card-wrapper.main-agent::before {
  content: 'PM';
  position: absolute;
  top: 4px;
  right: 8px;
  font-size: 0.65rem;
  font-weight: 600;
  color: #4a9eff;
  background: rgba(74, 158, 255, 0.12);
  padding: 2px 6px;
  border-radius: 4px;
  z-index: 1;
}

.flow-node.active {
  border-color: #4a9eff;
  box-shadow: 0 0 0 3px rgba(74, 158, 255, 0.2);
}

/* 模型节点 */
.flow-node.model-node {
  padding: 0.5rem 0.75rem;
  align-items: flex-start;
}

.model-name {
  font-size: 0.8rem;
  font-weight: 600;
  font-family: ui-monospace, 'Cascadia Code', monospace;
  color: #334155;
  margin-bottom: 0.5rem;
}

.model-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  width: 100%;
  min-height: 20px;
}

.call-bead {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  flex-shrink: 0;
}

.call-bead:hover {
  transform: scale(1.3);
  box-shadow: 0 0 8px currentColor;
}

/* 调用详情弹窗 */
.call-detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.call-detail-modal {
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  min-width: 360px;
  max-width: 90%;
}

.call-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #e5e7eb;
}

.call-detail-header h3 {
  margin: 0;
  font-size: 1rem;
}

.call-detail-header .close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #6b7280;
  line-height: 1;
}

.call-detail-body {
  padding: 1rem 1.25rem;
}

.call-detail-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.call-detail-row .label {
  font-weight: 500;
  color: #6b7280;
  min-width: 60px;
}

.call-detail-row .value {
  color: #333;
  word-break: break-word;
}

.trigger-type-badge {
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  padding: 0.6rem 0.75rem;
  background: #eff6ff;
  border: 1px solid #93c5fd;
  border-radius: 6px;
  margin-bottom: 0.25rem;
}

.trigger-badge {
  display: inline-block;
  font-size: 0.9rem;
  font-weight: 600;
  color: #1d4ed8;
  padding: 0.15rem 0.5rem;
  background: #dbeafe;
  border-radius: 4px;
}

.trigger-badge-desc {
  font-size: 0.8rem;
  color: #1e40af;
  line-height: 1.4;
}

.call-detail-row.trigger .value {
  font-size: 0.85rem;
  white-space: pre-wrap;
  word-break: break-word;
}

.flow-node.status-completed {
  border-color: #22c55e;
}

.flow-node.status-working {
  border-color: #3b82f6;
}

.flow-node.status-error {
  border-color: #ef4444;
}

.node-icon {
  font-size: 1.5rem;
  margin-bottom: 0.25rem;
}

.node-name {
  font-size: 0.85rem;
  font-weight: 500;
  color: #333;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  padding: 0 0.5rem;
}

.node-status {
  font-size: 0.7rem;
  color: #6b7280;
  margin-top: 0.25rem;
}

.node-tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: #1e293b;
  color: white;
  padding: 0.75rem;
  border-radius: 6px;
  font-size: 0.8rem;
  white-space: nowrap;
  z-index: 100;
  margin-bottom: 0.5rem;
}

.node-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: #1e293b;
}

.tooltip-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}

.tooltip-label {
  color: #94a3b8;
}

.flow-legend-floating {
  position: absolute;
  bottom: 1rem;
  right: 1rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
  font-size: 0.8rem;
  color: #64748b;
  z-index: 10;
}

.flow-legend-floating .legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.flow-legend-floating .legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #94a3b8;
  flex-shrink: 0;
}

.flow-legend-floating .legend-dot.active {
  background: #4a9eff;
}

/* 响应式 */
@media (max-width: 1024px) {
  .flow-canvas {
    min-width: 800px;
  }
}

@media (max-width: 640px) {
  .flow-legend-floating {
    bottom: 0.5rem;
    right: 0.5rem;
    padding: 0.5rem 0.75rem;
    font-size: 0.7rem;
    gap: 0.5rem;
  }
}
</style>
