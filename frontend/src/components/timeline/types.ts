// Timeline 类型定义

/** 步骤类型 */
export type StepType =
  | 'user'        // 用户消息
  | 'thinking'    // Agent 思考
  | 'text'        // Agent 文本响应
  | 'toolCall'    // 工具调用
  | 'toolResult'  // 工具结果
  | 'error'       // 错误

/** 步骤状态 */
export type StepStatus = 'pending' | 'running' | 'success' | 'error'

/** Token 使用 */
export interface TokenUsage {
  input: number
  output: number
  cumulative?: number
}

/** 时序步骤 */
export interface TimelineStep {
  id: string
  type: StepType
  status: StepStatus
  timestamp: number
  duration?: number

  // 内容
  content?: string
  thinking?: string

  // 工具调用
  toolName?: string
  toolCallId?: string
  toolArguments?: Record<string, unknown>
  toolResult?: string
  toolResultStatus?: 'ok' | 'error'

  // 错误
  errorMessage?: string
  errorType?: string

  // 统计
  tokens?: TokenUsage

  // 展示控制
  collapsed?: boolean
}

/** 时序统计 */
export interface TimelineStats {
  totalDuration: number
  totalInputTokens: number
  totalOutputTokens: number
  toolCallCount: number
  stepCount: number
}

/** 时序会话响应 */
export interface TimelineResponse {
  sessionId: string | null
  agentId: string
  agentName?: string
  model?: string
  startedAt: number | null
  status: 'running' | 'completed' | 'error' | 'empty'
  steps: TimelineStep[]
  stats: TimelineStats
}

/** 步骤图标和颜色配置 */
export const stepConfig: Record<StepType, { icon: string; bgColor: string; borderColor: string; label: string }> = {
  user: { icon: '👤', bgColor: '#f0f9ff', borderColor: '#3b82f6', label: '用户' },
  thinking: { icon: '🧠', bgColor: '#fef3c7', borderColor: '#f59e0b', label: '思考' },
  text: { icon: '🤖', bgColor: '#f0fdf4', borderColor: '#22c55e', label: '响应' },
  toolCall: { icon: '🔧', bgColor: '#f5f3ff', borderColor: '#8b5cf6', label: '调用' },
  toolResult: { icon: '✅', bgColor: '#ecfdf5', borderColor: '#10b981', label: '结果' },
  error: { icon: '⚠️', bgColor: '#fef2f2', borderColor: '#dc2626', label: '错误' }
}
