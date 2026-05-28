/**
 * 状态管理器 — 统一 Patch 模型 (C3-1)
 *
 * 职责:
 * 1. 集中状态管理和数据缓存（保留原有功能）
 * 2. 统一所有 entity 的 merge 逻辑（新增）
 *    - agents:    按 agent_id 字段级 patch
 *    - subagents: 按 run_id merge
 *    - tasks:     add → 追加, update → 按 task_id 替换, remove → 按 task_id 删除
 *    - collaboration: 字段级 merge
 *    - performance:   整包替换
 * 3. version 追踪：维护 entityType_lastVersion Map，丢弃 version ≤ 本地 version 的事件
 * 4. applyEvent() 统一入口：检查 version → patchMerge
 *
 * bootstrap 事件（full_state / FullStateSnapshot）不走 patch，仍然全量替换。
 */

import { ref, type Ref } from 'vue'

// ─── 原有缓存 & 通用状态 ────────────────────────────────────────────

interface CacheEntry<T> {
  value: T
  expiresAt: number
}

type StateKey = string

// ─── Entity 类型 ────────────────────────────────────────────────────

/** 支持的 entity 类型 */
export type EntityType = 'agents' | 'subagents' | 'tasks' | 'collaboration' | 'performance'

/** 单个 patch 变更 */
export interface FieldDiff {
  field: string
  old_value: unknown
  new_value: unknown
}

/** 统一 Patch 事件（由 RealtimeDataManager 产出，传给 applyEvent） */
export interface PatchEvent {
  type: string           // 事件类型，如 'AgentStateChanged', 'TaskChanged', etc.
  entityType: EntityType  // 目标 entity 类型
  entityId?: string      // 主键（agents/subagents/tasks 需要）
  patch?: Record<string, unknown>           // 字段级 patch（agents/subagents/collaboration）
  change?: 'added' | 'updated' | 'removed'  // tasks 专用
  taskData?: Record<string, unknown>        // tasks add/update 时的完整数据
  data?: Record<string, unknown>            // performance 整包替换用
  diffs?: FieldDiff[]                        // 可选，携带服务端计算的 diffs
  version?: number                           // 服务端全局版本号
  timestamp?: string | number                // UTC 时间戳
}

// ─── Merge 策略注册 ────────────────────────────────────────────────

export interface MergeStrategy {
  /** 对一个 entity 集合应用变更 */
  merge(collection: Ref<unknown[]>, patch: PatchEvent): void
}

/** agents: 按 agent_id 字段级 patch */
class AgentMergeStrategy implements MergeStrategy {
  merge(collection: Ref<unknown[]>, patch: PatchEvent): void {
    const patchData = patch.patch
    if (!patchData || !patch.entityId) return

    const arr = collection.value as Array<Record<string, unknown>>
    const idx = arr.findIndex((a) => a.id === patch.entityId)

    if (idx >= 0) {
      // 已存在：字段级 merge
      arr[idx] = { ...arr[idx], ...patchData }
    } else {
      // 新 agent：追加
      arr.push({ ...patchData, id: patch.entityId })
    }
  }
}

/** subagents: 按 run_id merge */
class SubagentMergeStrategy implements MergeStrategy {
  merge(collection: Ref<unknown[]>, patch: PatchEvent): void {
    const patchData = patch.patch
    if (!patchData || !patch.entityId) return

    const arr = collection.value as Array<Record<string, unknown>>
    const idx = arr.findIndex((s) => s.runId === patch.entityId || s.id === patch.entityId)

    if (idx >= 0) {
      arr[idx] = { ...arr[idx], ...patchData }
    } else {
      arr.push({ ...patchData, runId: patch.entityId, id: patch.entityId })
    }
  }
}

