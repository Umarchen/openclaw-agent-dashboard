// 类型定义入口文件

export * from './collaboration'
export * from './task'
export * from './performance'

// 通用类型
export interface ConnectionState {
  status: 'disconnected' | 'connecting' | 'connected' | 'error'
  lastConnected?: number
  reconnectAttempts: number
  errorMessage?: string
}

export interface AgentStateChangeEvent {
  agentId: string
  status: 'idle' | 'working' | 'down'
  lastActiveAt?: number
  lastActiveFormatted?: string
  currentTask?: string
  error?: unknown
  modelInfo?: { primary?: string; fallbacks?: string[] }
  subStatus?: 'thinking' | 'tool_executing' | 'waiting_llm' | 'waiting_child'
  currentAction?: string
  toolName?: string
  waitingFor?: string
  agentTasks?: unknown[]
}

export interface WebSocketMessage {
  type: 'update' | 'ping' | 'pong' | 'error' | 'full_state' | 'state_update' | 'agent_state_changed'
  channel?: 'collaboration' | 'tasks' | 'performance'
  data?: unknown
  timestamp?: number
}
