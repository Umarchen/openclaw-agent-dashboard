/**
 * 实时数据管理器 (C3-2 改造)
 * 负责 WebSocket 连接管理和 HTTP 轮询回退
 *
 * C3-2 改造要点：
 * - handleMessage() 统一调用 StateManager.applyEvent() 处理增量事件
 * - 移除各 case 内的独立 merge 逻辑
 * - bootstrap 事件（full_state / FullStateSnapshot）走 StateManager.bootstrapReplace()
 * - 所有 entity merge 由 StateManager 统一管理
 */

import { getStateManager, type PatchEvent, type EntityType } from './StateManager'
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

  // ═══════════════════════════════════════════════════════════════════
  //  handleMessage — 统一事件路由 + StateManager.applyEvent()
  // ═══════════════════════════════════════════════════════════════════

  private handleMessage(message: WebSocketMessage): void {
    const stateManager = getStateManager()

    if (message.type === 'ping') {
      this.send({ type: 'pong', timestamp: Date.now() })
      return
    }

    // ─── Bootstrap 事件：全量替换 ────────────────────────────────

    // C1: FullStateSnapshot (new format)
    if (message.type === 'FullStateSnapshot' && message.payload) {
      this.handleBootstrap(message.payload as Record<string, unknown>)
      return
    }

    // C0 legacy: full_state (old format)
    if (message.type === 'full_state' && message.data) {
      this.handleBootstrap(message.data as Record<string, unknown>)
      return
    }

    // C1: ready — server confirmed schemaVersion match, no action needed
    if (message.type === 'ready') {
      return
    }

    // ─── 增量事件：统一走 StateManager.applyEvent() ───────────────

    // C0/C1: 单个 Agent 状态变更
    if (message.type === 'agent_state_changed' && message.data) {
      this.applyAgentPatch(message.data as Record<string, unknown>, message)
      return
    }

    // C1: AgentStateChanged (new format, payload-based)
    if (message.type === 'AgentStateChanged' && message.payload) {
      this.applyAgentStateChanged(message.payload as Record<string, unknown>, message)
      return
    }

    // C0 legacy: state_update
    if (message.type === 'state_update' && message.data) {
      const data = message.data as Record<string, unknown>
      if (data.agents) {
        const agents = data.agents as Array<Record<string, unknown>>
        for (const agent of agents) {
          this.applyAgentPatch(agent, message)
        }
      }
      return
    }

    // C2: CollaborationChanged
    if (message.type === 'CollaborationChanged' && message.payload) {
      const payload = message.payload as Record<string, unknown>
      this.applyPatchEvent({
        type: message.type,
        entityType: 'collaboration',
        patch: payload,
        version: this.extractVersion(message),
        timestamp: message.timestamp as string | undefined,
      })
      // 同时 emit 给下游（保持向后兼容）
      this.emit('collaboration_update', payload)
      return
    }

    // C2: TaskChanged
    if (message.type === 'TaskChanged' && message.payload) {
      const payload = message.payload as Record<string, unknown>
      const change = payload.change as 'added' | 'updated' | 'removed' | undefined
      const taskId = payload.task_id as string | undefined
      if (change && taskId) {
        this.applyPatchEvent({
          type: message.type,
          entityType: 'tasks',
          entityId: taskId,
          change,
          taskData: payload.task_data as Record<string, unknown> | undefined,
          version: this.extractVersion(message),
          timestamp: message.timestamp as string | undefined,
        })
      }
      this.emit('task_changed', payload)
      return
    }

    // C2: PerformanceSnapshot — 30s slow channel, full replacement
    if (message.type === 'PerformanceSnapshot' && message.payload) {
      const payload = message.payload as Record<string, unknown>
      this.applyPatchEvent({
        type: message.type,
        entityType: 'performance',
        data: payload,
        version: this.extractVersion(message),
        timestamp: message.timestamp as string | undefined,
      })
      this.emit('performance', payload)
      return
    }

    // Fallback: unknown channel
    if (message.channel && message.data) {
      this.emit(message.channel, message.data)
    }
  }

  // ─── Bootstrap 处理 ──────────────────────────────────────────────

  private handleBootstrap(data: Record<string, unknown>): void {
    const stateManager = getStateManager()

    // agents
    if (data.agents && Array.isArray(data.agents)) {
      stateManager.bootstrapReplace('agents', data.agents as unknown[])
      this.emit('agents', data.agents)
    }

    // subagents
    if (data.subagents && Array.isArray(data.subagents)) {
      stateManager.bootstrapReplace('subagents', data.subagents as unknown[])
      this.emit('subagents', data.subagents)
    }

    // tasks
    const tasksArray = Array.isArray(data.tasks) ? data.tasks : []
    stateManager.bootstrapReplace('tasks', tasksArray as unknown[])
    this.emit('tasks', { tasks: tasksArray })

    // collaboration
    if (data.collaboration) {
      stateManager.bootstrapReplace('collaboration', [data.collaboration] as unknown[])
      this.emit('collaboration', data.collaboration)
    }

    // performance
    if (data.performance) {
      stateManager.bootstrapReplace('performance', [data.performance] as unknown[])
      this.emit('performance', data.performance)
    }

    // workflows / apiStatus — 非 entity，仅 emit
    if (data.workflows) this.emit('workflows', data.workflows)
    if (data.apiStatus) this.emit('api_status', data.apiStatus)
  }

  // ─── Agent patch 构建 ──────────────────────────────────────────

  /**
   * C0: agent_state_changed → 构建 patch
   */
  private applyAgentPatch(data: Record<string, unknown>, message: WebSocketMessage): void {
    const agentId = data.agentId as string | undefined
    if (!agentId) return

    const patch: Record<string, unknown> = { id: agentId }
    if (data.status !== undefined) patch.status = data.status
    if (data.currentTask !== undefined) patch.currentTask = data.currentTask
    if (data.lastActiveAt !== undefined) patch.lastActiveAt = data.lastActiveAt
    if (data.error !== undefined) patch.error = data.error

    this.applyPatchEvent({
      type: message.type,
      entityType: 'agents',
      entityId: agentId,
      patch,
      version: this.extractVersion(message),
      timestamp: message.timestamp as string | undefined,
    })
  }

  /**
   * C1: AgentStateChanged (diffs 格式) → 构建 patch
   */
  private applyAgentStateChanged(payload: Record<string, unknown>, message: WebSocketMessage): void {
    const agentId = payload.agent_id as string | undefined
    if (!agentId) return

    const patch: Record<string, unknown> = { id: agentId }

    // snake_case → camelCase 映射
    const fieldMap: Record<string, string> = {
      status: 'status',
      current_task: 'currentTask',
      last_active_at: 'lastActiveAt',
      error: 'error',
    }

    const diffs = payload.diffs as Array<Record<string, unknown>> | undefined
    if (Array.isArray(diffs)) {
      for (const diff of diffs) {
        // Prefer new_value (standard format); fall back to changed (C1 backend format)
        const val = diff.new_value !== undefined ? diff.new_value : diff.changed
        if (diff.field && val !== undefined) {
          const frontendKey = fieldMap[diff.field as string] || diff.field as string
          patch[frontendKey] = val
        }
      }
    }

    this.applyPatchEvent({
      type: message.type,
      entityType: 'agents',
      entityId: agentId,
      patch,
      diffs: Array.isArray(diffs) ? diffs.map(d => ({
        field: d.field as string,
        old_value: d.old_value,
        new_value: d.new_value !== undefined ? d.new_value : d.changed,
      })) : undefined,
      version: this.extractVersion(message),
      timestamp: message.timestamp as string | undefined,
    })
  }

  // ─── 统一 Patch 应用 ──────────────────────────────────────────

  /**
   * 统一入口：调用 StateManager.applyEvent()
   */
  private applyPatchEvent(event: PatchEvent): void {
    const stateManager = getStateManager()
    const applied = stateManager.applyEvent(event)

    if (!applied) {
      // 事件被丢弃（version 重复），静默
      return
    }

    // 仍然 emit 给下游消费者（保持向后兼容）
    // 消费者可以逐步迁移到直接用 StateManager
    this.emitPatchNotification(event)
  }

  /**
   * 向下游 emit patch 通知（保持向后兼容）
   */
  private emitPatchNotification(event: PatchEvent): void {
    switch (event.entityType) {
      case 'agents': {
        // 兼容原有的 agents_update 事件格式
        if (event.patch) {
          this.emit('agents_update', [event.patch])
        }
        break
      }
      case 'tasks': {
        // task_changed 已在 handleMessage 中单独 emit
        break
      }
      case 'subagents': {
        if (event.patch) {
          this.emit('subagents_update', [event.patch])
        }
        break
      }
      // collaboration 和 performance 已在 handleMessage 中单独 emit
    }
  }

  /**
   * 从 WebSocketMessage 中提取 version
   */
  private extractVersion(message: WebSocketMessage): number | undefined {
    // C1 格式：version 在 payload 中
    if (message.payload && typeof message.payload === 'object') {
      const payload = message.payload as Record<string, unknown>
      if (typeof payload.version === 'number') return payload.version
    }
    // C0 格式：version 在 data 中
    if (message.data && typeof message.data === 'object') {
      const data = message.data as Record<string, unknown>
      if (typeof data.version === 'number') return data.version
    }
    return undefined
  }

  // ─── 底层通信 ──────────────────────────────────────────────────

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
