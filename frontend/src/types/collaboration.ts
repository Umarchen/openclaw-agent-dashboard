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

export type SubStatus = 'thinking' | 'tool_executing' | 'waiting_llm' | 'waiting_child'

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
  // 详细状态 (TR5)
  subStatus?: SubStatus
  currentAction?: string
  toolName?: string
  waitingFor?: string
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
  // 多任务并行数据（按 agent 分组）
  agentActiveTasks?: Record<string, ActiveTask[]>
}

export interface AgentDynamicStatus {
  status: string  // 'idle' | 'working'
  subStatus?: SubStatus
  currentAction?: string
  toolName?: string
  waitingFor?: string
}

export interface AgentDisplayStatus {
  /** 状态：idle 或 working */
  status: 'idle' | 'working'
  /** 显示文本，如 "等待响应"、"执行命令"、"处理中..." */
  display: string
  /** 持续时间（秒） */
  duration: number
  /** 是否需要警告（如等待时间过长） */
  alert: boolean
}

/** 单个活跃任务（用于多任务并行展示） */
export interface ActiveTask {
  /** 任务ID */
  id: string
  /** 任务名称（清理后） */
  name: string
  /** 状态：working | retrying | failed */
  status: 'working' | 'retrying' | 'failed'
  /** 开始时间戳 */
  timestamp?: number
  /** 主 Agent 任务时，指向被派发的子 Agent */
  childAgentId?: string
  /** FEATURE_ID（如果有） */
  featureId?: string
}

export interface CollaborationDynamic {
  activePath: string[]
  recentCalls: ModelCall[]
  agentStatuses: Record<string, string>
  agentDynamicStatuses?: Record<string, AgentDynamicStatus>
  /** 详细显示状态（TR9-1：基于时间阈值） */
  agentDisplayStatuses?: Record<string, AgentDisplayStatus>
  taskNodes: CollaborationNode[]
  taskEdges: CollaborationEdge[]
  mainAgentId: string
  lastUpdate: number
  /** 多任务并行数据（按 agent 分组） */
  agentActiveTasks?: Record<string, ActiveTask[]>
}