/** tasks: add → 追加, update → 按 task_id 替换, remove → 按 task_id 删除 */
class TaskMergeStrategy implements MergeStrategy {
  merge(collection: Ref<unknown[]>, patch: PatchEvent): void {
    const arr = collection.value as Array<Record<string, unknown>>
    const change = patch.change
    const taskId = patch.entityId
    const taskData = patch.taskData

    if (!change || !taskId) return

    if (change === 'added') {
      // 避免重复追加
      if (!arr.find((t) => t.id === taskId)) {
        arr.push({ ...(taskData || {}), id: taskId })
      }
    } else if (change === 'updated') {
      const idx = arr.findIndex((t) => t.id === taskId)
      if (idx >= 0 && taskData) {
        arr[idx] = { ...arr[idx], ...taskData }
      }
    } else if (change === 'removed') {
      const idx = arr.findIndex((t) => t.id === taskId)
      if (idx >= 0) {
        arr.splice(idx, 1)
      }
    }
  }
}

/** collaboration: 字段级 merge */
class CollaborationMergeStrategy implements MergeStrategy {
  merge(collection: Ref<unknown[]>, patch: PatchEvent): void {
    // collaboration 当前在 App.vue 中作为单一对象使用（不是数组）
    // patch 中的 diffs 是 FieldDiff[]，直接对对象进行字段级 merge
    const patchData = patch.patch
    if (!patchData) return

    const arr = collection.value as Array<Record<string, unknown>>
    if (arr.length === 0) return

    // collaboration 存为单元素数组
    arr[0] = { ...arr[0], ...patchData }
  }
}

/** performance: 整包替换（30s 快照语义） */
class PerformanceMergeStrategy implements MergeStrategy {
  merge(collection: Ref<unknown[]>, patch: PatchEvent): void {
    if (!patch.data) return

    // 整包替换
    const arr = collection.value as Array<Record<string, unknown>>
    if (arr.length > 0 && patch.data) {
      arr[0] = { ...patch.data }
    } else {
      arr.push({ ...patch.data })
    }
  }
}

// ─── StateManager ──────────────────────────────────────────────────

export class StateManager {
  // ---- 原有 ----
  private state: Map<StateKey, Ref<unknown>> = new Map()
  private cache: Map<StateKey, CacheEntry<unknown>> = new Map()
  private defaultTTL = 5000

  // ---- C3-1 新增 ----
  /** 各 entity 的响应式数据集合 */
  private entityCollections: Map<EntityType, Ref<unknown[]>> = new Map()
  /** 各 entity 的最后一次已应用 version */
  private entityVersions: Map<EntityType, number> = new Map()
  /** merge 策略注册表 */
  private strategies: Map<EntityType, MergeStrategy> = new Map()

  constructor() {
    // 注册所有 merge 策略
    this.strategies.set('agents', new AgentMergeStrategy())
    this.strategies.set('subagents', new SubagentMergeStrategy())
    this.strategies.set('tasks', new TaskMergeStrategy())
    this.strategies.set('collaboration', new CollaborationMergeStrategy())
    this.strategies.set('performance', new PerformanceMergeStrategy())
  }

  // ═══════════════════════════════════════════════════════════════════
  //  原有接口（保持不变）
  // ═══════════════════════════════════════════════════════════════════

  getState<T>(key: StateKey): T | undefined {
    const stateRef = this.state.get(key)
    return stateRef?.value as T | undefined
  }

  setState<T>(key: StateKey, value: T): void {
    const existing = this.state.get(key)
    if (existing) {
      existing.value = value
    } else {
      this.state.set(key, ref(value))
    }
  }

  useStore<T>(key: StateKey, defaultValue: T): Ref<T> {
    const existing = this.state.get(key)
    if (existing) {
      return existing as Ref<T>
    }

    const newRef = ref<T>(defaultValue) as Ref<T>
    this.state.set(key, newRef)
    return newRef
  }

  getCache<T>(key: StateKey): T | undefined {
    const entry = this.cache.get(key)
    if (!entry) return undefined

    if (Date.now() > entry.expiresAt) {
      this.cache.delete(key)
      return undefined
    }

    return entry.value as T
  }

  setCache<T>(key: StateKey, value: T, ttl?: number): void {
    this.cache.set(key, {
      value,
      expiresAt: Date.now() + (ttl ?? this.defaultTTL)
    })
  }

  hasValidCache(key: StateKey): boolean {
    const entry = this.cache.get(key)
    if (!entry) return false
    return Date.now() <= entry.expiresAt
  }

