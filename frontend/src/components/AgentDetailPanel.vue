<template>
  <div class="panel-overlay" @click="$emit('close')">
    <div class="panel" @click.stop>
      <div class="header">
        <h2>{{ agent.name }}</h2>
        <button class="close-btn" @click="$emit('close')">×</button>
      </div>

      <div class="content">
        <div class="section">
          <h3>状态</h3>
          <div class="status-info">
            <span class="status-dot" :class="`status-${agent.status}`"></span>
            <span class="status-text">{{ statusText }}</span>
          </div>
        </div>

        <div v-if="agent.currentTask" class="section">
          <h3>当前任务</h3>
          <p>{{ agent.currentTask }}</p>
        </div>

        <div v-if="agent.lastActiveFormatted" class="section">
          <h3>最后活跃</h3>
          <p>{{ agent.lastActiveFormatted }}</p>
        </div>

        <div v-if="agent.error" class="section">
          <h3 class="error-title">错误信息</h3>
          <div class="error-info">
            <div class="error-type">{{ agent.error.type }}</div>
            <div class="error-message">{{ agent.error.message }}</div>
          </div>
        </div>

        <!-- 卡顿诊断面板 -->
        <div v-if="stuckInfo" class="section">
          <div class="diagnostic-panel" :class="`severity-${stuckInfo.severity}`">
            <div class="diagnostic-header">
              <span class="diagnostic-icon">{{ stuckInfo.severity === 'critical' ? '🚨' : '⚠️' }}</span>
              <span class="diagnostic-title">{{ stuckInfo.label }}检测</span>
            </div>
            <div class="diagnostic-content">
              <div class="diagnostic-item">
                <span class="item-label">无响应时间:</span>
                <span class="item-value highlight">{{ stuckInfo.idleMinutes }} 分钟</span>
              </div>
              <div v-if="lastToolResultDisplay" class="diagnostic-item">
                <span class="item-label">最后操作:</span>
                <span class="item-value">{{ lastToolResultDisplay.tool }} → {{ lastToolResultDisplay.result }}</span>
              </div>
              <div v-if="timeoutCountdown" class="diagnostic-item">
                <span class="item-label">自动超时:</span>
                <span class="item-value">{{ timeoutCountdown }}</span>
              </div>
              <div class="diagnostic-hint">
                <div class="hint-title">可能原因:</div>
                <ul>
                  <li>LLM API 响应超时</li>
                  <li>网络连接问题</li>
                  <li>API 配额限制</li>
                </ul>
              </div>
              <div class="diagnostic-actions">
                <button class="action-btn primary" @click="cancelRun" v-if="subagentRun">
                  取消任务
                </button>
                <button class="action-btn" @click="refreshStatus">
                  刷新状态
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="section">
          <h3>最近活动</h3>
          <div class="activity-list">
            <div v-if="agent.status === 'working'" class="activity-item working">
              💼 正在执行任务...
            </div>
            <div v-else-if="agent.status === 'idle'" class="activity-item idle">
              😴 空闲中
            </div>
            <div v-else-if="agent.status === 'down'" class="activity-item down">
              ⚠️ 检测到错误
            </div>
          </div>
        </div>

        <!-- 视图切换 Tab -->
        <div class="section">
          <div class="view-tabs">
            <button
              class="tab-btn"
              :class="{ active: activeView === 'timeline' }"
              @click="activeView = 'timeline'"
            >
              📊 时序视图
            </button>
            <button
              class="tab-btn"
              :class="{ active: activeView === 'chain' }"
              @click="activeView = 'chain'"
            >
              🔗 链路视图
            </button>
            <button
              class="tab-btn"
              :class="{ active: activeView === 'config' }"
              @click="activeView = 'config'"
            >
              ⚙️ 配置
            </button>
            <button
              class="tab-btn"
              :class="{ active: activeView === 'errors' }"
              @click="activeView = 'errors'"
            >
              🔍 错误分析
            </button>
            <button
              class="tab-btn"
              :class="{ active: activeView === 'simple' }"
              @click="activeView = 'simple'"
            >
              📋 简单视图
            </button>
          </div>

          <!-- 时序视图 -->
          <div v-if="activeView === 'timeline'" class="timeline-container">
            <TimelineView
              :agentId="agent.id"
              :autoRefresh="false"
            />
          </div>

          <!-- 链路视图 -->
          <div v-else-if="activeView === 'chain'" class="chain-container">
            <TaskChainView :autoRefresh="true" :refreshInterval="10" />
          </div>

          <!-- 配置视图 -->
          <div v-else-if="activeView === 'config'" class="config-container">
            <AgentConfigPanel :agentId="agent.id" />
          </div>

          <!-- 错误分析视图 -->
          <div v-else-if="activeView === 'errors'" class="errors-container">
            <ErrorAnalysisView :agentId="agent.id" />
          </div>

          <!-- 简单视图 (原有) -->
          <div v-else-if="activeView === 'simple'" class="session-detail">
            <div v-if="loadingTurns" class="loading">加载中...</div>
            <div v-else-if="turns.length === 0" class="empty">暂无会话记录</div>
            <div v-else class="turns-list">
              <div
                v-for="(turn, idx) in turns"
                :key="idx"
                class="turn-item"
                :class="`turn-${turn.role}`"
              >
                <div class="turn-header">
                  <span class="turn-role">{{ roleLabel(turn.role) }}</span>
                  <span v-if="turn.toolName" class="turn-tool">{{ turn.toolName }}</span>
                  <span v-if="turn.usage" class="turn-usage">
                    in {{ turn.usage.input }} / out {{ turn.usage.output }}
                    <span v-if="turn.usage.cacheRead">(cache {{ turn.usage.cacheRead }})</span>
                  </span>
                  <span v-if="turn.stopReason === 'error'" class="turn-error">[错误]</span>
                </div>
                <div class="turn-content">
                  <template v-for="(c, i) in turn.content" :key="i">
                    <div v-if="c.type === 'text' && c.text" class="content-text">{{ truncate(c.text, 200) }}</div>
                    <div v-else-if="c.type === 'thinking' && c.text" class="content-thinking">思考: {{ truncate(c.text, 100) }}</div>
                    <div v-else-if="c.type === 'toolResult'" class="content-tool-result">
                      {{ c.status || c.error ? `[${c.status || 'error'}]` : '' }} {{ truncate(String(c.content || c.error || ''), 150) }}
                    </div>
                  </template>
                  <div v-if="turn.toolCalls?.length" class="content-tool-calls">
                    <span v-for="tc in turn.toolCalls" :key="tc.id">{{ tc.name }}({{ tc.arguments ? '...' : '' }})</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { TimelineView } from './timeline'
