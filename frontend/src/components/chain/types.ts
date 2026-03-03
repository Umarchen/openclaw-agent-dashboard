// Task Chain 类型定义

/** 节点状态 */
export type ChainNodeStatus = 'pending' | 'running' | 'completed' | 'error'

/** 链路状态 */
export type ChainStatus = 'running' | 'completed' | 'error'

/** 链路节点 */
export interface ChainNode {
  agentId: string
  agentName: string
  role: string

  status: ChainNodeStatus
  startedAt?: number
  endedAt?: number
  duration?: number

  task?: string
  runId?: string

  input?: string
  output?: string
  artifacts: string[]

  toolCallCount: number
  tokenUsage: { input: number; output: number }
}

/** 链路边 */
export interface ChainEdge {
  from: string
  to: string
}

/** 任务链 */
export interface TaskChain {
  chainId: string
  projectId?: string
  rootTask: string

  startedAt?: number
  status: ChainStatus

  nodes: ChainNode[]
  edges: ChainEdge[]

  progress: number
  completedNodes: number
  totalNodes: number
  totalDuration: number
}

/** 任务链响应 */
export interface TaskChainResponse {
  chains: TaskChain[]
  activeChain?: TaskChain
}

/** 节点状态配置 */
export const nodeStatusConfig: Record<ChainNodeStatus, { icon: string; bgColor: string; borderColor: string; label: string }> = {
  pending: { icon: '⏳', bgColor: '#f3f4f6', borderColor: '#9ca3af', label: '等待中' },
  running: { icon: '🔄', bgColor: '#eff6ff', borderColor: '#3b82f6', label: '进行中' },
  completed: { icon: '✅', bgColor: '#f0fdf4', borderColor: '#22c55e', label: '已完成' },
  error: { icon: '❌', bgColor: '#fef2f2', borderColor: '#ef4444', label: '失败' }
}

/** Agent 角色顺序 */
export const agentRoleOrder = ['main', 'analyst', 'architect', 'devops']
