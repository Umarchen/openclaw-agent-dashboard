<template>
  <div class="agent-card" :class="[`status-${agent.status}`, { 'is-main': isMain }]" @click="$emit('click')">
    <!-- 警告指示器（独立于卡片颜色） -->
    <div v-if="error || stuckWarning" class="warning-indicator" :class="{ 'has-error': error }" @click.stop="showWarningDetail">
      <span class="indicator-icon">{{ error ? '⚠️' : '⏳' }}</span>
      <span class="indicator-count" v-if="stuckWarning">{{ stuckWarning.idleSeconds }}s</span>
    </div>

    <div class="card-header">
      <div class="avatar">{{ emoji }}</div>
      <div class="header-info">
        <div class="name">{{ agent.name }}</div>
        <div class="status-pill" :class="`status-${agent.status}`">
          <span class="status-dot" :class="`status-${agent.status}`"></span>
          <span class="status-text">{{ statusText }}</span>
        </div>
      </div>
      <div v-if="isMain" class="main-badge">PM</div>
    </div>

    <div class="card-body">
      <!-- 模型信息 -->
      <div v-if="modelInfo && modelInfo.primary" class="model-row">
        <span class="model-label">模型</span>
        <span class="model-value">{{ shortModelId(modelInfo.primary) }}</span>
        <span v-if="modelInfo.fallbacks?.length" class="model-fallbacks" :title="'备用: ' + modelInfo.fallbacks.map(shortModelId).join(', ')">
          <span v-for="(fb, idx) in modelInfo.fallbacks.slice(0, 2)" :key="fb" class="fallback-tag">
            {{ shortModelId(fb) }}
          </span>
          <span v-if="modelInfo.fallbacks.length > 2" class="fallback-more">+{{ modelInfo.fallbacks.length - 2 }}</span>
        </span>
      </div>

      <!-- 当前任务（单任务模式） -->
      <div v-if="displayTaskName && !showTaskList" class="current-task">
        <div class="task-header">
          <span class="task-icon">▶</span>
          <span class="task-label">当前任务</span>
        </div>
        <div class="task-name" :title="displayTaskName">{{ displayTaskName }}</div>
        <div v-if="displayTaskChildAgent" class="task-child-info">
          <span class="child-arrow">→</span>
          <span class="child-name">{{ displayTaskChildAgent }}</span>
        </div>
      </div>

      <!-- 多任务并行展示 -->
      <div v-if="showTaskList" class="multi-tasks">
        <div class="tasks-header" @click.stop="tasksExpanded = !tasksExpanded">
          <span class="tasks-icon">📋</span>
          <span class="tasks-label">并行任务</span>
          <span class="tasks-count">{{ taskCount }}</span>
          <span class="tasks-toggle">{{ tasksExpanded ? '▲' : '▼' }}</span>
        </div>
        <div class="tasks-list" :class="{ expanded: tasksExpanded }">
          <div v-for="task in visibleTasks" :key="task.id" class="task-item" :class="`task-status-${task.status}`">
            <span class="task-status-dot"></span>
            <span class="task-name" :title="task.name">{{ task.name }}</span>
            <span v-if="task.childAgentId" class="task-child-agent">→ {{ task.childAgentId }}</span>
          </div>
          <div v-if="hiddenTaskCount > 0" class="tasks-more">
            +{{ hiddenTaskCount }} 更多任务
          </div>
        </div>
      </div>

      <!-- 详细状态（工作中时显示） -->
      <div v-if="agent.status === 'working' && currentAction" class="status-detail" :class="`sub-status-${subStatus}`">
        <span class="action-icon">{{ subStatusIcon }}</span>
        <span class="action-text">{{ currentAction }}</span>
      </div>

      <!-- 空闲状态 -->
      <div v-else-if="agent.status === 'idle'" class="idle-hint">
        空闲中，等待任务...
      </div>
    </div>

    <!-- 警告详情弹窗 -->
    <Teleport to="body">
      <div v-if="showDetailModal" class="warning-modal-overlay" @click.self="showDetailModal = false">
        <div class="warning-modal">
          <div class="modal-header">
            <span class="modal-icon">{{ error ? '⚠️' : '⏳' }}</span>
            <span class="modal-title">{{ error ? '异常详情' : '卡顿分析' }}</span>
            <button class="modal-close" @click="showDetailModal = false">×</button>
          </div>
          <div class="modal-body">
            <!-- 错误详情 -->
            <template v-if="error">
              <div class="detail-row">
                <span class="detail-label">类型</span>
                <span class="detail-value error-type-tag">{{ errorTypeLabel }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">信息</span>
                <span class="detail-value">{{ error.message }}</span>
              </div>
            </template>
            <!-- 卡顿详情 -->
            <template v-else-if="stuckWarning">
              <div class="detail-row">
                <span class="detail-label">等待时间</span>
                <span class="detail-value highlight">{{ stuckWarning.idleSeconds }} 秒</span>
              </div>
              <div class="detail-row" v-if="stuckWarning.reason">
                <span class="detail-label">原因</span>
                <span class="detail-value">{{ stuckReasonLabel }}</span>
              </div>
              <div class="detail-row" v-if="stuckWarning.reasonDetail">
                <span class="detail-label">详情</span>
                <span class="detail-value">{{ stuckWarning.reasonDetail }}</span>
              </div>
              <div class="detail-row" v-if="stuckWarning.waitingFor">
                <span class="detail-label">等待对象</span>
                <span class="detail-value agent-link" @click="navigateToAgent(stuckWarning.waitingFor.agentId)">
                  {{ stuckWarning.waitingFor.agentId }}
                  <span v-if="stuckWarning.waitingFor.task" class="waiting-task">({{ stuckWarning.waitingFor.task }})</span>
                </span>
              </div>
              <div class="stuck-suggestion" v-if="stuckSuggestion">
                <span class="suggestion-icon">💡</span>
                <span>{{ stuckSuggestion }}</span>
              </div>
            </template>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

interface Agent {
  name: string
  status: 'idle' | 'working' | 'down'
  lastActiveFormatted?: string
}

interface AgentError {
  hasError: boolean
  type: string
  message: string
  timestamp: number
}

interface StuckWarning {
  isStuck: boolean
  idleSeconds: number
  lastUpdate: number
  reason?: 'self_busy' | 'waiting_for_child' | 'unknown'
  reasonDetail?: string
  waitingFor?: {
    agentId: string
    task?: string
  }
}

/** 活跃任务（多任务并行展示） */
interface ActiveTask {
  id: string
  name: string
  status: 'working' | 'retrying' | 'failed'
  timestamp?: number
  childAgentId?: string
  featureId?: string
}

const props = defineProps<{
  agent: Agent
  modelInfo?: { primary?: string; fallbacks?: string[] }
  isMain?: boolean
  currentTask?: string
  error?: AgentError
  stuckWarning?: StuckWarning
  hierarchyDepth?: number
  agentColor?: string
  // TR5: 详细状态
  subStatus?: 'thinking' | 'tool_executing' | 'waiting_llm' | 'waiting_child'
  currentAction?: string
  toolName?: string
  waitingFor?: string
  // 多任务并行：活跃任务列表
  agentTasks?: ActiveTask[]
}>()

const emit = defineEmits<{
  click: []
  'navigate-agent': [agentId: string]
}>()

const showDetailModal = ref(false)
const tasksExpanded = ref(false)

const EMOJI_POOL = ['🤖', '👤', '📊', '🏗️', '💻', '🧪', '🔧', '📋', '🎯', '⚙️']

const emoji = computed(() => {
  const name = (props.agent.name || '').toLowerCase()
  if (name.includes('pm') || name.includes('project') || name.includes('主')) return '👨‍💼'
  if (name.includes('analyst') || name.includes('分析')) return '📊'
  if (name.includes('architect') || name.includes('架构')) return '🏗️'
  if (name.includes('dev') || name.includes('开发')) return '💻'
  if (name.includes('qa') || name.includes('test') || name.includes('测试')) return '🧪'
  if (name.includes('ops') || name.includes('运维')) return '🔧'
  if (name.includes('frontend') || name.includes('前端')) return '🎨'
  if (name.includes('backend') || name.includes('后端')) return '⚙️'
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash << 5) - hash + name.charCodeAt(i)
  return EMOJI_POOL[Math.abs(hash) % EMOJI_POOL.length]
})