import { TaskChainView } from './chain'
import AgentConfigPanel from './AgentConfigPanel.vue'
import ErrorAnalysisView from './ErrorAnalysisView.vue'

interface Agent {
  id: string
  name: string
  status: 'idle' | 'working' | 'down'
  currentTask?: string
  lastActiveFormatted?: string
  lastActiveAt?: number  // 后端返回的字段名
  error?: {
    type: string
    message: string
    timestamp: number
  }
}

interface SubagentRun {
  runId: string
  status: string
  startedAt?: number
  archiveAtMs?: number
  lastToolResult?: string
}

const props = defineProps<{
  agent: Agent
}>()

defineEmits<{
  close: []
}>()

const activeView = ref<'timeline' | 'chain' | 'config' | 'errors' | 'simple'>('timeline')
const subagentRun = ref<SubagentRun | null>(null)
const currentTime = ref(Date.now())
let timeUpdateInterval: ReturnType<typeof setInterval> | null = null

// 卡顿检测阈值
const STUCK_WARNING_MS = 5 * 60 * 1000  // 5 分钟警告
const STUCK_CRITICAL_MS = 15 * 60 * 1000 // 15 分钟严重

const statusText = computed(() => {
  const statusMap = {
    'idle': '空闲',
    'working': '工作中',
    'down': '异常'
  }
  return statusMap[props.agent.status] || '未知'
})

// 卡顿检测
const stuckInfo = computed(() => {
  if (props.agent.status !== 'working') return null

  const lastActive = props.agent.lastActiveAt || 0
  const idleTime = currentTime.value - lastActive

  if (idleTime > STUCK_CRITICAL_MS) {
    return {
      isStuck: true,
      idleMinutes: Math.floor(idleTime / 60000),
      severity: 'critical' as const,
      label: '严重卡顿'
    }
  } else if (idleTime > STUCK_WARNING_MS) {
    return {
      isStuck: true,
      idleMinutes: Math.floor(idleTime / 60000),
      severity: 'warning' as const,
      label: '可能卡顿'
    }
  }
  return null
})

