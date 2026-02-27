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
      <div class="task-list" :style="{ height: `${totalHeight}px` }">
        <div
          v-for="item in visibleItems"
          :key="filteredTasks[item.index].id"
          class="task-item"
          :style="item.style"
        >
          <div class="task-header" @click="toggleExpand(filteredTasks[item.index].id)">
            <span class="expand-icon" :class="{ expanded: expandedTasks.has(filteredTasks[item.index].id) }">
              {{ filteredTasks[item.index].subtasks?.length ? '▶' : '' }}
            </span>
            <span class="task-status-icon" :class="filteredTasks[item.index].status">
              {{ getStatusIcon(filteredTasks[item.index].status) }}
            </span>
            <span class="task-name">{{ filteredTasks[item.index].name }}</span>
            <span class="task-agent" v-if="filteredTasks[item.index].agentName">
              {{ filteredTasks[item.index].agentName }}
            </span>
            <span class="task-time" v-if="filteredTasks[item.index].startTime">
              {{ formatDuration(filteredTasks[item.index]) }}
            </span>
          </div>
          
          <div class="task-progress" v-if="filteredTasks[item.index].status === 'running'">
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{ width: `${filteredTasks[item.index].progress}%` }"
              ></div>
            </div>
            <span class="progress-text">{{ filteredTasks[item.index].progress }}%</span>
          </div>

          <div
            v-if="expandedTasks.has(filteredTasks[item.index].id) && filteredTasks[item.index].subtasks?.length"
            class="subtasks"
          >
            <div
              v-for="subtask in filteredTasks[item.index].subtasks"
              :key="subtask.id"
              class="subtask-item"
            >
              <span class="task-status-icon" :class="subtask.status">
                {{ getStatusIcon(subtask.status) }}
              </span>
              <span class="task-name">{{ subtask.name }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRealtime, useDebounce, useVirtualScroll } from '../../composables'
import type { Task, TaskStatus as TaskStatusType } from '../../types'

const { connectionState, subscribe } = useRealtime()

const tasks = ref<Task[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const searchQuery = ref('')
const activeFilters = ref<TaskStatusType[]>([])
const expandedTasks = ref<Set<string>>(new Set())
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

// 虚拟滚动
const totalCount = computed(() => filteredTasks.value.length)
const { visibleItems, totalHeight } = useVirtualScroll(containerRef, totalCount, {
  itemHeight: 60,
  bufferSize: 5
})

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

function toggleExpand(taskId: string): void {
  if (expandedTasks.value.has(taskId)) {
    expandedTasks.value.delete(taskId)
  } else {
    expandedTasks.value.add(taskId)
  }
}

async function fetchData(): Promise<void> {
  loading.value = true
  error.value = null
  
  try {
    const response = await fetch('/api/tasks')
    if (!response.ok) throw new Error('Failed to fetch tasks')
    
    const data = await response.json()
    tasks.value = (data.tasks || []).map((t: any) => ({
      id: t.id,
      name: t.name || 'Unknown Task',
      status: mapTaskStatus(t.status),
      progress: t.progress ?? 0,
      startTime: t.startTime,
      endTime: t.endTime,
      agentId: t.agentId,
      agentName: t.agentName,
      error: t.error
    }))
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

function handleTasksUpdate(data: unknown): void {
  const taskData = data as { tasks?: any[] }
  if (taskData.tasks) {
    tasks.value = taskData.tasks.map((t: any) => ({
      id: t.id,
      name: t.name || 'Unknown Task',
      status: mapTaskStatus(t.status),
      progress: t.progress ?? 0,
      startTime: t.startTime,
      endTime: t.endTime,
      agentId: t.agentId,
      agentName: t.agentName,
      error: t.error
    }))
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
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  position: relative;
}

.task-list {
  position: relative;
}

.task-item {
  position: absolute;
  left: 0;
  right: 0;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #f1f5f9;
  background: white;
}

.task-item:last-child {
  border-bottom: none;
}

.task-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
}

.expand-icon {
  width: 16px;
  color: #94a3b8;
  transition: transform 0.2s;
}

.expand-icon.expanded {
  transform: rotate(90deg);
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

.task-name {
  flex: 1;
  font-size: 0.9rem;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

.task-progress {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.5rem;
  padding-left: 2.5rem;
}

.progress-bar {
  flex: 1;
  height: 6px;
  background: #e5e7eb;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #4a9eff, #6bb9ff);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 0.75rem;
  color: #6b7280;
  min-width: 40px;
}

.subtasks {
  margin-top: 0.5rem;
  padding-left: 2.5rem;
  border-left: 2px solid #e5e7eb;
  margin-left: 0.75rem;
}

.subtask-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0;
  font-size: 0.85rem;
}

.subtask-item .task-name {
  color: #6b7280;
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