const statusText = computed(() => {
  const map = { idle: '空闲', working: '工作中', down: '异常' }
  return map[props.agent.status] || '未知'
})

const taskCount = computed(() => props.agentTasks?.length || 0)

const showTaskList = computed(() => taskCount.value >= 1)

const visibleTasks = computed(() => {
  if (!props.agentTasks) return []
  // 最多显示3个任务，其余折叠
  return props.agentTasks.slice(0, 3)
})

const hiddenTaskCount = computed(() => {
  if (!props.agentTasks) return 0
  return Math.max(0, props.agentTasks.length - 3)
})

// 单任务时显示的任务名（优先使用 agentTasks，否则用 currentTask）
const displayTaskName = computed(() => {
  if (props.agentTasks && props.agentTasks.length === 1) {
    return props.agentTasks[0].name
  }
  return props.currentTask
})

// 单任务时的子 Agent（仅 agentTasks 有此信息）
const displayTaskChildAgent = computed(() => {
  if (props.agentTasks && props.agentTasks.length === 1) {
    return props.agentTasks[0].childAgentId
  }
  return undefined
})

const subStatusIcon = computed(() => {
  const icons: Record<string, string> = {
    'thinking': '🧠',
    'tool_executing': '⚙️',
    'waiting_llm': '📡',
    'waiting_child': '⏳',
  }
  return icons[props.subStatus || ''] || '🔄'
})

