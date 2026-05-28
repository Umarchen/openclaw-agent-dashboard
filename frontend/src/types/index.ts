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
  type: 'update' | 'ping' | 'pong' | 'error' | 'full_state' | 'state_update' | 'agent_state_changed'
    | 'AgentStateChanged' | 'FullStateSnapshot' | 'hello' | 'ready'
  channel?: 'collaboration' | 'tasks' | 'performance'
  data?: unknown
  payload?: unknown
  schemaVersion?: number
  timestamp?: number | string
}
