/**
 * C3-5: VirtualAgentList 虚拟滚动测试
 *
 * 测试核心逻辑：
 * 1. <20 agents: 普通模式，全渲染
 * 2. >20 agents (≥21): 虚拟模式，仅渲染可见+buffer
 * 3. scroll 更新可见范围
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick, defineComponent, h, ref } from 'vue'

import VirtualAgentList from '../components/agent-list/VirtualAgentList.vue'

// ─── helpers ──────────────────────────────────────────────────

function generateAgents(count: number): Array<{ id: string; name: string }> {
  return Array.from({ length: count }, (_, i) => ({
    id: `agent-${i}`,
    name: `Agent ${i}`,
  }))
}

/** 让所有 setTimeout(0) 回调都同步执行 */
function flushTimers(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 50))
}

// ═══════════════════════════════════════════════════════════════════

describe('VirtualAgentList', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('ResizeObserver', function (
      this: { observe: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn>; unobserve: ReturnType<typeof vi.fn> },
      _cb: ResizeObserverCallback,
    ) {
      this.observe = vi.fn()
      this.disconnect = vi.fn()
      this.unobserve = vi.fn()
    } as unknown as new (cb: ResizeObserverCallback) => ResizeObserver)

    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      setTimeout(() => cb(0), 0)
      return 1
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  // ═══════════════════════════════════════════════════════════════════
  //  < threshold: 普通模式，全渲染
  // ═══════════════════════════════════════════════════════════════════

  describe('normal mode (< threshold)', () => {
    it('should render all items when count is below threshold', async () => {
      const items = ref(generateAgents(10))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, itemHeight: 80, threshold: 20 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()

      const renderedItems = wrapper.findAll('.agent-item')
      expect(renderedItems).toHaveLength(10)
      expect(renderedItems[0].text()).toBe('Agent 0')
      expect(renderedItems[9].text()).toBe('Agent 9')

      wrapper.unmount()
    })

    it('should not have virtual-mode class when below threshold', async () => {
      const items = ref(generateAgents(15))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, threshold: 20 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()
      expect(wrapper.find('.virtual-agent-list').classes()).not.toContain('virtual-mode')
      wrapper.unmount()
    })

    it('should not have virtual-spacer when below threshold', async () => {
      const items = ref(generateAgents(20))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, threshold: 20 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()
      expect(wrapper.find('.virtual-spacer').exists()).toBe(false)
      wrapper.unmount()
    })

    it('should render 0 items (empty state) correctly', async () => {
      const items = ref<unknown[]>([])
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, threshold: 20 },
        slots: {
          empty: () => h('div', { class: 'my-empty' }, 'No agents'),
        },
      })
      await nextTick()
      expect(wrapper.find('.my-empty').exists()).toBe(true)
      expect(wrapper.find('.my-empty').text()).toBe('No agents')
      wrapper.unmount()
    })

    it('should render exactly at threshold in normal mode', async () => {
      const items = ref(generateAgents(20))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, threshold: 20 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()
      expect(wrapper.find('.virtual-spacer').exists()).toBe(false)
      const renderedItems = wrapper.findAll('.agent-item')
      expect(renderedItems).toHaveLength(20)
      wrapper.unmount()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  ≥ threshold: 虚拟模式
  // ═══════════════════════════════════════════════════════════════════

  describe('virtual mode (≥ threshold)', () => {
    it('should enter virtual mode when items exceed threshold', async () => {
      const items = ref(generateAgents(21))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, itemHeight: 80, threshold: 20 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()

      expect(wrapper.find('.virtual-agent-list').classes()).toContain('virtual-mode')
      expect(wrapper.find('.virtual-spacer').exists()).toBe(true)
      expect(wrapper.find('.virtual-viewport').exists()).toBe(true)

      wrapper.unmount()
    })

    it('should only render visible + buffer items', async () => {
      const itemHeight = 80
      const buffer = 5
      const totalItems = 50

      const items = ref(generateAgents(totalItems))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, itemHeight, threshold: 20, buffer },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()

      const renderedItems = wrapper.findAll('.agent-item')
      expect(renderedItems.length).toBeLessThanOrEqual(18)
      expect(renderedItems.length).toBeGreaterThan(0)

      wrapper.unmount()
    })

    it('should render far fewer items than total in virtual mode', async () => {
      const items = ref(generateAgents(100))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, itemHeight: 80, threshold: 20, buffer: 5 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()

      const renderedItems = wrapper.findAll('.agent-item')
      expect(renderedItems.length).toBeLessThan(50)
      expect(renderedItems.length).toBeGreaterThan(0)

      wrapper.unmount()
    })

    it('should have correct total height spacer', async () => {
      const totalItems = 50
      const itemHeight = 80

      const items = ref(generateAgents(totalItems))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, itemHeight, threshold: 20 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()

      const spacer = wrapper.find('.virtual-spacer')
      expect(spacer.exists()).toBe(true)
      // totalHeight = 50 * 80 = 4000px
      expect(spacer.attributes('style')).toContain('height: 4000px')

      wrapper.unmount()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  scroll 更新 (rAF 节流)
  // ═══════════════════════════════════════════════════════════════════

  describe('scroll updates visible range', () => {
    it('should update visible items on scroll (after rAF)', async () => {
      const itemHeight = 80
      const buffer = 5
      const totalItems = 50

      const items = ref(generateAgents(totalItems))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, itemHeight, threshold: 20, buffer },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item', 'data-index': String(item._virtualIndex) }, item.name),
        },
      })
      await nextTick()

      const container = wrapper.find('.virtual-agent-list').element as HTMLElement
      Object.defineProperty(container, 'clientHeight', {
        value: 600,
        configurable: true,
        writable: true,
      })
      Object.defineProperty(container, 'scrollHeight', {
        value: 10000,
        configurable: true,
        writable: true,
      })
      Object.defineProperty(container, 'scrollTop', {
        value: 2000,
        configurable: true,
        writable: true,
      })
      container.dispatchEvent(new Event('scroll'))

      // Advance timers to trigger rAF
      vi.advanceTimersByTime(20)
      await nextTick()

      const renderedItems = wrapper.findAll('.agent-item')
      // startIndex = max(0, floor(2000/80) - 5) = max(0, 25 - 5) = 20
      expect(renderedItems.length).toBeGreaterThan(0)
      const firstIndex = parseInt(renderedItems[0].attributes('data-index')!)
      expect(firstIndex).toBeGreaterThanOrEqual(20)

      wrapper.unmount()
    })

    it('should handle scroll to very bottom', async () => {
      const itemHeight = 80
      const totalItems = 50

      const items = ref(generateAgents(totalItems))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, itemHeight, threshold: 20, buffer: 5 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item', 'data-index': String(item._virtualIndex) }, item.name),
        },
      })
      await nextTick()

      const container = wrapper.find('.virtual-agent-list').element as HTMLElement
      Object.defineProperty(container, 'clientHeight', {
        value: 600,
        configurable: true,
        writable: true,
      })
      Object.defineProperty(container, 'scrollTop', {
        value: 3400,
        configurable: true,
        writable: true,
      })
      Object.defineProperty(container, 'scrollHeight', {
        value: 4000,
        configurable: true,
        writable: true,
      })
      container.dispatchEvent(new Event('scroll'))

      vi.advanceTimersByTime(20)
      await nextTick()

      const renderedItems = wrapper.findAll('.agent-item')
      const lastIndex = parseInt(
        renderedItems[renderedItems.length - 1].attributes('data-index')!
      )
      // Should include the last item (index 49)
      expect(lastIndex).toBe(49)

      wrapper.unmount()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  mode 切换 (通过 setProps 更新)
  // ═══════════════════════════════════════════════════════════════════

  describe('mode switching', () => {
    it('should switch from normal to virtual when items increase past threshold', async () => {
      const wrapper = mount(VirtualAgentList, {
        props: { items: generateAgents(10), itemHeight: 80, threshold: 20 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()
      expect(wrapper.find('.virtual-spacer').exists()).toBe(false)

      // Use setProps to update items (triggers Vue reactivity)
      await wrapper.setProps({ items: generateAgents(25) })
      await nextTick()

      expect(wrapper.find('.virtual-spacer').exists()).toBe(true)
      expect(wrapper.find('.virtual-agent-list').classes()).toContain('virtual-mode')

      wrapper.unmount()
    })

    it('should switch from virtual to normal when items decrease below threshold', async () => {
      const wrapper = mount(VirtualAgentList, {
        props: { items: generateAgents(25), itemHeight: 80, threshold: 20 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()
      expect(wrapper.find('.virtual-spacer').exists()).toBe(true)

      await wrapper.setProps({ items: generateAgents(15) })
      await nextTick()

      expect(wrapper.find('.virtual-spacer').exists()).toBe(false)
      expect(wrapper.find('.virtual-agent-list').classes()).not.toContain('virtual-mode')

      wrapper.unmount()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  offsetY 计算
  // ═══════════════════════════════════════════════════════════════════

  describe('offsetY calculation', () => {
    it('should have offsetY = 0 at top', async () => {
      const items = ref(generateAgents(50))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, itemHeight: 80, threshold: 20 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()

      const viewport = wrapper.find('.virtual-viewport')
      expect(viewport.attributes('style')).toContain('translateY(0px)')

      wrapper.unmount()
    })

    it('should update offsetY on scroll', async () => {
      const itemHeight = 80
      const items = ref(generateAgents(50))
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, itemHeight, threshold: 20, buffer: 5 },
        slots: {
          item: ({ item }: any) =>
            h('div', { class: 'agent-item' }, item.name),
        },
      })
      await nextTick()

      const container = wrapper.find('.virtual-agent-list').element as HTMLElement
      Object.defineProperty(container, 'clientHeight', {
        value: 600,
        configurable: true,
        writable: true,
      })
      Object.defineProperty(container, 'scrollHeight', {
        value: 10000,
        configurable: true,
        writable: true,
      })
      Object.defineProperty(container, 'scrollTop', {
        value: 1600,
        configurable: true,
        writable: true,
      })
      container.dispatchEvent(new Event('scroll'))

      vi.advanceTimersByTime(20)
      await nextTick()

      const viewport = wrapper.find('.virtual-viewport')
      const style = viewport.attributes('style') || ''
      // startIndex = max(0, floor(1600/80) - 5) = max(0, 20 - 5) = 15
      // offsetY = 15 * 80 = 1200
      expect(style).toContain('translateY(1200px)')

      wrapper.unmount()
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  empty state
  // ═══════════════════════════════════════════════════════════════════

  describe('empty state', () => {
    it('should show default empty text when items is empty', async () => {
      const items = ref<unknown[]>([])
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, threshold: 20 },
      })
      await nextTick()

      expect(wrapper.find('.empty-state').exists()).toBe(true)
      expect(wrapper.find('.empty-state').text()).toBe('暂无数据')

      wrapper.unmount()
    })

    it('should use custom empty slot when provided', async () => {
      const items = ref<unknown[]>([])
      const wrapper = mount(VirtualAgentList, {
        props: { items: items.value, threshold: 20 },
        slots: {
          empty: () => h('div', { class: 'custom-empty' }, 'No agents found'),
        },
      })
      await nextTick()

      expect(wrapper.find('.custom-empty').exists()).toBe(true)
      expect(wrapper.find('.custom-empty').text()).toBe('No agents found')
      expect(wrapper.find('.empty-state').exists()).toBe(true)

      wrapper.unmount()
    })
  })
})
