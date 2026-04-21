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
  toolResultError?: string  // 工具失败时的错误信息

  // 工具链路关联
  pairedToolCallId?: string   // toolResult 专用：对应的 toolCall ID
  pairedToolResultId?: string // toolCall 专用：对应的 toolResult ID
  executionTime?: number      // 工具执行耗时（ms），toolResult 专用

  // 错误
  errorMessage?: string
  errorType?: string

  // 统计
  tokens?: TokenUsage

  // 展示控制
  collapsed?: boolean

  // 消息来源（用于区分真实用户和其他 Agent）
  senderId?: string      // 发送者 Agent ID（如 'main'）
  senderName?: string    // 发送者显示名（如 '老K'）
}

/** 时序统计 */
export interface TimelineStats {
  totalDuration: number
  totalInputTokens: number
  totalOutputTokens: number
  toolCallCount: number
  stepCount: number
}

/** LLM 轮次 */
export interface LLMRound {
  id: string           // round_1, round_2, ...
  index: number        // 轮次序号（从1开始）
  trigger: 'user_input' | 'tool_result' | 'subagent_result' | 'start'
  triggerBy?: string   // 触发来源描述
  stepIds: string[]    // 该轮次包含的步骤 ID 列表
  duration: number     // 该轮次耗时（ms）
  tokens?: TokenUsage  // 该轮次的 token 使用
}

/** 时序会话响应 */
export interface TimelineResponse {
  sessionId: string | null
  agentId: string
  agentName?: string
  model?: string
  startedAt: number | null
  /** runs.json 中本次子 Agent run 的 startedAt（与子会话派发时刻对齐） */
  runStartedAt?: number | null
  status: 'running' | 'completed' | 'error' | 'empty' | 'no_sessions'
  steps: TimelineStep[]
  stats: TimelineStats
  message?: string
  /** 主 Agent 无会话文件等场景，后端标记，避免与子 Agent 空态混淆 */
  isMainAgent?: boolean
  // LLM 轮次分组
  rounds?: LLMRound[]
  roundMode?: boolean
  dataSource?: string
}

/** 步骤图标和颜色配置 */
export const stepConfig: Record<StepType, { icon: string; bgColor: string; borderColor: string; label: string }> = {
  user: { icon: '👤', bgColor: '#f0f9ff', borderColor: '#3b82f6', label: '用户' },
  thinking: { icon: '🧠', bgColor: '#fef3c7', borderColor: '#f59e0b', label: '思考' },
  text: { icon: '🤖', bgColor: '#f0fdf4', borderColor: '#22c55e', label: '回复' },
  toolCall: { icon: '🔧', bgColor: '#f5f3ff', borderColor: '#8b5cf6', label: '调用' },
  toolResult: { icon: '✅', bgColor: '#ecfdf5', borderColor: '#10b981', label: '结果' },
  error: { icon: '⚠️', bgColor: '#fef2f2', borderColor: '#dc2626', label: '错误' }
}

/**
 * 获取用户步骤的显示标签
 * 如果有 senderName，显示发送者名称；否则显示"用户"
 */
export function getUserStepLabel(step: TimelineStep): string {
  if (step.senderName) {
    return step.senderName
  }
  if (step.senderId) {
    return step.senderId
  }
  return '用户'
}
