// 协作流程类型定义

export type NodeStatus = 'idle' | 'working' | 'active' | 'completed' | 'error'
export type NodeType = 'agent' | 'task' | 'tool'

export interface CollaborationNode {
  id: string
  type: NodeType
  name: string
  status: NodeStatus
  timestamp?: number
  position?: { x: number; y: number }
  metadata?: Record<string, unknown>
}

export type EdgeType = 'delegates' | 'calls' | 'returns' | 'error'

export interface CollaborationEdge {
  id: string
  source: string
  target: string
  type: EdgeType
  label?: string
  animated?: boolean
}

export interface CollaborationFlow {
  nodes: CollaborationNode[]
  edges: CollaborationEdge[]
  activePath: string[]
  lastUpdate: number
}
