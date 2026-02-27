/**
 * 防抖组合函数
 */

import { ref, onUnmounted } from 'vue'

export function useDebounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  delay: number = 300
): { debouncedFn: T; cancel: () => void; flush: () => void } {
  const timer = ref<ReturnType<typeof setTimeout> | null>(null)
  let lastArgs: unknown[] | null = null

  const debouncedFn = ((...args: unknown[]) => {
    lastArgs = args
    if (timer.value) {
      clearTimeout(timer.value)
    }
    timer.value = setTimeout(() => {
      fn(...args)
      timer.value = null
      lastArgs = null
    }, delay)
  }) as T

  const cancel = () => {
    if (timer.value) {
      clearTimeout(timer.value)
      timer.value = null
      lastArgs = null
    }
  }

  const flush = () => {
    if (timer.value && lastArgs) {
      clearTimeout(timer.value)
      fn(...lastArgs)
      timer.value = null
      lastArgs = null
    }
  }

  onUnmounted(() => {
    cancel()
  })

  return { debouncedFn, cancel, flush }
}