  invalidateCache(key: StateKey): void {
    this.cache.delete(key)
  }

  batchUpdate(updates: Record<StateKey, unknown>): void {
    Object.entries(updates).forEach(([key, value]) => {
      this.setState(key, value)
    })
  }

  clearAll(): void {
    this.state.clear()
    this.cache.clear()
    this.entityCollections.clear()
    this.entityVersions.clear()
  }

  clearCache(): void {
    this.cache.clear()
  }

  // ═══════════════════════════════════════════════════════════════════
  //  C3-1 新增：统一 Patch 模型
  // ═══════════════════════════════════════════════════════════════════

  /**
   * 注册一个 entity 类型的响应式集合
   * 用于后续 patchMerge / applyEvent 操作
   */
  registerEntity(entityType: EntityType, collection: Ref<unknown[]>): void {
    this.entityCollections.set(entityType, collection)
  }

  /**
   * 获取已注册的 entity 集合
   */
  getEntityCollection<T>(entityType: EntityType): Ref<T[]> | undefined {
    const col = this.entityCollections.get(entityType)
    return col as Ref<T[]> | undefined
  }

  /**
   * 通用 patch 合并
   *
   * @param entityType - entity 类型
   * @param key - 主键（agent_id / run_id / task_id）
   * @param patch - 变更数据
   * @param options - 额外选项（tasks 的 change 类型、performance 的整包数据等）
   */
  patchMerge(
    entityType: EntityType,
    key: string | undefined,
    patch: Record<string, unknown>,
    options?: {
      change?: 'added' | 'updated' | 'removed'
      taskData?: Record<string, unknown>
      data?: Record<string, unknown>
    }
  ): void {
    const collection = this.entityCollections.get(entityType)
    if (!collection) return

    const strategy = this.strategies.get(entityType)
    if (!strategy) return

    const event: PatchEvent = {
      type: '',
      entityType,
      entityId: key,
      patch,
      change: options?.change,
      taskData: options?.taskData,
      data: options?.data,
    }

    strategy.merge(collection, event)
  }

  /**
   * 统一事件应用入口
   *
   * 流程:
   * 1. 检查 version：如果事件携带 version 且 ≤ 本地 version，丢弃
   * 2. 更新本地 version
   * 3. 调用对应 merge 策略
   *
   * @returns true = 已应用, false = 被丢弃（version 重复或无对应 entity）
   */
  applyEvent(event: PatchEvent): boolean {
    // version 检查：丢弃 version ≤ 本地 version 的事件
    if (event.version !== undefined) {
      const localVersion = this.entityVersions.get(event.entityType) ?? 0
      if (event.version <= localVersion) {
        return false
      }
      // 更新本地 version
      this.entityVersions.set(event.entityType, event.version)
    }

    // 获取 entity 集合
    const collection = this.entityCollections.get(event.entityType)
    if (!collection) return false

    // 获取 merge 策略
    const strategy = this.strategies.get(event.entityType)
    if (!strategy) return false

    // 执行 merge
    strategy.merge(collection, event)
    return true
  }

  /**
   * Bootstrap 全量替换（full_state / FullStateSnapshot 专用）
   * 不走 patch，直接替换 entity 集合内容
   */
  bootstrapReplace(entityType: EntityType, data: unknown[]): void {
    const collection = this.entityCollections.get(entityType)
    if (!collection) return

    collection.value = [...data]

    // 重置 version（bootstrap 后 version 重置）
    if (entityType !== 'performance') {
      // performance 没有 version，不重置
    }
  }

  /**
   * 获取某个 entity 类型的本地 version
   */
  getVersion(entityType: EntityType): number {
    return this.entityVersions.get(entityType) ?? 0
  }

  /**
   * 设置某个 entity 类型的本地 version（一般由 applyEvent 自动管理）
   */
  setVersion(entityType: EntityType, version: number): void {
    const current = this.entityVersions.get(entityType) ?? 0
    if (version > current) {
      this.entityVersions.set(entityType, version)
    }
  }

  /**
   * 重置所有 entity versions（用于 bootstrap 后重置状态）
   */
  resetVersions(): void {
    this.entityVersions.clear()
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
