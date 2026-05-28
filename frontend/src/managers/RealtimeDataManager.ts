/**
 * 实时数据管理器
 * 负责 WebSocket 连接管理和 HTTP 轮询回退
 */

import type { ConnectionState, WebSocketMessage } from '../types'

type EventCallback = (data: unknown) => void

export interface RealtimeDataManagerOptions {
  wsUrl?: string
  httpFallback?: boolean
  reconnectMaxAttempts?: number
  reconnectDelay?: number
  pollingInterval?: number
  /**
   * Schema version for FullStateSnapshot negotiation (C1+).
   * When set, the client sends a hello message after WS connect.
   * If the server supports the same version, it responds with FullStateSnapshot (new format).
   * If not, the server falls back to full_state (legacy format).
   * Default: 2 (matches C1 backend).
   */
  schemaVersion?: number
}

export class RealtimeDataManager {
  private ws: WebSocket | null = null
  private connectionState: ConnectionState = {
    status: 'disconnected',
    reconnectAttempts: 0
  }
  private subscribers: Map<string, Set<EventCallback>> = new Map()
  private options: Required<RealtimeDataManagerOptions>
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private pollingTimer: ReturnType<typeof setInterval> | null = null
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private stateListeners: Set<(state: ConnectionState) => void> = new Set()

  constructor(options: RealtimeDataManagerOptions = {}) {
    this.options = {
      wsUrl: options.wsUrl || `ws://${window.location.host}/ws`,
      httpFallback: options.httpFallback ?? true,
      reconnectMaxAttempts: options.reconnectMaxAttempts ?? 5,
      reconnectDelay: options.reconnectDelay ?? 3000,
      pollingInterval: options.pollingInterval ?? 10000,
      schemaVersion: options.schemaVersion ?? 2
    }
  }

  /**
   * 建立 WebSocket 连接
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return
    }

    this.updateConnectionState({ status: 'connecting', reconnectAttempts: this.connectionState.reconnectAttempts })

    try {
      this.ws = new WebSocket(this.options.wsUrl)
      
      this.ws.onopen = () => {
        this.updateConnectionState({
          status: 'connected',
          lastConnected: Date.now(),
          reconnectAttempts: 0
        })
        this.startHeartbeat()
        this.stopPolling()
        // C1: Send hello with schemaVersion for FullStateSnapshot negotiation
        if (this.options.schemaVersion) {
          this.send({
            type: 'hello',
            schemaVersion: this.options.schemaVersion
          })
        }
      }

      this.ws.onclose = () => {
        this.stopHeartbeat()
        this.handleDisconnect()
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        this.updateConnectionState({
          status: 'error',
          errorMessage: 'WebSocket connection failed'
        })
        // 连接失败时触发重连或 HTTP 轮询回退
        this.handleDisconnect()
      }

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
      this.handleDisconnect()
    }
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this.stopHeartbeat()
    this.stopReconnect()
    this.stopPolling()
    
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }

    this.updateConnectionState({ status: 'disconnected', reconnectAttempts: 0 })
  }

  /**
   * 获取连接状态
   */
  getConnectionState(): ConnectionState {
    return { ...this.connectionState }
  }

  /**
   * 订阅事件
   */
  subscribe(event: string, callback: EventCallback): () => void {
    if (!this.subscribers.has(event)) {
      this.subscribers.set(event, new Set())
    }
    this.subscribers.get(event)!.add(callback)

    // 返回取消订阅函数
    return () => {
      this.subscribers.get(event)?.delete(callback)
    }
  }

  /**
   * 监听连接状态变化
   */
  onStateChange(callback: (state: ConnectionState) => void): () => void {
    this.stateListeners.add(callback)
    return () => {
      this.stateListeners.delete(callback)
    }
  }

  /**
   * 是否已连接
   */
  isConnected(): boolean {
    return this.connectionState.status === 'connected'
  }

  /**
   * 获取初始数据
   */
  async fetchInitialData(): Promise<void> {
    try {
      const [collaboration, tasks, performance, agents] = await Promise.all([
        fetch('/api/collaboration').then(r => r.json()).catch(() => null),
        fetch('/api/tasks').then(r => r.json()).catch(() => null),
        fetch('/api/performance?range=20m').then(r => r.json()).catch(() => null),
        fetch('/api/agents').then(r => r.json()).catch(() => null)
      ])

      if (collaboration) this.emit('collaboration', collaboration)
      if (tasks) this.emit('tasks', tasks)
      if (performance) this.emit('performance', performance)
      if (agents) this.emit('agents', agents)
    } catch (error) {
      console.error('Failed to fetch initial data:', error)
    }
  }

