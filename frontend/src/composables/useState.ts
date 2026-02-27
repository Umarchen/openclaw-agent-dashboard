/**
 * 状态管理组合函数
 */

import { computed, type Ref } from 'vue'
import { getStateManager } from '../managers'

export function useState<T>(key: string, defaultValue: T): Ref<T> {
  const manager = getStateManager()
  return manager.useStore(key, defaultValue)
}

export function useCache<T>(key: string, fetcher: () => Promise<T>, ttl?: number) {
  const manager = getStateManager()
  const data = useState<T | null>(`cache:${key}`, null)
  const loading = useState(`cache:${key}:loading`, false)
  const error = useState<Error | null>(`cache:${key}:error`, null)

  const fetch = async () => {
    // 检查缓存
    if (manager.hasValidCache(key)) {
      data.value = manager.getCache<T>(key) ?? null
      return
    }

    loading.value = true
    error.value = null

    try {
      const result = await fetcher()
      data.value = result
      manager.setCache(key, result, ttl)
    } catch (e) {
      error.value = e as Error
    } finally {
      loading.value = false
    }
  }

  const invalidate = () => {
    manager.invalidateCache(key)
    data.value = null
  }

  return {
    data: computed(() => data.value),
    loading: computed(() => loading.value),
    error: computed(() => error.value),
    fetch,
    invalidate
  }
}
