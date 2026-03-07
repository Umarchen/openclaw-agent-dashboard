// 性能数据类型定义

export interface PerformanceCurrent {
  tpm: number
  rpm: number
  windowTotal: {
    tokens: number
    requests: number
  }
}

export interface PerformanceHistory {
  tpm: number[]
  rpm: number[]
  timestamps: number[]
}

export interface PerformanceStatistics {
  avgTpm: number
  peakTpm: number
  peakTime: string
}

export interface PerformanceData {
  current: PerformanceCurrent
  history: PerformanceHistory
  statistics: PerformanceStatistics
}

export type TimeRange = '20m' | '1h' | '24h'

export interface PerformanceAlert {
  id: string
  type: 'high_tpm'
  message: string
  value: number
  threshold: number
  timestamp: number
  acknowledged: boolean
}

// 调用详情类型
export interface CallDetail {
  agentId: string
  sessionId: string
  model: string
  tokens: number
  trigger: string
  inputTokens: number
  outputTokens: number
  time: string
}

export interface CallDetailsResponse {
  timeWindow: string
  calls: CallDetail[]
  totalCalls: number
  totalTokens: number
  summary: {
    avgTokens: number
  }
}

// Token 分析类型
export interface TokenSummary {
  input: number
  output: number
  cacheRead: number
  cacheWrite: number
  total: number
  cacheHitRate: number
}

export interface TokenCost {
  input: number
  output: number
  cacheRead: number
  cacheWrite: number
  total: number
  saved: number
  savedPercent: number
}

export interface AgentTokenData {
  agent: string
  input: number
  output: number
  cacheRead: number
  cacheWrite: number
  total: number
  percent: number
}

export interface TokenTrend {
  timestamps: number[]
  input: number[]
  output: number[]
}

export interface TokenAnalysisData {
  summary: TokenSummary
  cost: TokenCost
  byAgent: AgentTokenData[]
  trend: TokenTrend | null
}
