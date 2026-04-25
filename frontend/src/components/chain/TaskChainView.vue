<template>
  <div class="chain-view">
    <!-- 头部 -->
    <div class="chain-header">
      <div class="header-left">
        <span class="title">🔗 任务执行链路</span>
        <span class="project-info" v-if="displayChain">
          {{ displayChain.projectId || '当前任务' }}
        </span>
      </div>
      <div class="header-right">
        <span class="status-badge" :class="`status-${displayChain?.status || 'empty'}`">
          {{ statusLabel }}
        </span>
        <button class="refresh-btn" @click="refresh" :disabled="loading">
          {{ loading ? '加载中...' : '🔄 刷新' }}
        </button>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading && !displayChain" class="loading-state">
      <div class="spinner"></div>
      <span>加载链路数据...</span>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!displayChain && chains.length === 0" class="empty-state">
      <span class="empty-icon">🔗</span>
      <span>暂无任务链路</span>
      <div class="empty-hint">当 Main Agent 派发任务给子 Agent 时，这里会显示执行链路</div>
    </div>

    <!-- 链路内容 -->
    <div v-else class="chain-content">
      <!-- 根任务信息 -->
      <div class="root-task" v-if="displayChain">
        <div class="task-label">根任务</div>
        <div class="task-text">{{ displayChain.rootTask }}</div>
        <div class="task-meta">
          <span v-if="displayChain.startedAt">开始: {{ formatTime(displayChain.startedAt) }}</span>
        </div>
      </div>

      <!-- 链路图 -->
      <div class="chain-diagram" v-if="displayChain">
        <div class="diagram-container">
          <template v-for="(node, index) in sortedNodes" :key="node.agentId">
            <!-- 连接线 -->
            <ChainEdge
              v-if="index > 0"
              :from-status="sortedNodes[index - 1]?.status"
              :to-status="node.status"
            />
            <!-- 节点 -->
            <ChainNode
              :node="node"
              :is-selected="selectedNode?.agentId === node.agentId"
              @click="selectNode(node)"
            />
          </template>
        </div>
      </div>

      <!-- 进度条 -->
      <div class="chain-progress" v-if="displayChain">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: `${displayChain.progress * 100}%` }"></div>
        </div>
        <div class="progress-text">
          {{ Math.round(displayChain.progress * 100) }}% ({{ displayChain.completedNodes }}/{{ displayChain.totalNodes }} 完成)
        </div>
      </div>

      <!-- 节点详情 -->
      <div class="node-detail" v-if="selectedNode">
        <div class="detail-header">
          <span class="detail-title">{{ selectedNode.agentName }}</span>
          <span class="detail-status" :class="`status-${selectedNode.status}`">
            {{ nodeStatusConfig[selectedNode.status]?.label || selectedNode.status }}
          </span>
        </div>

        <div class="detail-content">
          <!-- 任务信息 -->
          <div class="detail-section" v-if="selectedNode.task">
            <div class="section-label">任务</div>
            <div class="section-value">{{ selectedNode.task }}</div>
          </div>

          <!-- 时间信息 -->
          <div class="detail-row">
            <div class="detail-item">
              <span class="item-label">开始时间</span>
              <span class="item-value">{{ selectedNode.startedAt ? formatTime(selectedNode.startedAt) : '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="item-label">耗时</span>
              <span class="item-value">{{ formatDuration(selectedNode.duration) }}</span>
            </div>
          </div>

          <!-- Token 使用 -->
          <div class="detail-row" v-if="selectedNode.tokenUsage">
            <div class="detail-item">
              <span class="item-label">Token 输入</span>
              <span class="item-value">{{ formatNumber(selectedNode.tokenUsage.input) }}</span>
            </div>
            <div class="detail-item">
              <span class="item-label">Token 输出</span>
              <span class="item-value">{{ formatNumber(selectedNode.tokenUsage.output) }}</span>
            </div>
          </div>

          <!-- 工具调用 -->
          <div class="detail-section" v-if="selectedNode.toolCallCount > 0">
            <div class="section-label">工具调用</div>
            <div class="section-value">{{ selectedNode.toolCallCount }} 次</div>
          </div>

          <!-- 产出物 -->
          <div class="detail-section" v-if="selectedNode.artifacts && selectedNode.artifacts.length > 0">
            <div class="section-label">产出物</div>
            <div class="artifacts-list">
              <div v-for="artifact in selectedNode.artifacts" :key="artifact" class="artifact-item">
                📄 {{ artifact }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { TaskChain, ChainNode as ChainNodeType, TaskChainResponse, ChainNodeStatus } from './types'
import { nodeStatusConfig } from './types'
import ChainNode from './ChainNode.vue'
import ChainEdge from './ChainEdge.vue'

const props = defineProps<{
  autoRefresh?: boolean
  refreshInterval?: number
}>()

const chains = ref<TaskChain[]>([])
/** 仅「进行中」的链路；任务结束后为 null，但 chains 中仍有已完成项 */
const activeChain = ref<TaskChain | null>(null)
const selectedNode = ref<ChainNodeType | null>(null)
const loading = ref(false)

/** 优先展示进行中的；若无（已全部结束）则展示最近一条链路，避免跑完后整块空白 */
const displayChain = computed<TaskChain | null>(() => {
  if (activeChain.value) return activeChain.value
  if (chains.value.length > 0) return chains.value[0]
  return null
})

const statusLabel = computed(() => {
  const labels: Record<string, string> = {
    running: '🔄 进行中',
    completed: '✅ 已完成',
    error: '❌ 出错',
    empty: '空'
  }
  return labels[displayChain.value?.status || 'empty'] || '未知'
})

const sortedNodes = computed(() => {
  const nodes = displayChain.value?.nodes
  if (!nodes) return []

  // 按照 main -> analyst -> architect -> devops 顺序排序
  const roleOrder = ['main', 'analyst', 'architect', 'devops']
  return [...nodes].sort((a, b) => {
    const aIndex = roleOrder.findIndex(r => a.role.includes(r))
    const bIndex = roleOrder.findIndex(r => b.role.includes(r))
    return aIndex - bIndex
  })
})

async function refresh() {
  loading.value = true
  try {
    const res = await fetch('/api/chains?limit=10')
    if (res.ok) {
      const data: TaskChainResponse = await res.json()
      chains.value = data.chains || []
      activeChain.value = data.activeChain || null
    }
  } catch (e) {
    console.error('Chain load error:', e)
  } finally {
    loading.value = false
  }
}

function selectNode(node: ChainNodeType) {
  selectedNode.value = selectedNode.value?.agentId === node.agentId ? null : node
}

function formatTime(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatDuration(ms: number | undefined): string {
  if (!ms) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}

function formatNumber(n: number | undefined): string {
  if (!n) return '0'
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

let refreshTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  refresh()
  if (props.autoRefresh && props.refreshInterval) {
    refreshTimer = setInterval(refresh, props.refreshInterval * 1000)
  }
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<style scoped>
.chain-view {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
}

.chain-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title {
  font-weight: 600;
  font-size: 14px;
  color: #374151;
}

.project-info {
  font-size: 13px;
  color: #6b7280;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-badge {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
}

.status-badge.status-running { background: #fef3c7; color: #92400e; }
.status-badge.status-completed { background: #d1fae5; color: #065f46; }
.status-badge.status-error { background: #fee2e2; color: #991b1b; }
.status-badge.status-empty { background: #f3f4f6; color: #6b7280; }

.refresh-btn {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: #374151;
}

.refresh-btn:hover:not(:disabled) { background: #f3f4f6; }
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.loading-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
  color: #6b7280;
  gap: 12px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #e5e7eb;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.empty-icon { font-size: 32px; }
.empty-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
  text-align: center;
  max-width: 280px;
}

.chain-content { padding: 16px; }

.root-task {
  padding: 12px;
  background: #f9fafb;
  border-radius: 6px;
  margin-bottom: 16px;
}

.task-label {
  font-size: 11px;
  color: #9ca3af;
  margin-bottom: 4px;
}

.task-text {
  font-size: 14px;
  color: #374151;
  font-weight: 500;
}

.task-meta {
  margin-top: 8px;
  font-size: 12px;
  color: #6b7280;
}

.chain-diagram {
  margin: 20px 0;
}

.diagram-container {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  flex-wrap: wrap;
}

.chain-progress {
  margin-top: 16px;
}

.progress-bar {
  height: 8px;
  background: #e5e7eb;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #22c55e, #3b82f6);
  transition: width 0.3s ease;
}

.progress-text {
  margin-top: 8px;
  font-size: 12px;
  color: #6b7280;
  text-align: center;
}

.node-detail {
  margin-top: 16px;
  padding: 16px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.detail-status {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
}

.detail-content { display: flex; flex-direction: column; gap: 12px; }
.detail-section { }
.section-label { font-size: 11px; color: #9ca3af; margin-bottom: 4px; }
.section-value { font-size: 13px; color: #374151; }
.detail-row { display: flex; gap: 24px; }
.detail-item { display: flex; flex-direction: column; }
.item-label { font-size: 11px; color: #9ca3af; }
.item-value { font-size: 13px; color: #374151; font-weight: 500; }
.artifacts-list { display: flex; flex-direction: column; gap: 4px; }
.artifact-item { font-size: 12px; color: #6b7280; padding: 4px 8px; background: #fff; border-radius: 4px; }
</style>