// 超时倒计时
const timeoutCountdown = computed(() => {
  if (!subagentRun.value?.archiveAtMs) return null
  const remaining = subagentRun.value.archiveAtMs - currentTime.value
  if (remaining <= 0) return '即将超时'
  const minutes = Math.floor(remaining / 60000)
  const seconds = Math.floor((remaining % 60000) / 1000)
  return `${minutes}分${seconds}秒`
})

// 最后工具结果
const lastToolResultDisplay = computed(() => {
  if (!turns.value.length) return null
  const lastTurn = turns.value[turns.value.length - 1]
  if (lastTurn.role === 'toolResult') {
    const content = lastTurn.content[0]
    if (content) {
      const text = content.text || content.content || ''
      return {
        tool: lastTurn.toolName || '未知工具',
        status: content.status || 'completed',
        result: text.slice(0, 100) || '(无输出)'
      }
    }
  }
  return null
})

const turns = ref<Array<{
  turnIndex: number
  role: string
  content: Array<{ type: string; text?: string; content?: string; status?: string; error?: string }>
  usage?: { input: number; output: number; cacheRead?: number }
  toolCalls?: Array<{ name: string; id?: string; arguments?: unknown }>
  toolName?: string
  stopReason?: string
}>>([])
const loadingTurns = ref(false)

function roleLabel(role: string) {
  const map: Record<string, string> = { user: '用户', assistant: '助手', toolResult: '工具结果' }
  return map[role] || role
}

function truncate(s: string, max: number) {
  if (!s || s.length <= max) return s
  return s.slice(0, max) + '...'
}

async function loadTurns() {
  if (!props.agent?.id) return
  loadingTurns.value = true
  try {
    const res = await fetch(`/api/agents/${props.agent.id}/output?limit=30`)
    if (res.ok) {
      const data = await res.json()
      turns.value = data.turns || []
    } else {
      turns.value = []
    }
  } catch {
    turns.value = []
  } finally {
    loadingTurns.value = false
  }
}

// 加载子 agent 运行状态
async function loadSubagentRun() {
  if (props.agent.status !== 'working') {
    subagentRun.value = null
    return
  }
  try {
    const res = await fetch('/api/chains?limit=10')
    if (res.ok) {
      const data = await res.json()
      // 查找当前 agent 的运行
      const activeChain = data.activeChain
      if (activeChain?.nodes) {
        const node = activeChain.nodes.find((n: { agentId: string }) => n.agentId === props.agent.id)
        if (node && node.status === 'running') {
          subagentRun.value = {
            runId: activeChain.chainId,
            status: 'running',
            startedAt: node.startedAt,
            archiveAtMs: activeChain.archiveAtMs
          }
        }
      }
    }
  } catch {
    // ignore
  }
}

// 取消运行
async function cancelRun() {
  if (!subagentRun.value?.runId) return
  if (!confirm('确定要取消这个任务吗？')) return
  try {
    // 这里需要 OpenClaw 提供取消 API
    alert('取消功能需要 OpenClaw 支持，请使用命令行: openclaw subagents cancel ' + subagentRun.value.runId)
  } catch (e) {
    console.error('Cancel failed:', e)
  }
}

// 刷新状态
function refreshStatus() {
  loadTurns()
  loadSubagentRun()
}

watch(() => props.agent?.id, () => {
  loadTurns()
  loadSubagentRun()
}, { immediate: true })

// 监听 agent 状态变化
watch(() => props.agent.status, loadSubagentRun)

