/**
 * C3-5: StateManager.applyEvent version 防护测试
 *
 * 覆盖 3 种场景：
 * 1. version > 本地 version → 应用
 * 2. version ≤ 本地 version → 丢弃
 * 3. 无 version → 始终应用
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import { StateManager } from '../managers/StateManager'
import type { PatchEvent } from '../managers/StateManager'

describe('StateManager.applyEvent', () => {
  let sm: StateManager

  beforeEach(() => {
    sm = new StateManager()
    // 注册各 entity 集合
    sm.registerEntity('agents', ref([]))
    sm.registerEntity('subagents', ref([]))
    sm.registerEntity('tasks', ref([]))
    sm.registerEntity('collaboration', ref([{ activeAgents: 0 }]))
    sm.registerEntity('performance', ref([]))
  })

  // ═══════════════════════════════════════════════════════════════════
  //  version > 本地 version → 应用
  // ═══════════════════════════════════════════════════════════════════

  describe('version > local → apply', () => {
    it('should apply event when version is greater than local version', () => {
      // 初始 version = 0
      expect(sm.getVersion('agents')).toBe(0)

      const event: PatchEvent = {
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'agent-1',
        patch: { name: 'Test' },
        version: 1,
      }

      const applied = sm.applyEvent(event)
      expect(applied).toBe(true)
      expect(sm.getVersion('agents')).toBe(1)

      const agents = sm.getEntityCollection<any[]>('agents')!
      expect(agents.value).toHaveLength(1)
      expect(agents.value[0].name).toBe('Test')
    })

    it('should apply sequential events with increasing versions', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // version 1
      const r1 = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'agent-1',
        patch: { status: 'idle' },
        version: 1,
      })
      expect(r1).toBe(true)

      // version 2
      const r2 = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'agent-1',
        patch: { status: 'running' },
        version: 2,
      })
      expect(r2).toBe(true)

      // version 3
      const r3 = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'agent-1',
        patch: { status: 'completed' },
        version: 3,
      })
      expect(r3).toBe(true)

      expect(sm.getVersion('agents')).toBe(3)
      expect(agents.value[0].status).toBe('completed')
    })

    it('should track version independently per entity type', () => {
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'X' },
        version: 5,
      })
      sm.applyEvent({
        type: 'TaskChanged',
        entityType: 'tasks',
        entityId: 't1',
        patch: {},
        change: 'added',
        taskData: { title: 'Y' },
        version: 2,
      })

      expect(sm.getVersion('agents')).toBe(5)
      expect(sm.getVersion('tasks')).toBe(2)
    })

    it('should apply event after setting version via setVersion', () => {
      sm.setVersion('agents', 10)

      const r = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'X' },
        version: 11,
      })
      expect(r).toBe(true)
      expect(sm.getVersion('agents')).toBe(11)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  version ≤ 本地 version → 丢弃
  // ═══════════════════════════════════════════════════════════════════

  describe('version ≤ local → discard', () => {
    it('should discard event when version equals local version', () => {
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { status: 'running' },
        version: 5,
      })

      const agents = sm.getEntityCollection<any[]>('agents')!
      expect(agents.value[0].status).toBe('running')

      // same version → discard
      const r = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { status: 'completed' },
        version: 5,
      })
      expect(r).toBe(false)
      // state should NOT have changed
      expect(agents.value[0].status).toBe('running')
      expect(sm.getVersion('agents')).toBe(5)
    })

    it('should discard event when version is less than local version', () => {
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { status: 'running' },
        version: 10,
      })

      // lower version → discard
      const r = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { status: 'idle' },
        version: 8,
      })
      expect(r).toBe(false)
      expect(sm.getVersion('agents')).toBe(10)
    })

    it('should discard out-of-order events', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // apply version 3
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'V3' },
        version: 3,
      })
      expect(agents.value[0].name).toBe('V3')

      // version 2 (out of order) → discard
      const r = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'V2-REPLAY' },
        version: 2,
      })
      expect(r).toBe(false)
      expect(agents.value[0].name).toBe('V3') // unchanged

      // version 1 (out of order) → discard
      const r2 = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'V1-REPLAY' },
        version: 1,
      })
      expect(r2).toBe(false)
      expect(agents.value[0].name).toBe('V3') // still unchanged
    })

    it('should discard all duplicate versions across different entity types', () => {
      // agents version 10
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'X' },
        version: 10,
      })

      // tasks version 10 (separate entity type, different version counter)
      const r = sm.applyEvent({
        type: 'TaskChanged',
        entityType: 'tasks',
        entityId: 't1',
        patch: {},
        change: 'added',
        taskData: { title: 'Y' },
        version: 10,
      })
      // tasks local version is 0, so 10 > 0 → should apply
      expect(r).toBe(true)
    })

    it('should return false for replayed events without changing data', () => {
      const collaboration = sm.getEntityCollection<any[]>('collaboration')!

      // apply version 1
      sm.applyEvent({
        type: 'CollaborationChanged',
        entityType: 'collaboration',
        patch: { activeAgents: 5 },
        version: 1,
      })
      expect(collaboration.value[0].activeAgents).toBe(5)

      // replay version 1
      const r = sm.applyEvent({
        type: 'CollaborationChanged',
        entityType: 'collaboration',
        patch: { activeAgents: 100 },  // would change if applied
        version: 1,
      })
      expect(r).toBe(false)
      expect(collaboration.value[0].activeAgents).toBe(5) // unchanged
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  无 version → 始终应用
  // ═══════════════════════════════════════════════════════════════════

  describe('no version → always apply', () => {
    it('should apply event without version field', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // no version → always apply
      const r = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'NoVersion' },
      })
      expect(r).toBe(true)
      expect(agents.value[0].name).toBe('NoVersion')
      expect(sm.getVersion('agents')).toBe(0) // version unchanged
    })

    it('should apply multiple events without version', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { status: 'idle' },
      })
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { status: 'running' },
      })
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { status: 'completed' },
      })

      // all applied
      expect(agents.value).toHaveLength(1)
      expect(agents.value[0].status).toBe('completed')
      expect(sm.getVersion('agents')).toBe(0)
    })

    it('should apply no-version event even after versioned event', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // versioned event first
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'Versioned' },
        version: 10,
      })
      expect(sm.getVersion('agents')).toBe(10)

      // no-version event → should still apply
      const r = sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'NoVersion' },
      })
      expect(r).toBe(true)
      expect(agents.value[0].name).toBe('NoVersion')
      // version stays at 10 (no-version events don't update version)
      expect(sm.getVersion('agents')).toBe(10)
    })

    it('should apply no-version events interleaved with versioned events', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // v1
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { s: 'v1' }, version: 1 })
      // no-version
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { s: 'nv1' } })
      // v2
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { s: 'v2' }, version: 2 })
      // no-version
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { s: 'nv2' } })

      expect(agents.value[0].s).toBe('nv2')
      expect(sm.getVersion('agents')).toBe(2)
    })

    it('should apply no-version performance replacement events', () => {
      const perf = sm.getEntityCollection<any[]>('performance')!

      sm.applyEvent({
        type: 'PerformanceSnapshot',
        entityType: 'performance',
        data: { cpu: 50 },
      })
      expect(perf.value[0].cpu).toBe(50)

      sm.applyEvent({
        type: 'PerformanceSnapshot',
        entityType: 'performance',
        data: { cpu: 80 },
      })
      expect(perf.value[0].cpu).toBe(80)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  entity not registered
  // ═══════════════════════════════════════════════════════════════════

  describe('entity not registered', () => {
    it('should return false when entity type has no registered collection', () => {
      // Create a fresh StateManager with NO registered entities
      const fresh = new StateManager()

      const r = fresh.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { name: 'X' },
      })
      expect(r).toBe(false)
    })
  })
})