const errorTypeLabel = computed(() => {
  const labels: Record<string, string> = {
    'rate-limit': '请求过快',
    'token-limit': 'Token 超限',
    'timeout': '请求超时',
    'quota': '余额不足',
    'unknown': '发生错误'
  }
  return labels[props.error?.type || 'unknown'] || '发生错误'
})

const stuckReasonLabel = computed(() => {
  const labels: Record<string, string> = {
    'waiting_for_child': '等待子代理响应',
    'self_busy': '自身处理中',
    'unknown': '原因未明'
  }
  return labels[props.stuckWarning?.reason || 'unknown'] || '原因未明'
})

const stuckSuggestion = computed(() => {
  if (!props.stuckWarning) return null
  const reason = props.stuckWarning.reason
  const seconds = props.stuckWarning.idleSeconds

  if (reason === 'waiting_for_child') {
    if (seconds > 180) {
      return '子代理响应时间过长，建议检查子代理状态或考虑终止任务'
    }
    return '子代理正在执行任务，请耐心等待'
  }
  if (reason === 'self_busy') {
    if (seconds > 120) {
      return '任务处理时间过长，可能遇到复杂问题或外部资源阻塞'
    }
    return '正在处理复杂任务，请稍候'
  }
  return null
})

function shortModelId(id: string): string {
  const parts = id.split('/')
  return parts[parts.length - 1] || id
}

function showWarningDetail() {
  showDetailModal.value = true
}

function navigateToAgent(agentId: string) {
  emit('navigate-agent', agentId)
  showDetailModal.value = false
}
</script>

<style scoped>
.agent-card {
  display: flex;
  flex-direction: column;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  overflow: hidden;
  height: 100%;
}

.agent-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
}

.agent-card.is-main {
  border: 2px solid #4a9eff;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
}

.agent-card.is-main:hover {
  box-shadow: 0 6px 20px rgba(74, 158, 255, 0.2);
}