// 更新当前时间
onMounted(() => {
  timeUpdateInterval = setInterval(() => {
    currentTime.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  if (timeUpdateInterval) {
    clearInterval(timeUpdateInterval)
    timeUpdateInterval = null
  }
})
</script>

<style scoped>
.panel-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.panel {
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  overflow: hidden;
  display: flex;
  flex-direction: column;
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
  padding: 1.5rem;
  overflow-y: auto;
}

.section {
  margin-bottom: 1.5rem;
}

.section:last-child {
  margin-bottom: 0;
}

.section h3 {
  margin: 0 0 0.75rem 0;
  font-size: 1rem;
  color: #666;
}

.status-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.status-dot.status-idle {
  background: #4ade80;
}

.status-dot.status-working {
  background: #fbbf24;
}

.status-dot.status-down {
  background: #ef4444;
}

.status-text {
  font-size: 1.1rem;
  color: #333;
  font-weight: 500;
}

.error-title {
  color: #dc2626;
}

.error-info {
  padding: 1rem;
  background: #fef2f2;
  border-radius: 6px;
  border-left: 4px solid #dc2626;
}

.error-type {
  font-weight: 600;
  color: #dc2626;
  margin-bottom: 0.5rem;
}

.error-message {
  font-size: 0.9rem;
  color: #666;
}

.activity-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.activity-item {
  padding: 0.75rem;
  border-radius: 6px;
  font-size: 0.9rem;
}

.activity-item.working {
  background: #fef3c7;
  color: #92400e;
}

.activity-item.idle {
  background: #d1fae5;
  color: #065f46;
}

.activity-item.down {
  background: #fee2e2;
  color: #991b1b;
}

/* 视图切换 Tab */
.view-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-btn {
  padding: 8px 16px;
  font-size: 13px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  color: #6b7280;
  transition: all 0.2s;
}

.tab-btn:hover {
  background: #f9fafb;
}

.tab-btn.active {
  background: #3b82f6;
  color: #fff;
  border-color: #3b82f6;
}

.timeline-container,
.chain-container,
.config-container,
.errors-container {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.session-detail {
  margin-top: 0;
}

.session-detail .loading,
.session-detail .empty {
  color: #666;
  font-size: 0.9rem;
  padding: 20px;
  text-align: center;
}

.turns-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-height: 300px;
  overflow-y: auto;
}

.turn-item {
  padding: 0.75rem;
  border-radius: 6px;
  font-size: 0.85rem;
  border-left: 4px solid #e5e7eb;
}

.turn-item.turn-user {
  border-left-color: #4a9eff;
  background: #f0f9ff;
}

.turn-item.turn-assistant {
  border-left-color: #22c55e;
  background: #f0fdf4;
}

.turn-item.turn-toolResult {
  border-left-color: #f59e0b;
  background: #fffbeb;
}

.turn-header {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
  font-weight: 600;
  color: #374151;
}

.turn-tool {
  font-size: 0.85em;
  color: #6b7280;
}

.turn-usage {
  font-size: 0.8em;
  color: #9ca3af;
}

.turn-error {
  color: #dc2626;
}

.turn-content {
  color: #4b5563;
}

.content-text,
.content-thinking,
.content-tool-result,
.content-tool-calls {
  margin-top: 0.25rem;
  word-break: break-word;
}

.content-thinking {
  font-style: italic;
  color: #6b7280;
}

/* 诊断面板样式 */
.diagnostic-panel {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid;
}

.diagnostic-panel.severity-warning {
  border-color: #fbbf24;
  background: #fffbeb;
}

.diagnostic-panel.severity-critical {
  border-color: #ef4444;
  background: #fef2f2;
}

.diagnostic-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  font-weight: 600;
}

.severity-warning .diagnostic-header {
  background: #fef3c7;
  color: #92400e;
}

.severity-critical .diagnostic-header {
  background: #fee2e2;
  color: #991b1b;
}

.diagnostic-icon {
  font-size: 18px;
}

.diagnostic-title {
  font-size: 14px;
}

.diagnostic-content {
  padding: 12px 16px;
}

.diagnostic-item {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

.diagnostic-item .item-label {
  color: #6b7280;
  min-width: 80px;
}

.diagnostic-item .item-value {
  color: #374151;
}

.diagnostic-item .item-value.highlight {
  font-weight: 600;
  color: #dc2626;
}

.diagnostic-hint {
  margin-top: 12px;
  padding: 10px;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 6px;
  font-size: 12px;
}

.hint-title {
  font-weight: 600;
  color: #374151;
  margin-bottom: 6px;
}

.diagnostic-hint ul {
  margin: 0;
  padding-left: 18px;
  color: #6b7280;
}

.diagnostic-hint li {
  margin: 4px 0;
}

.diagnostic-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 14px;
  font-size: 13px;
  border-radius: 6px;
  border: 1px solid #d1d5db;
  background: #fff;
  cursor: pointer;
  color: #374151;
  transition: all 0.2s;
}

.action-btn:hover {
  background: #f3f4f6;
}

.action-btn.primary {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
}

.action-btn.primary:hover {
  background: #dc2626;
}
</style>
