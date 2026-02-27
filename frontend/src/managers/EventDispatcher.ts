/**
 * 事件分发器
 * 负责组件间事件通信
 */

type EventHandler = (payload?: unknown) => void

interface QueuedEvent {
  event: string
  payload?: unknown
}

export class EventDispatcher {
  private listeners: Map<string, Set<EventHandler>> = new Map()
  private eventQueue: QueuedEvent[] = []
  private isFlushing = false
  private maxQueueSize = 100

  /**
   * 分发事件
   */
  emit(event: string, payload?: unknown): void {
    const handlers = this.listeners.get(event)
    if (handlers) {
      handlers.forEach(handler => {
        try {
          handler(payload)
        } catch (e) {
          console.error(`Error in event handler for ${event}:`, e)
        }
      })
    }
  }

  /**
   * 监听事件
   * 返回取消监听函数
   */
  on(event: string, handler: EventHandler): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(handler)

    return () => {
      this.listeners.get(event)?.delete(handler)
    }
  }

  /**
   * 监听一次事件
   */
  once(event: string, handler: EventHandler): void {
    const wrapper: EventHandler = (payload) => {
      this.off(event, wrapper)
      handler(payload)
    }
    this.on(event, wrapper)
  }

  /**
   * 取消监听
   */
  off(event: string, handler: EventHandler): void {
    this.listeners.get(event)?.delete(handler)
  }

  /**
   * 将事件加入队列
   */
  enqueue(event: string, payload?: unknown): void {
    if (this.eventQueue.length >= this.maxQueueSize) {
      console.warn('Event queue is full, dropping oldest event')
      this.eventQueue.shift()
    }
    this.eventQueue.push({ event, payload })
  }

  /**
   * 刷新队列中的所有事件
   */
  flush(): void {
    if (this.isFlushing) return
    
    this.isFlushing = true
    try {
      while (this.eventQueue.length > 0) {
        const { event, payload } = this.eventQueue.shift()!
        this.emit(event, payload)
      }
    } finally {
      this.isFlushing = false
    }
  }

  /**
   * 获取队列长度
   */
  getQueueLength(): number {
    return this.eventQueue.length
  }

  /**
   * 清空队列
   */
  clearQueue(): void {
    this.eventQueue = []
  }

  /**
   * 清除所有监听器
   */
  clearAll(): void {
    this.listeners.clear()
    this.eventQueue = []
  }
}

// 单例实例
let instance: EventDispatcher | null = null

export function getEventDispatcher(): EventDispatcher {
  if (!instance) {
    instance = new EventDispatcher()
  }
  return instance
}
