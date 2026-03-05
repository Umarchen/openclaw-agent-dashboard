// 协作流程类型定义

export type NodeStatus = 'idle' | 'working' | 'active' | 'completed' | 'error'
export type NodeType = 'agent' | 'task' | 'tool' | 'model'

export interface AgentError {
  hasError: boolean
  type: string  // rate-limit, token-limit, timeout, quota, unknown
  message: string
  timestamp: number
}

export interface StuckWarning {
  isStuck: boolean
  idleSeconds: number
  lastUpdate: number
  // 卡顿原因分析
  reason?: 'waiting_for_child' | 'self_busy' | 'unknown'
  reasonDetail?: string
  waitingFor?: {
    agentId: string
    task?: string
  }
}

export interface CollaborationNode {
  id: string
  type: NodeType
  name: string
  status: NodeStatus
  timestamp?: number
  position?: { x: number; y: number }
  metadata?: Record<string, unknown>
  // 当前任务（有效描述）
  currentTask?: string
  // 错误信息
  error?: AgentError
  // 卡顿警告
  stuckWarning?: StuckWarning
}

export type EdgeType = 'delegates' | 'calls' | 'returns' | 'error' | 'model'

export interface CollaborationEdge {
  id: string
  source: string
  target: string
  type: EdgeType
  label?: string
  animated?: boolean
}

export interface ModelCall {
  id: string
  agentId: string
  model: string
  sessionId: string
  trigger: string
  tokens: number
  timestamp: number
  time: string
}

export interface CollaborationFlow {
  nodes: CollaborationNode[]
  edges: CollaborationEdge[]
  activePath: string[]
  lastUpdate: number
  mainAgentId?: string
  agentModels?: Record<string, { primary?: string; fallbacks?: string[] }>
  models?: string[]
  recentCalls?: ModelCall[]
  // 拓扑信息（用于嵌套组网布局）
  hierarchy?: Record<string, string[]>  // agentId -> [子 agent IDs]
  depths?: Record<string, number>  // agentId -> 层级深度
}

export interface CollaborationDynamic {
  activePath: string[]
  recentCalls: ModelCall[]
  agentStatuses: Record<string, string>
  taskNodes: CollaborationNode[]
  taskEdges: CollaborationEdge[]
  mainAgentId: string
  lastUpdate: number
}
