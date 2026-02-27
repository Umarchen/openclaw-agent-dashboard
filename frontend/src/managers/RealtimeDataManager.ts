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
      wsUrl: options.wsUrl || `ws://${window.location.host}/ws/dashboard`,
      httpFallback: options.httpFallback ?? true,
      reconnectMaxAttempts: options.reconnectMaxAttempts ?? 5,
      reconnectDelay: options.reconnectDelay ?? 3000,
      pollingInterval: options.pollingInterval ?? 10000
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
      const [collaboration, tasks, performance] = await Promise.all([
        fetch('/api/collaboration').then(r => r.json()).catch(() => null),
        fetch('/api/tasks').then(r => r.json()).catch(() => null),
        fetch('/api/performance').then(r => r.json()).catch(() => null)
      ])

      if (collaboration) {
        this.emit('collaboration', collaboration)
      }
      if (tasks) {
        this.emit('tasks', tasks)
      }
      if (performance) {
        this.emit('performance', performance)
      }
    } catch (error) {
      console.error('Failed to fetch initial data:', error)
    }
  }

  private handleMessage(message: WebSocketMessage): void {
    if (message.type === 'ping') {
      this.send({ type: 'pong', timestamp: Date.now() })
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
