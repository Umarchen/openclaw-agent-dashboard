// 任务状态类型定义

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface Task {
  id: string
  name: string
  status: TaskStatus
  progress: number // 0-100
  startTime?: number
  endTime?: number
  agentId?: string
  agentName?: string
  subtasks?: Task[]
  error?: string
  metadata?: Record<string, unknown>
}

export interface TaskStatusSummary {
  tasks: Task[]
  total: number
  completed: number
  failed: number
  running: number
  pending: number
  cancelled: number
}

export interface TaskFilters {
  status?: TaskStatus[]
  search?: string
  agentId?: string
}
