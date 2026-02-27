// 任务状态类型定义

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface Task {
  id: string
  name: string
  task?: string // 完整任务内容（用于显示全量）
  status: TaskStatus
  progress: number // 0-100
  startTime?: number
  endTime?: number
  agentId?: string
  agentName?: string
  taskPath?: string
  subtasks?: Task[]
  error?: string
  output?: string // 任务成功时 Agent 的输出内容
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
