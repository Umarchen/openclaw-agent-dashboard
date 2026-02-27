// 性能数据类型定义

export interface PerformanceMetric {
  timestamp: number
  tpm: number // Tokens per minute
  rpm: number // Requests per minute
  latency: number // API response time (ms)
  errorRate: number // 0-1
  connections?: number
}

export interface PerformanceAggregates {
  avgTpm: number
  avgLatency: number
  totalTokens: number
  totalRequests: number
  maxTpm: number
  maxLatency: number
}

export interface PerformanceData {
  current: PerformanceMetric
  history: PerformanceMetric[]
  aggregates: PerformanceAggregates
}

export type TimeRange = '5m' | '15m' | '1h' | '6h'

export interface PerformanceAlert {
  id: string
  type: 'high_tpm' | 'high_latency' | 'high_error_rate'
  message: string
  value: number
  threshold: number
  timestamp: number
  acknowledged: boolean
}
