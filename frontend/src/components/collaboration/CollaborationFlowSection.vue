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
            <!-- 光球渐变 -->
            <linearGradient id="lightGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" style="stop-color:#4a9eff;stop-opacity:0.2" />
              <stop offset="50%" style="stop-color:#4a9eff;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#4a9eff;stop-opacity:0.2" />
            </linearGradient>
          </defs>
          <g v-for="edge in edges" :key="edge.id">
            <!-- 连接线（无箭头）-->
            <path
              :d="getEdgePath(edge)"
              class="edge-path"
              :class="{ active: isActiveEdge(edge) }"
              fill="none"
              stroke-linecap="round"
            />
            
            <!-- 光球动画（仅活跃边）-->
            <circle
              v-if="isActiveEdge(edge)"
              :cx="getLightBallX(edge)"
              :cy="getLightBallY(edge)"
              r="8"
              class="light-ball"
              fill="url(#lightGradient)"
            >
              <animateMotion
                :dur="getAnimationDuration(edge)"
                repeatCount="indefinite"
                :path="getEdgePath(edge)"
                rotate="auto"
              />
            </circle>
            
            <!-- 标签 -->
            <text v-if="edge.label" :x="getEdgeLabelX(edge)" :y="getEdgeLabelY(edge)" class="edge-label">
              {{ edge.label }}
            </text>
          </g>
        </svg>

        <!-- Nodes -->
        <div
          v-for="node in nodes"
          :key="node.id"
          class="flow-node"
          :class="[`type-${node.type}`, `status-${node.status}`, { active: isActiveNode(node) }]"
          :style="getNodeStyle(node)"
          @mouseenter="hoveredNode = node.id"
          @mouseleave="hoveredNode = null"
        >
          <div class="node-icon">{{ getNodeIcon(node) }}</div>
          <div class="node-name">{{ node.name }}</div>
          <div class="node-status">{{ getNodeStatusLabel(node.status) }}</div>
          
          <!-- Hover tooltip -->
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
      </div>
    </div>

    <div class="flow-legend">
      <div class="legend-item">
        <span class="legend-icon">🤖</span>
        <span>Agent</span>
      </div>
      <div class="legend-item">
        <span class="legend-icon">📋</span>
        <span>Task</span>
      </div>
      <div class="legend-item">
        <span class="legend-icon">🔧</span>
        <span>Tool</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot active"></span>
        <span>活跃</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot completed"></span>
        <span>完成</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot error"></span>
        <span>错误</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRealtime } from '../../composables'
import type { CollaborationNode, CollaborationEdge, CollaborationFlow } from '../../types'

const { connectionState, subscribe, connect } = useRealtime()

