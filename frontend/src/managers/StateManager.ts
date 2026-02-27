/**
 * 状态管理器
 * 负责集中状态管理和数据缓存
 */

import { ref, type Ref } from 'vue'

interface CacheEntry<T> {
  value: T
  expiresAt: number
}

type StateKey = string

export class StateManager {
  private state: Map<StateKey, Ref<unknown>> = new Map()
  private cache: Map<StateKey, CacheEntry<unknown>> = new Map()
  private defaultTTL = 5000 // 默认缓存 5 秒

  /**
   * 获取状态值
   */
  getState<T>(key: StateKey): T | undefined {
    const stateRef = this.state.get(key)
    return stateRef?.value as T | undefined
  }

  /**
   * 设置状态值
   */
  setState<T>(key: StateKey, value: T): void {
    const existing = this.state.get(key)
    if (existing) {
      existing.value = value
    } else {
      this.state.set(key, ref(value))
    }
  }

  /**
   * 获取响应式状态引用
   */
  useStore<T>(key: StateKey, defaultValue: T): Ref<T> {
    const existing = this.state.get(key)
    if (existing) {
      return existing as Ref<T>
    }
    
    const newRef = ref<T>(defaultValue) as Ref<T>
    this.state.set(key, newRef)
    return newRef
  }

  /**
   * 获取缓存数据
   */
  getCache<T>(key: StateKey): T | undefined {
    const entry = this.cache.get(key)
    if (!entry) return undefined
    
    if (Date.now() > entry.expiresAt) {
      this.cache.delete(key)
      return undefined
    }
    
    return entry.value as T
  }

  /**
   * 设置缓存数据
   */
  setCache<T>(key: StateKey, value: T, ttl?: number): void {
    this.cache.set(key, {
      value,
      expiresAt: Date.now() + (ttl ?? this.defaultTTL)
    })
  }

  /**
   * 检查缓存是否有效
   */
  hasValidCache(key: StateKey): boolean {
    const entry = this.cache.get(key)
    if (!entry) return false
    return Date.now() <= entry.expiresAt
  }

  /**
   * 使缓存失效
   */
  invalidateCache(key: StateKey): void {
    this.cache.delete(key)
  }

  /**
   * 批量更新状态
   */
  batchUpdate(updates: Record<StateKey, unknown>): void {
    Object.entries(updates).forEach(([key, value]) => {
      this.setState(key, value)
    })
  }

  /**
   * 清除所有状态
   */
  clearAll(): void {
    this.state.clear()
    this.cache.clear()
  }

  /**
   * 清除所有缓存
   */
  clearCache(): void {
    this.cache.clear()
  }
}

// 单例实例
let instance: StateManager | null = null

export function getStateManager(): StateManager {
  if (!instance) {
    instance = new StateManager()
  }
  return instance
}
