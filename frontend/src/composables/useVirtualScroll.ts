/**
 * 虚拟滚动组合函数
 */

import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'

interface VirtualScrollOptions {
  itemHeight: number
  bufferSize?: number
}

export function useVirtualScroll(
  containerRef: Ref<HTMLElement | null>,
  totalCount: Ref<number>,
  options: VirtualScrollOptions
) {
  const { itemHeight, bufferSize = 5 } = options
  
  const scrollTop = ref(0)
  const containerHeight = ref(0)

  const visibleCount = computed(() => {
    return Math.ceil(containerHeight.value / itemHeight) + bufferSize * 2
  })

  const startIndex = computed(() => {
    const rawStart = Math.floor(scrollTop.value / itemHeight) - bufferSize
    return Math.max(0, rawStart)
  })

  const endIndex = computed(() => {
    return Math.min(totalCount.value, startIndex.value + visibleCount.value)
  })

  const offsetY = computed(() => {
    return startIndex.value * itemHeight
  })

  const totalHeight = computed(() => {
    return totalCount.value * itemHeight
  })

  const visibleItems = computed(() => {
    const items: { index: number; style: { transform: string } }[] = []
    for (let i = startIndex.value; i < endIndex.value; i++) {
      items.push({
        index: i,
        style: {
          transform: `translateY(${i * itemHeight}px)`
        }
      })
    }
    return items
  })

  const scrollToIndex = (index: number) => {
    if (containerRef.value) {
      containerRef.value.scrollTop = index * itemHeight
    }
  }

  const handleScroll = () => {
    if (containerRef.value) {
      scrollTop.value = containerRef.value.scrollTop
    }
  }

  const updateContainerHeight = () => {
    if (containerRef.value) {
      containerHeight.value = containerRef.value.clientHeight
    }
  }

  let resizeObserver: ResizeObserver | null = null

  onMounted(() => {
    if (containerRef.value) {
      containerRef.value.addEventListener('scroll', handleScroll, { passive: true })
      
      resizeObserver = new ResizeObserver(() => {
        updateContainerHeight()
      })
      resizeObserver.observe(containerRef.value)
      updateContainerHeight()
    }
  })

  onUnmounted(() => {
    if (containerRef.value) {
      containerRef.value.removeEventListener('scroll', handleScroll)
    }
    if (resizeObserver) {
      resizeObserver.disconnect()
    }
  })

  return {
    startIndex,
    endIndex,
    offsetY,
    totalHeight,
    visibleItems,
    scrollToIndex,
    updateContainerHeight
  }
}