const nodes = ref<CollaborationNode[]>([])
const edges = ref<CollaborationEdge[]>([])
const activePath = ref<string[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const hoveredNode = ref<string | null>(null)
const flowContainerRef = ref<HTMLElement | null>(null)

// Canvas dimensions - 加大画布尺寸，改善显示比例
const canvasWidth = 1200
const canvasHeight = 600
const nodeWidth = 140
const nodeHeight = 90
const horizontalSpacing = 250
const verticalSpacing = 150

const canvasStyle = computed(() => ({
  width: `${canvasWidth}px`,
  height: `${canvasHeight}px`
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

// 自动布局节点位置 - 老 K 在左，子 Agents 在中，任务在右（星型拓扑）
function autoLayoutNodes(nodeList: CollaborationNode[]): void {
  const mainNode = nodeList.find(n => n.id === 'main')
  const subAgents = nodeList.filter(n => n.type === 'agent' && n.id !== 'main')
  const taskNodes = nodeList.filter(n => n.type === 'task')
  const toolNodes = nodeList.filter(n => n.type === 'tool')

  // Layer 0: 老 K 单独在左侧居中
  if (mainNode) {
    mainNode.position = { x: 80, y: (canvasHeight - nodeHeight) / 2 }
  }

  // Layer 1: 子 Agents 在中间
  const midX = 80 + horizontalSpacing
  const subAgentTotalH = Math.max(0, (subAgents.length - 1) * verticalSpacing)
  const subStartY = Math.max(80, (canvasHeight - subAgentTotalH) / 2)
  subAgents.forEach((node, i) => {
    node.position = { x: midX, y: subStartY + i * verticalSpacing }
  })

  // Layer 2: 任务节点在右侧
  const taskX = 80 + horizontalSpacing * 2
  const taskTotalH = Math.max(0, (taskNodes.length - 1) * verticalSpacing)
  const taskStartY = Math.max(80, (canvasHeight - taskTotalH) / 2)
  taskNodes.forEach((node, i) => {
    node.position = { x: taskX, y: taskStartY + i * verticalSpacing }
  })

  // Layer 3: 工具节点
  const toolX = 80 + horizontalSpacing * 3
  toolNodes.forEach((node, i) => {
    node.position = { x: toolX, y: 80 + i * verticalSpacing }
  })
}

function getNodeStyle(node: CollaborationNode): Record<string, string> {
  const pos = node.position || { x: 0, y: 0 }
  return {
    left: `${pos.x}px`,
    top: `${pos.y}px`,
    width: `${nodeWidth}px`,
    height: `${nodeHeight}px`
  }
}

function getNodeIcon(node: CollaborationNode): string {
  switch (node.type) {
    case 'agent': return '🤖'
    case 'task': return '📋'
    case 'tool': return '🔧'
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
  
  const x1 = source.position.x + nodeWidth
  const y1 = source.position.y + nodeHeight / 2
  const x2 = target.position.x
  const y2 = target.position.y + nodeHeight / 2
  
  // 贝塞尔曲线
  const cx = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`
}

function getEdgeLabelX(edge: CollaborationEdge): number {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  
  if (!source?.position || !target?.position) return 0
  return (source.position.x + nodeWidth + target.position.x) / 2
}

function getEdgeLabelY(edge: CollaborationEdge): number {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  
  if (!source?.position || !target?.position) return 0
  return (source.position.y + target.position.y) / 2 + nodeHeight / 2 - 10
}

// 光球动画相关函数
function getLightBallX(edge: CollaborationEdge): number {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  
  if (!source?.position || !target?.position) return 0
  return source.position.x + nodeWidth
}

function getLightBallY(edge: CollaborationEdge): number {
  const source = nodes.value.find(n => n.id === edge.source)
  const target = nodes.value.find(n => n.id === edge.target)
  
  if (!source?.position || !target?.position) return 0
  return source.position.y + nodeHeight / 2
}

function getAnimationDuration(edge: CollaborationEdge): string {
  // 根据边的类型设置动画时长
  return edge.type === 'delegates' ? '3s' : '2s'
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
  autoLayoutNodes(nodes.value)
}

let unsubscribe: (() => void) | null = null

onMounted(() => {
  fetchData()
  unsubscribe = subscribe('collaboration', handleCollaborationUpdate)
})

onUnmounted(() => {
  if (unsubscribe) unsubscribe()
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

.flow-container {
  overflow: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
  min-height: 300px;
  position: relative;
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
}

.edges-layer {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
}

.edge-path {
  fill: none;
  stroke: #94a3b8;
  stroke-width: 2;
  transition: stroke 0.3s ease;
}

.edge-path.active {
  stroke: #4a9eff;
  stroke-width: 2.5;
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
  transition: all 0.3s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.flow-node:hover {
  border-color: #4a9eff;
  box-shadow: 0 4px 12px rgba(74, 158, 255, 0.2);
}

.flow-node.active {
  border-color: #4a9eff;
  box-shadow: 0 0 0 3px rgba(74, 158, 255, 0.2);
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

.flow-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #e5e7eb;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: #6b7280;
}

.legend-icon {
  font-size: 1rem;
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #94a3b8;
}

.legend-dot.active {
  background: #4a9eff;
}

.legend-dot.completed {
  background: #22c55e;
}

.legend-dot.error {
  background: #ef4444;
}

/* 响应式 */
@media (max-width: 640px) {
  .flow-legend {
    gap: 0.5rem;
  }
  
  .legend-item {
    font-size: 0.7rem;
  }
}
</style>
