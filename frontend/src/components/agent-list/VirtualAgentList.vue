<template>
  <div
    ref="containerRef"
    class="virtual-agent-list"
    :class="{ 'virtual-mode': isVirtual }"
    @scroll="onScroll"
  >
    <!-- 虚拟模式：占位元素撑开滚动高度 -->
    <div v-if="isVirtual" class="virtual-spacer" :style="{ height: totalHeight + 'px' }">
      <div
        class="virtual-viewport"
        :style="{ transform: `translateY(${offsetY}px)` }"
      >
        <div
          v-for="item in visibleItems"
          :key="getItemKey(item)"
          class="virtual-row"
        >
          <slot name="item" :item="item" :index="item._virtualIndex">
            <component
              :is="itemComponent"
              v-bind="getSlotProps(item)"
            />
          </slot>
        </div>
      </div>
    </div>

    <!-- 普通模式：直接渲染所有 items -->
    <template v-else>
      <div
        v-for="(item, idx) in items"
        :key="getItemKey(item)"
        class="normal-row"
      >
        <slot name="item" :item="item" :index="idx">
          <component
            :is="itemComponent"
            v-bind="getSlotProps(item)"
          />
        </slot>
      </div>
    </template>

    <!-- 空状态 -->
    <div v-if="items.length === 0" class="empty-state">
      <slot name="empty">
        <span>暂无数据</span>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  computed,
  onMounted,
  onUnmounted,
  watch,
  type Component,
} from 'vue'

export interface VirtualListOptions {
  /** 虚拟滚动启用的阈值，items 数超过此值时启用 */
  threshold?: number
  /** 固定行高 (px) */
  itemHeight?: number
  /** 可视区域上下方额外渲染的 buffer 行数 */
  buffer?: number
}

const props = withDefaults(
  defineProps<{
    items: unknown[]
    itemComponent?: Component
    itemHeight?: number
    threshold?: number
    buffer?: number
    /** 自定义 key getter */
    itemKey?: (item: unknown) => string
  }>(),
  {
    itemHeight: 80,
    threshold: 20,
    buffer: 5,
    itemKey: undefined,
  }
)

const emit = defineEmits<{
  scroll: [scrollTop: number]
}>()

// ─── 响应式状态 ─────────────────────────────────────────────────

const containerRef = ref<HTMLElement | null>(null)
const scrollTop = ref(0)
const containerHeight = ref(600) // 初始估算

// ─── 计算属性 ─────────────────────────────────────────────────

/** 是否启用虚拟滚动 */
const isVirtual = computed(() => props.items.length > props.threshold)

/** 总高度 */
const totalHeight = computed(() => props.items.length * props.itemHeight)

/** 可视区域内能显示的行数 */
const visibleCount = computed(() =>
  Math.ceil(containerHeight.value / props.itemHeight) + props.buffer * 2
)

/** 起始索引 */
const startIndex = computed(() => {
  const raw = Math.floor(scrollTop.value / props.itemHeight) - props.buffer
  return Math.max(0, raw)
})

/** 结束索引 */
const endIndex = computed(() =>
  Math.min(props.items.length, startIndex.value + visibleCount.value)
)

/** 当前可视的 items（带虚拟索引信息） */
const visibleItems = computed(() => {
  const result: Array<Record<string, unknown>> = []
  for (let i = startIndex.value; i < endIndex.value; i++) {
    const item = props.items[i] as Record<string, unknown>
    result.push({ ...item, _virtualIndex: i })
  }
  return result
})

/** 虚拟区域 Y 偏移 */
const offsetY = computed(() => startIndex.value * props.itemHeight)

// ─── 方法 ────────────────────────────────────────────────────

function getItemKey(item: unknown): string {
  if (props.itemKey) return props.itemKey(item)
  const record = item as Record<string, unknown>
  return String(record.id ?? record.key ?? JSON.stringify(item))
}

function getSlotProps(item: Record<string, unknown>): Record<string, unknown> {
  const { _virtualIndex, ...rest } = item
  return rest
}

/** 滚动事件处理（rAF 节流） */
let rafId = 0

function onScroll(): void {
  if (!containerRef.value) return

  if (rafId) cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => {
    rafId = 0
    if (containerRef.value) {
      scrollTop.value = containerRef.value.scrollTop
      containerHeight.value = containerRef.value.clientHeight
      emit('scroll', scrollTop.value)
    }
  })
}

/** 更新容器高度 */
function updateContainerHeight(): void {
  if (containerRef.value) {
    containerHeight.value = containerRef.value.clientHeight
  }
}

// ─── 键盘导航支持 ──────────────────────────────────────────────

function onKeyDown(e: KeyboardEvent): void {
  if (!isVirtual.value) return

  const container = containerRef.value
  if (!container) return

  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    const step = props.itemHeight * 3
    const newTop = e.key === 'ArrowDown'
      ? Math.min(container.scrollTop + step, totalHeight.value - containerHeight.value)
      : Math.max(container.scrollTop - step, 0)
    container.scrollTop = newTop
  }

  if (e.key === 'Home' || e.key === 'End') {
    e.preventDefault()
    container.scrollTop = e.key === 'Home' ? 0 : totalHeight.value - containerHeight.value
  }
}

// ─── ResizeObserver ───────────────────────────────────────────

let resizeObs: ResizeObserver | null = null

// ─── 生命周期 ──────────────────────────────────────────────────

onMounted(() => {
  updateContainerHeight()
  if (containerRef.value) {
    containerRef.value.addEventListener('keydown', onKeyDown)
    resizeObs = new ResizeObserver(() => updateContainerHeight())
    resizeObs.observe(containerRef.value)
  }
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  if (containerRef.value) {
    containerRef.value.removeEventListener('keydown', onKeyDown)
  }
  if (resizeObs) {
    resizeObs.disconnect()
    resizeObs = null
  }
})

// 当 items 变化时重置 scrollTop（避免空状态滚动）
watch(
  () => props.items.length,
  (newLen, oldLen) => {
    if (newLen <= props.threshold && oldLen > props.threshold) {
      scrollTop.value = 0
      if (containerRef.value) containerRef.value.scrollTop = 0
    }
  }
)
</script>

<style scoped>
.virtual-agent-list {
  position: relative;
  overflow-y: auto;
  overflow-x: hidden;
}

.virtual-agent-list:focus {
  outline: 2px solid #4a9eff;
  outline-offset: -2px;
}

/* 虚拟模式 */
.virtual-spacer {
  position: relative;
}

.virtual-viewport {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  will-change: transform;
}

.virtual-row {
  height: v-bind(itemHeight + 'px');
  box-sizing: border-box;
}

/* 普通模式 */
.normal-row {
  /* 无固定高度，自然布局 */
}

/* 空状态 */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: #94a3b8;
  font-size: 0.9rem;
}
</style>