  private handleMessage(message: WebSocketMessage): void {
    if (message.type === 'ping') {
      this.send({ type: 'pong', timestamp: Date.now() })
      return
    }

    // C1: FullStateSnapshot (new format) — data is in payload, not data
    if (message.type === 'FullStateSnapshot' && message.payload) {
      const payload = message.payload as Record<string, unknown>
      if (payload.agents) this.emit('agents', payload.agents)
      if (payload.subagents) this.emit('subagents', payload.subagents)
      if (payload.collaboration) this.emit('collaboration', payload.collaboration)
      const tasksArray = Array.isArray(payload.tasks) ? payload.tasks : []
      this.emit('tasks', { tasks: tasksArray })
      if (payload.performance) this.emit('performance', payload.performance)
      if (payload.workflows) this.emit('workflows', payload.workflows)
      if (payload.apiStatus) this.emit('api_status', payload.apiStatus)
      return
    }

    // C0 legacy: full_state (old format) — data is in message.data
    if (message.type === 'full_state' && message.data) {
      const data = message.data as Record<string, unknown>
      if (data.agents) this.emit('agents', data.agents)
      if (data.subagents) this.emit('subagents', data.subagents)
      if (data.collaboration) this.emit('collaboration', data.collaboration)
      const tasksArray = Array.isArray(data.tasks) ? data.tasks : []
      this.emit('tasks', { tasks: tasksArray })
      if (data.performance) this.emit('performance', data.performance)
      return
    }

    // C1: ready — server confirmed schemaVersion match, no action needed
    if (message.type === 'ready') {
      return
    }

    // 新增：增量状态更新（periodic broadcast legacy, C0 后端仍可能发）
    if (message.type === 'state_update' && message.data) {
      const data = message.data as Record<string, unknown>
      if (data.agents) {
        this.emit('agents_update', data.agents)  // 新增事件
      }
      return
    }

    // C0: 单个 Agent 状态变更（EventBus → WS subscriber, old format agent_state_changed）
    // 包装为 agents_update 数组，复用现有增量 merge 逻辑
    if (message.type === 'agent_state_changed' && message.data) {
      const d = message.data as Record<string, unknown>
      const agentPatch: Record<string, unknown> = { id: d.agentId }
      if (d.status !== undefined) agentPatch.status = d.status
      if (d.currentTask !== undefined) agentPatch.currentTask = d.currentTask
      if (d.lastActiveAt !== undefined) agentPatch.lastActiveAt = d.lastActiveAt
      if (d.error !== undefined) agentPatch.error = d.error
      this.emit('agents_update', [agentPatch])
      return
    }

    // C1: AgentStateChanged (new format, payload-based)
    if (message.type === 'AgentStateChanged' && message.payload) {
      const payload = message.payload as Record<string, unknown>
      if (payload.agent_id) {
        const agentPatch: Record<string, unknown> = { id: payload.agent_id }
        // diffs is an array of {field, old_value, new_value} or {field, changed}
        const diffs = payload.diffs as Array<Record<string, unknown>> | undefined
        if (Array.isArray(diffs)) {
          for (const diff of diffs) {
            // Prefer new_value (standard format); fall back to changed (C1 backend format)
            const val = diff.new_value !== undefined ? diff.new_value : diff.changed
            if (diff.field && val !== undefined) {
              // Map snake_case field names to camelCase for frontend Agent interface
              const fieldMap: Record<string, string> = {
                status: 'status',
                current_task: 'currentTask',
                last_active_at: 'lastActiveAt',
                error: 'error',
              }
              const frontendKey = fieldMap[diff.field as string] || diff.field
              agentPatch[frontendKey] = val
            }
          }
        }
        this.emit('agents_update', [agentPatch])
      }
      return
    }

    if (message.channel && message.data) {
      this.emit(message.channel, message.data)
    }
  }

  private emit(event: string, data: unknown): void {
    const callbacks = this.subscribers.get(event)
    if (callbacks) {
      callbacks.forEach(cb => {
        try {
          cb(data)
        } catch (e) {
          console.error(`Error in subscriber callback for ${event}:`, e)
        }
      })
    }
  }

  private send(message: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  private handleDisconnect(): void {
    if (this.connectionState.reconnectAttempts < this.options.reconnectMaxAttempts) {
      this.scheduleReconnect()
    } else if (this.options.httpFallback) {
      this.startPolling()
    }
  }

  private scheduleReconnect(): void {
    this.stopReconnect()
    
    const delay = this.options.reconnectDelay * Math.pow(1.5, this.connectionState.reconnectAttempts)
    
    this.reconnectTimer = setTimeout(() => {
      this.updateConnectionState({
        status: 'connecting',
        reconnectAttempts: this.connectionState.reconnectAttempts + 1
      })
      this.connect()
    }, delay)
  }

  private stopReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      this.send({ type: 'ping', timestamp: Date.now() })
    }, 30000)
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  private startPolling(): void {
    this.stopPolling()
    this.updateConnectionState({
      status: 'connected',
      errorMessage: 'Using HTTP polling fallback'
    })
    this.fetchInitialData()
    this.pollingTimer = setInterval(() => {
      this.fetchInitialData()
    }, this.options.pollingInterval)
  }

  private stopPolling(): void {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer)
      this.pollingTimer = null
    }
  }

  private updateConnectionState(updates: Partial<ConnectionState>): void {
    this.connectionState = { ...this.connectionState, ...updates }
    this.stateListeners.forEach(listener => {
      try {
        listener(this.connectionState)
      } catch (e) {
        console.error('Error in state listener:', e)
      }
    })
  }
}

// 单例实例
let instance: RealtimeDataManager | null = null

export function getRealtimeManager(options?: RealtimeDataManagerOptions): RealtimeDataManager {
  if (!instance) {
    instance = new RealtimeDataManager(options)
  }
  return instance
}
