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

export interface WebSocketMessage {
  type:
    | 'update'
    | 'ping'
    | 'pong'
    | 'error'
    | 'full_state'
    | 'state_update'
    | 'agent_update'
    | 'subagent_update'
    | 'api_status_update'
  channel?: 'agents' | 'subagents' | 'collaboration' | 'tasks' | 'performance'
  data?: unknown
  timestamp?: number
}
