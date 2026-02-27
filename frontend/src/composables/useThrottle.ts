/**
 * 节流组合函数
 */

import { ref, onUnmounted } from 'vue'

export function useThrottle<T extends (...args: unknown[]) => unknown>(
  fn: T,
  interval: number = 100
): { throttledFn: T; cancel: () => void } {
  const lastExec = ref(0)
  const timer = ref<ReturnType<typeof setTimeout> | null>(null)

  const throttledFn = ((...args: unknown[]) => {
    const now = Date.now()
    const timeSinceLastExec = now - lastExec.value

    if (timeSinceLastExec >= interval) {
      lastExec.value = now
      fn(...args)
    } else {
      // 确保最后一次调用会被执行
      if (timer.value) {
        clearTimeout(timer.value)
      }
      timer.value = setTimeout(() => {
        lastExec.value = Date.now()
        fn(...args)
        timer.value = null
      }, interval - timeSinceLastExec)
    }
  }) as T

  const cancel = () => {
    if (timer.value) {
      clearTimeout(timer.value)
      timer.value = null
    }
  }

  onUnmounted(() => {
    cancel()
  })

  return { throttledFn, cancel }
}