.agent-card.has-error {
  border: 2px solid #ef4444;
  background: linear-gradient(180deg, #ffffff 0%, #fef2f2 100%);
}

.agent-card.is-stuck {
  border: 2px solid #f59e0b;
  background: linear-gradient(180deg, #ffffff 0%, #fffbeb 100%);
}

/* 主 agent 卡片内容更大 */
.agent-card.is-main .card-header {
  padding: 0.85rem 1rem;
}

.agent-card.is-main .avatar {
  font-size: 2.2rem;
  width: 48px;
  height: 48px;
}

.agent-card.is-main .name {
  font-size: 1rem;
}

.agent-card.is-main .card-body {
  padding: 0.85rem 1rem;
}

.agent-card.is-main .current-task {
  padding: 0.6rem 0.85rem;
}

.agent-card.is-main .current-task .task-name {
  font-size: 0.85rem;
  white-space: normal;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

/* 头部 */
.card-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-bottom: 1px solid #e5e7eb;
}

.avatar {
  font-size: 2rem;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: white;
  border-radius: 10px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
}

.header-info {
  flex: 1;
  min-width: 0;
}

.name {
  font-size: 0.95rem;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 0.25rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 0.7rem;
  font-weight: 500;
}

.status-pill.status-idle { background: #dcfce7; color: #166534; }
.status-pill.status-working { background: #dbeafe; color: #1d4ed8; }
.status-pill.status-down { background: #fee2e2; color: #991b1b; }

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-dot.status-idle { background: #22c55e; }
.status-dot.status-working { background: #3b82f6; }
.status-dot.status-down { background: #ef4444; }

.main-badge {
  font-size: 0.65rem;
  font-weight: 700;
  color: #4a9eff;
  background: rgba(74, 158, 255, 0.1);
  padding: 3px 8px;
  border-radius: 4px;
  letter-spacing: 0.5px;
}

/* 内容区 */
.card-body {
  flex: 1;
  padding: 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  overflow: hidden;
}

/* 模型行 */
.model-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
  font-size: 0.75rem;
}

.model-label {
  color: #94a3b8;
  min-width: 36px;
}

.model-value {
  font-family: ui-monospace, 'Cascadia Code', monospace;
  font-weight: 500;
  color: #475569;
}

.model-fallbacks {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: 0.25rem;
}

.fallback-tag {
  font-size: 0.6rem;
  color: #64748b;
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, monospace;
}

.fallback-more {
  font-size: 0.55rem;
  color: #94a3b8;
}

/* 错误警告 */
.error-warning {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border: 1px solid #fca5a5;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
}

/* 卡顿警告 */
.stuck-warning {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border: 1px solid #fcd34d;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
}

.warning-header {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.2rem;
}

.warning-icon {
  font-size: 0.75rem;
}

.warning-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: #991b1b;
}

.stuck-warning .warning-label {
  color: #92400e;
}

.warning-message {
  font-size: 0.7rem;
  color: #7f1d1d;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stuck-warning .warning-message {
  color: #78350f;
}

/* 当前任务 */
.current-task {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #93c5fd;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
}

.task-header {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-bottom: 0.25rem;
}

.task-icon {
  font-size: 0.65rem;
  color: #3b82f6;
}

.task-label {
  font-size: 0.65rem;
  color: #3b82f6;
  font-weight: 500;
}

.current-task .task-name {
  font-size: 0.8rem;
  color: #1e40af;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 任务子 Agent 信息 */
.task-child-info {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin-top: 0.35rem;
  padding-top: 0.35rem;
  border-top: 1px dashed #bfdbfe;
}

.child-arrow {
  font-size: 0.7rem;
  color: #64748b;
}

.child-name {
  font-size: 0.7rem;
  color: #64748b;
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 3px;
}

/* 空闲提示 */
.idle-hint {
  font-size: 0.75rem;
  color: #94a3b8;
  text-align: center;
  padding: 0.5rem;
  font-style: italic;
}

/* 详细状态 (TR5) */
.status-detail {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.6rem;
  border-radius: 6px;
  font-size: 0.75rem;
  animation: pulse-subtle 2s ease-in-out infinite;
}

.status-detail.sub-status-thinking {
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border: 1px solid #fcd34d;
  color: #92400e;
}

.status-detail.sub-status-tool_executing {
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
  border: 1px solid #93c5fd;
  color: #1e40af;
}

.status-detail.sub-status-waiting_llm {
  background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%);
  border: 1px solid #a5b4fc;
  color: #3730a3;
}

.status-detail.sub-status-waiting_child {
  background: linear-gradient(135deg, #fce7f3 0%, #fbcfe8 100%);
  border: 1px solid #f9a8d4;
  color: #9d174d;
}

.action-icon {
  font-size: 0.85rem;
}

.action-text {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

@keyframes pulse-subtle {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* 多任务并行展示 */
.multi-tasks {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #93c5fd;
  border-radius: 8px;
  overflow: hidden;
}

.tasks-header {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.5rem 0.75rem;
  cursor: pointer;
  user-select: none;
}

.tasks-header:hover {
  background: rgba(59, 130, 246, 0.1);
}

.tasks-icon {
  font-size: 0.75rem;
}

.tasks-label {
  font-size: 0.7rem;
  color: #3b82f6;
  font-weight: 500;
}

.tasks-count {
  font-size: 0.65rem;
  background: #3b82f6;
  color: white;
  padding: 1px 6px;
  border-radius: 10px;
  font-weight: 600;
  margin-left: 0.25rem;
}

.tasks-toggle {
  font-size: 0.6rem;
  color: #64748b;
  margin-left: auto;
}

.tasks-list {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;
}

.tasks-list.expanded {
  max-height: 200px;
  overflow-y: auto;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.75rem;
  border-top: 1px solid #e0e7ff;
  font-size: 0.75rem;
}

.task-item:hover {
  background: rgba(59, 130, 246, 0.05);
}

.task-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.task-item.task-status-working .task-status-dot {
  background: #3b82f6;
  animation: pulse-dot 1.5s ease-in-out infinite;
}

.task-item.task-status-retrying .task-status-dot {
  background: #f59e0b;
}

.task-item.task-status-failed .task-status-dot {
  background: #ef4444;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(0.8); }
}

.task-item .task-name {
  flex: 1;
  color: #1e40af;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-child-agent {
  font-size: 0.65rem;
  color: #64748b;
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 3px;
  flex-shrink: 0;
}

.tasks-more {
  padding: 0.4rem 0.75rem;
  font-size: 0.7rem;
  color: #64748b;
  text-align: center;
  border-top: 1px solid #e0e7ff;
  background: rgba(59, 130, 246, 0.03);
}
</style>
