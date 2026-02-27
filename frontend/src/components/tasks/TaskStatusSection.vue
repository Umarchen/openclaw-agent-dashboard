<template>
  <div class="task-status-section">
    <div class="section-header">
      <h2>任务状态</h2>
      <div class="summary-stats">
        <span class="stat running">执行中: {{ summary.running }}</span>
        <span class="stat completed">已完成: {{ summary.completed }}</span>
        <span class="stat failed">失败: {{ summary.failed }}</span>
        <span class="stat total">总计: {{ summary.total }}</span>
      </div>
    </div>

    <div class="filters-row">
      <div class="search-box">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜索任务..."
          class="search-input"
        />
      </div>
      <div class="filter-buttons">
        <button
          v-for="status in statusFilters"
          :key="status.value"
          :class="['filter-btn', { active: activeFilters.includes(status.value) }]"
          @click="toggleFilter(status.value)"
        >
          {{ status.label }} ({{ getStatusCount(status.value) }})
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <span>加载任务数据...</span>
    </div>

    <div v-else-if="error" class="error-state">
      <span class="error-icon">⚠️</span>
      <span>{{ error }}</span>
      <button @click="refreshData" class="retry-btn">重试</button>
    </div>

    <div v-else-if="filteredTasks.length === 0" class="empty-state">
      <span class="empty-icon">📭</span>
      <span>{{ searchQuery ? '无匹配任务' : '暂无任务数据' }}</span>
    </div>

    <div v-else class="task-list-container" ref="containerRef">
      <div class="task-list">
        <div
          v-for="task in filteredTasks"
          :key="task.id"
          class="task-item"
          @click="selectedTask = task"
        >
          <span class="task-status-icon" :class="task.status">
            {{ getStatusIcon(task.status) }}
          </span>
          <div class="task-main">
            <div class="task-name-short">{{ getShortTaskName(task) }}</div>
          </div>
          <span class="task-agent" v-if="task.agentName">{{ task.agentName }}</span>
          <span class="task-time" v-if="task.startTime">{{ formatDuration(task) }}</span>
          <span class="task-detail-hint">详情 ›</span>
        </div>
      </div>
    </div>

    <!-- 任务详情弹窗 -->
    <div v-if="selectedTask" class="task-detail-overlay" @click.self="selectedTask = null">
      <div class="task-detail-modal">
        <div class="task-detail-header">
          <h3>任务详情</h3>
          <button class="close-btn" @click="selectedTask = null">×</button>
        </div>
        <div class="task-detail-body">
          <div class="detail-row">
            <span class="detail-label">任务</span>
            <span class="detail-value task-content">{{ sanitizeTaskDisplay(selectedTask.task ?? selectedTask.name) }}</span>
          </div>
          <div v-if="selectedTask.taskPath" class="detail-row">
            <span class="detail-label">项目路径</span>
            <span class="detail-value">{{ sanitizeTaskDisplay(selectedTask.taskPath) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">状态</span>
            <span class="detail-value">
              <span class="task-status-icon" :class="selectedTask.status">{{ getStatusIcon(selectedTask.status) }}</span>
              {{ getStatusLabel(selectedTask.status) }}
            </span>
          </div>
          <div v-if="selectedTask.agentName" class="detail-row">
            <span class="detail-label">执行者</span>
            <span class="detail-value">{{ selectedTask.agentName }}</span>
          </div>
          <div v-if="selectedTask.startTime" class="detail-row">
            <span class="detail-label">耗时</span>
            <span class="detail-value">{{ formatDuration(selectedTask) }}</span>
          </div>
          <div v-if="selectedTask.status === 'running'" class="detail-row">
            <span class="detail-label">进度</span>
            <div class="detail-progress">
              <div class="progress-bar">
                <div class="progress-fill" :style="{ width: `${selectedTask.progress}%` }"></div>
              </div>
              <span class="progress-text">{{ selectedTask.progress }}%</span>
            </div>
          </div>
          <div v-if="selectedTask.status === 'failed'" class="detail-row">
            <span class="detail-label">失败原因</span>
            <span class="detail-value error">{{ formatErrorDisplay(selectedTask.error) }}</span>
          </div>
          <div v-if="selectedTask.status === 'completed' && selectedTask.output" class="detail-row">
            <span class="detail-label">Agent 输出</span>
            <div class="detail-value output-content">{{ sanitizeTaskDisplay(selectedTask.output) }}</div>
          </div>
          <div v-if="selectedTask.subtasks?.length" class="detail-row">
            <span class="detail-label">子任务</span>
            <div class="detail-subtasks">
              <div v-for="st in selectedTask.subtasks" :key="st.id" class="subtask-row">
                <span class="task-status-icon" :class="st.status">{{ getStatusIcon(st.status) }}</span>
                <span>{{ st.name }}</span>
                <span v-if="st.status === 'failed'" class="subtask-error-inline">{{ formatErrorDisplay(st.error) }}</span>
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
import { useRealtime, useDebounce } from '../../composables'
import type { Task, TaskStatus as TaskStatusType } from '../../types'

const { connectionState, subscribe } = useRealtime()

const tasks = ref<Task[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const searchQuery = ref('')
const activeFilters = ref<TaskStatusType[]>([])
const selectedTask = ref<Task | null>(null)
const containerRef = ref<HTMLElement | null>(null)

// 符合 PRD: 待分配/分配中/执行中/已完成/失败
const statusFilters = [
  { value: 'running', label: '执行中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'pending', label: '待分配' }
]

// 防抖搜索
const { debouncedFn: debouncedSearch } = useDebounce((query: string) => {
  // 触发重新计算
  void query
}, 300)

// 过滤后的任务
const filteredTasks = computed(() => {
  let result = tasks.value

  // 状态过滤
  if (activeFilters.value.length > 0) {
    result = result.filter(t => activeFilters.value.includes(t.status))
  }

  // 搜索过滤
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(t => 
      t.name.toLowerCase().includes(query) ||
      t.agentName?.toLowerCase().includes(query)
    )
  }

  return result
})

// 统计摘要
const summary = computed(() => ({
  total: tasks.value.length,
  running: tasks.value.filter(t => t.status === 'running').length,
  completed: tasks.value.filter(t => t.status === 'completed').length,
  failed: tasks.value.filter(t => t.status === 'failed').length,
  pending: tasks.value.filter(t => t.status === 'pending').length,
  cancelled: tasks.value.filter(t => t.status === 'cancelled').length
}))

// 符合 PRD 状态图标
function getStatusIcon(status: TaskStatusType): string {
  const icons: Record<TaskStatusType, string> = {
    pending: '⏳',
    running: '🔄',   // 执行中
    completed: '✅', // 已完成
    failed: '❌',    // 失败
    cancelled: '🚫'
  }
  return icons[status] || '📋'
}

function getStatusCount(status: string): number {
  return tasks.value.filter(t => t.status === status).length
}

function formatErrorDisplay(raw: string | undefined): string {
  if (!raw || !raw.trim()) return '未知'
  const lower = raw.trim().toLowerCase()
  const mapping: Record<string, string> = {
    'terminated': '任务被终止（可能是超时或被用户取消）',
    'timeout': '任务执行超时',
    'cancelled': '任务已取消',
    'canceled': '任务已取消',
    'killed': '任务被终止',
    'subagent-error': '子任务执行异常',
  }
  for (const [key, desc] of Object.entries(mapping)) {
    if (lower.includes(key)) return desc
  }
  return raw.trim()
}

function sanitizeTaskDisplay(text: string | undefined): string {
  if (!text || typeof text !== 'string') return ''
  return text
    .replace(/\*\*/g, '')
    .replace(/`([^`]+)`/g, '$1')
}

function formatDuration(task: Task): string {
  if (!task.startTime) return ''
  
  const start = new Date(task.startTime).getTime()
  const end = task.endTime ? new Date(task.endTime).getTime() : Date.now()
  const duration = Math.floor((end - start) / 1000)
  
  if (duration < 60) return `${duration}s`
  if (duration < 3600) return `${Math.floor(duration / 60)}m ${duration % 60}s`
  return `${Math.floor(duration / 3600)}h ${Math.floor((duration % 3600) / 60)}m`
}

function toggleFilter(status: TaskStatusType): void {
  const index = activeFilters.value.indexOf(status)
  if (index === -1) {
    activeFilters.value.push(status)
  } else {
    activeFilters.value.splice(index, 1)
  }
}

function getShortTaskName(task: Task): string {
  const full = sanitizeTaskDisplay(task.task ?? task.name)
  const firstLine = full.split('\n')[0].trim()
  if (firstLine.length <= 60) return firstLine
  return firstLine.slice(0, 60) + '…'
}

function getStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待分配',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return map[status] || status
}

async function fetchData(): Promise<void> {
  loading.value = true
  error.value = null
  
  try {
    const response = await fetch('/api/tasks')
    if (!response.ok) throw new Error('Failed to fetch tasks')
    
    const data = await response.json()
    tasks.value = (data.tasks || []).map((t: any) => mapTaskFromApi(t))
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function mapTaskStatus(status: string): TaskStatusType {
  const statusMap: Record<string, TaskStatusType> = {
    'pending': 'pending',
    'assigning': 'pending',  // 分配中归入 pending 显示
    'running': 'running',
    'in_progress': 'running',
    'active': 'running',
    'completed': 'completed',
    'success': 'completed',
    'failed': 'failed',
    'error': 'failed',
    'cancelled': 'cancelled'
  }
  return statusMap[status] || 'pending'
}

function refreshData(): void {
  fetchData()
}

function mapTaskFromApi(t: any): Task {
  const subtasks = (t.subtasks || []).map((s: any) => ({
    id: s.id || s.name,
    name: s.name || 'Unknown',
    task: s.task,
    status: mapTaskStatus(s.status),
    progress: s.progress ?? 0,
    startTime: s.startTime,
    endTime: s.endTime,
    agentId: s.agentId,
    agentName: s.agentName,
    taskPath: s.taskPath,
    error: s.error,
    output: s.output
  }))
  return {
    id: t.id,
    name: t.name || 'Unknown Task',
    task: t.task,
    status: mapTaskStatus(t.status),
    progress: t.progress ?? 0,
    startTime: t.startTime,
    endTime: t.endTime,
    agentId: t.agentId,
    agentName: t.agentName,
    taskPath: t.taskPath,
    error: t.error,
    output: t.output,
    subtasks: subtasks.length ? subtasks : undefined
  }
}

function handleTasksUpdate(data: unknown): void {
  const taskData = data as { tasks?: any[] }
  if (taskData.tasks) {
    tasks.value = taskData.tasks.map((t: any) => mapTaskFromApi(t))
  }
}

let unsubscribe: (() => void) | null = null

onMounted(() => {
  fetchData()
  unsubscribe = subscribe('tasks', handleTasksUpdate)
})

onUnmounted(() => {
  if (unsubscribe) unsubscribe()
})
</script>

<style scoped>
.task-status-section {
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

.section-header h2 {
  margin: 0;
  font-size: 1.3rem;
  color: #333;
}

.summary-stats {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.stat {
  font-size: 0.85rem;
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  background: #f1f5f9;
}

/* 符合 PRD 颜色: 执行中=绿色, 已完成=金色, 失败=红色 */
.stat.running {
  background: #dcfce7;
  color: #166534;
}

.stat.completed {
  background: #fef3c7;
  color: #92400e;
}

.stat.failed {
  background: #fee2e2;
  color: #991b1b;
}

.filters-row {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.search-box {
  flex: 1;
  min-width: 200px;
}

.search-input {
  width: 100%;
  padding: 0.5rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  font-size: 0.9rem;
  outline: none;
  transition: border-color 0.2s;
}

.search-input:focus {
  border-color: #4a9eff;
}

.filter-buttons {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.filter-btn {
  padding: 0.5rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: white;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.2s;
}

.filter-btn:hover {
  border-color: #4a9eff;
}

.filter-btn.active {
  background: #4a9eff;
  color: white;
  border-color: #4a9eff;
}

.loading-state,
.error-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
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

.retry-btn {
  padding: 0.5rem 1rem;
  background: #4a9eff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.task-list-container {
  max-height: 600px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  position: relative;
}

.task-list {
  display: flex;
  flex-direction: column;
}

.task-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 1rem;
  border-bottom: 1px solid #f1f5f9;
  background: white;
  cursor: pointer;
  transition: background 0.15s;
}

.task-item:hover {
  background: #f8fafc;
}

.task-item:last-child {
  border-bottom: none;
}

.task-status-icon {
  font-size: 1rem;
}

/* 符合 PRD 任务状态颜色 */
.task-status-icon.running {
  color: #22c55e;
}

.task-status-icon.completed {
  color: #f59e0b;
}

.task-status-icon.failed {
  color: #ef4444;
}

.task-status-icon.pending {
  color: #9ca3af;
}

.task-main {
  flex: 1;
  min-width: 0;
}

.task-name-short {
  font-size: 0.9rem;
  font-weight: 500;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-detail-hint {
  font-size: 0.75rem;
  color: #94a3b8;
  flex-shrink: 0;
}

.task-agent {
  font-size: 0.8rem;
  color: #6b7280;
  background: #f1f5f9;
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
}

.task-time {
  font-size: 0.8rem;
  color: #94a3b8;
}

/* 详情弹窗 */
.task-detail-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.task-detail-modal {
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
  max-width: 560px;
  width: 90%;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}

.task-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #e5e7eb;
}

.task-detail-header h3 {
  margin: 0;
  font-size: 1rem;
  color: #333;
}

.task-detail-header .close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #6b7280;
  line-height: 1;
  padding: 0 0.25rem;
}

.task-detail-header .close-btn:hover {
  color: #333;
}

.task-detail-body {
  padding: 1rem 1.25rem;
  overflow-y: auto;
}

.detail-row {
  margin-bottom: 1rem;
}

.detail-row:last-child {
  margin-bottom: 0;
}

.detail-label {
  display: block;
  font-size: 0.75rem;
  color: #64748b;
  margin-bottom: 0.25rem;
}

.detail-value {
  font-size: 0.9rem;
  color: #333;
  word-break: break-word;
}

.detail-value.task-content {
  white-space: pre-wrap;
  line-height: 1.5;
}

.detail-value.output-content {
  white-space: pre-wrap;
  line-height: 1.6;
  max-height: 400px;
  overflow-y: auto;
  background: #f8fafc;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  font-size: 0.85rem;
}

.detail-value.error {
  color: #b91c1c;
  background: #fef2f2;
  padding: 0.5rem;
  border-radius: 6px;
  display: block;
}

.detail-progress {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.detail-progress .progress-bar {
  flex: 1;
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  overflow: hidden;
}

.detail-progress .progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4a9eff, #6bb9ff);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.detail-progress .progress-text {
  font-size: 0.8rem;
  color: #6b7280;
  min-width: 40px;
}

.detail-subtasks {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.subtask-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  padding: 0.35rem 0.5rem;
  background: #f8fafc;
  border-radius: 6px;
}

.subtask-error-inline {
  margin-left: auto;
  font-size: 0.8rem;
  color: #b91c1c;
}


/* 响应式 */
@media (max-width: 640px) {
  .section-header {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .summary-stats {
    font-size: 0.75rem;
  }
  
  .filters-row {
    flex-direction: column;
  }
  
  .filter-buttons {
    width: 100%;
    justify-content: flex-start;
  }
  
  .task-agent {
    display: none;
  }
}
</style>
