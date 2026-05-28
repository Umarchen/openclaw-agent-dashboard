/**
 * C3-5: 端到端集成测试
 *
 * 测试完整生命周期：
 * 1. bootstrap → 全量替换
 * 2. 增量 patch → merge
 * 3. 乱序事件 → 丢弃
 * 4. 多 entity 协同
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import { StateManager } from '../managers/StateManager'
import type { PatchEvent } from '../managers/StateManager'

describe('E2E: bootstrap → patch → out-of-order', () => {
  let sm: StateManager

  beforeEach(() => {
    sm = new StateManager()
    // Register all entity collections
    sm.registerEntity('agents', ref([]))
    sm.registerEntity('subagents', ref([]))
    sm.registerEntity('tasks', ref([]))
    sm.registerEntity('collaboration', ref([{ activeAgents: 0 }]))
    sm.registerEntity('performance', ref([]))
  })

  // ═══════════════════════════════════════════════════════════════════
  //  1. Bootstrap: full_state / FullStateSnapshot 全量替换
  // ═══════════════════════════════════════════════════════════════════

  describe('bootstrap → full state replacement', () => {
    it('should replace agents collection via bootstrap', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // Bootstrap replaces all
      sm.bootstrapReplace('agents', [
        { id: 'a1', name: 'Agent 1', status: 'idle' },
        { id: 'a2', name: 'Agent 2', status: 'running' },
        { id: 'a3', name: 'Agent 3', status: 'completed' },
      ])

      expect(agents.value).toHaveLength(3)
      expect(agents.value.map((a: any) => a.id)).toEqual(['a1', 'a2', 'a3'])
    })

    it('should replace all entity types via bootstrap', () => {
      sm.bootstrapReplace('agents', [
        { id: 'a1', name: 'Alpha' },
        { id: 'a2', name: 'Beta' },
      ])
      sm.bootstrapReplace('subagents', [
        { runId: 'r1', taskName: 'Build' },
        { runId: 'r2', taskName: 'Test' },
        { runId: 'r3', taskName: 'Deploy' },
      ])
      sm.bootstrapReplace('tasks', [
        { id: 't1', title: 'Setup CI' },
        { id: 't2', title: 'Write tests' },
      ])
      sm.bootstrapReplace('performance', [
        { cpu: 25, memory: 512, agents: 2 },
      ])
      sm.bootstrapReplace('collaboration', [
        { activeAgents: 2, totalMessages: 50 },
      ])

      expect(sm.getEntityCollection<any[]>('agents')!.value).toHaveLength(2)
      expect(sm.getEntityCollection<any[]>('subagents')!.value).toHaveLength(3)
      expect(sm.getEntityCollection<any[]>('tasks')!.value).toHaveLength(2)
      expect(sm.getEntityCollection<any[]>('performance')!.value).toHaveLength(1)
      expect(sm.getEntityCollection<any[]>('collaboration')!.value).toHaveLength(1)
    })

    it('should clear previous data on bootstrap', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // First bootstrap
      sm.bootstrapReplace('agents', [
        { id: 'a1', name: 'Old' },
        { id: 'a2', name: 'Older' },
      ])
      expect(agents.value).toHaveLength(2)

      // Second bootstrap (simulating reconnect)
      sm.bootstrapReplace('agents', [
        { id: 'b1', name: 'New' },
        { id: 'b2', name: 'Newer' },
        { id: 'b3', name: 'Newest' },
      ])
      expect(agents.value).toHaveLength(3)
      expect(agents.value.map((a: any) => a.name)).toEqual(['New', 'Newer', 'Newest'])
      // Old data is completely gone
    })

    it('should accept empty bootstrap', () => {
      sm.bootstrapReplace('agents', [])
      expect(sm.getEntityCollection<any[]>('agents')!.value).toHaveLength(0)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  2. 增量 Patch: bootstrap → patch merge
  // ═══════════════════════════════════════════════════════════════════

  describe('bootstrap → incremental patch', () => {
    it('should patch agents after bootstrap', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // Bootstrap
      sm.bootstrapReplace('agents', [
        { id: 'a1', name: 'Agent 1', status: 'idle', model: 'gpt-4' },
        { id: 'a2', name: 'Agent 2', status: 'running', model: 'gpt-4' },
      ])

      // Incremental patch
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { status: 'running' },
        version: 1,
      })

      expect(agents.value[0].status).toBe('running')
      expect(agents.value[0].name).toBe('Agent 1')  // unchanged
      expect(agents.value[0].model).toBe('gpt-4')   // unchanged
      expect(agents.value[1].status).toBe('running')  // unchanged
    })

    it('should add new agent via patch after bootstrap', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      sm.bootstrapReplace('agents', [{ id: 'a1', name: 'Agent 1' }])

      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a2',
        patch: { name: 'New Agent' },
        version: 1,
      })

      expect(agents.value).toHaveLength(2)
      expect(agents.value[1].name).toBe('New Agent')
    })

    it('should apply task lifecycle (add → update → remove) after bootstrap', () => {
      const tasks = sm.getEntityCollection<any[]>('tasks')!

      sm.bootstrapReplace('tasks', [])

      // Add task
      sm.applyEvent({
        type: 'TaskChanged',
        entityType: 'tasks',
        entityId: 't1',
        change: 'added',
        taskData: { title: 'Build App', status: 'pending' },
        version: 1,
      })
      expect(tasks.value).toHaveLength(1)
      expect(tasks.value[0].title).toBe('Build App')

      // Update task
      sm.applyEvent({
        type: 'TaskChanged',
        entityType: 'tasks',
        entityId: 't1',
        change: 'updated',
        taskData: { status: 'in_progress' },
        version: 2,
      })
      expect(tasks.value).toHaveLength(1)
      expect(tasks.value[0].title).toBe('Build App')  // unchanged
      expect(tasks.value[0].status).toBe('in_progress') // updated

      // Complete and remove
      sm.applyEvent({
        type: 'TaskChanged',
        entityType: 'tasks',
        entityId: 't1',
        change: 'removed',
        version: 3,
      })
      expect(tasks.value).toHaveLength(0)
    })

    it('should apply performance snapshot after bootstrap', () => {
      const perf = sm.getEntityCollection<any[]>('performance')!

      sm.bootstrapReplace('performance', [{ cpu: 10, memory: 256 }])

      sm.applyEvent({
        type: 'PerformanceSnapshot',
        entityType: 'performance',
        data: { cpu: 45, memory: 1024, disk: 500 },
        version: 1,
      })

      expect(perf.value).toHaveLength(1)
      const data = perf.value[0]
      expect(data.cpu).toBe(45)
      expect(data.memory).toBe(1024)
      expect(data.disk).toBe(500)
    })

    it('should apply collaboration changes after bootstrap', () => {
      const collab = sm.getEntityCollection<any[]>('collaboration')!

      sm.bootstrapReplace('collaboration', [{ activeAgents: 3, totalMessages: 100 }])

      sm.applyEvent({
        type: 'CollaborationChanged',
        entityType: 'collaboration',
        patch: { activeAgents: 5, newField: 'hello' },
        version: 1,
      })

      expect(collab.value[0].activeAgents).toBe(5)
      expect(collab.value[0].totalMessages).toBe(100) // unchanged
      expect(collab.value[0].newField).toBe('hello')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  3. 乱序丢弃: out-of-order events are discarded
  // ═══════════════════════════════════════════════════════════════════

  describe('out-of-order event discard', () => {
    it('should discard stale events after bootstrap + patches', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // Bootstrap
      sm.bootstrapReplace('agents', [{ id: 'a1', name: 'Agent', status: 'idle' }])

      // Sequential patches: v1, v2, v3
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { status: 'running' }, version: 1 })
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { status: 'completed' }, version: 2 })
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { model: 'gpt-5' }, version: 3 })

      expect(agents.value[0].status).toBe('completed')
      expect(agents.value[0].model).toBe('gpt-5')

      // Out-of-order: replay v1
      const r1 = sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { status: 'STALE-1' }, version: 1 })
      expect(r1).toBe(false)

      // Out-of-order: replay v2
      const r2 = sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { status: 'STALE-2' }, version: 2 })
      expect(r2).toBe(false)

      // State unchanged
      expect(agents.value[0].status).toBe('completed')
      expect(agents.value[0].model).toBe('gpt-5')
    })

    it('should handle gap in version sequence', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { name: 'V1' }, version: 1 })
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { name: 'V5' }, version: 5 })
      // v2, v3, v4 were missed — that's OK (eventual consistency)

      expect(agents.value[0].name).toBe('V5')

      // Replay v2-v4 → should be discarded
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { name: 'V2' }, version: 2 })
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { name: 'V3' }, version: 3 })
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { name: 'V4' }, version: 4 })
      expect(agents.value[0].name).toBe('V5')
    })

    it('should handle reconnect: bootstrap resets, then new patches apply', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // Initial state
      sm.bootstrapReplace('agents', [{ id: 'a1', name: 'V1' }])
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { name: 'V2' }, version: 10 })
      expect(agents.value[0].name).toBe('V2')

      // Simulate reconnect: reset versions, re-bootstrap
      sm.resetVersions()
      sm.bootstrapReplace('agents', [{ id: 'a1', name: 'Fresh' }])

      // Old events should still be discarded (version tracking is reset)
      // but since we resetVersions, local version is now 0
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { name: 'FreshUpdated' }, version: 1 })
      expect(agents.value[0].name).toBe('FreshUpdated')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  4. 多 entity 协同
  // ═══════════════════════════════════════════════════════════════════

  describe('multi-entity coordination', () => {
    it('should handle interleaved events across entity types', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!
      const tasks = sm.getEntityCollection<any[]>('tasks')!
      const perf = sm.getEntityCollection<any[]>('performance')!

      // Bootstrap
      sm.bootstrapReplace('agents', [{ id: 'a1', name: 'Alpha' }])
      sm.bootstrapReplace('tasks', [])

      // Interleaved events with different entity types
      // Agent patch v1
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { status: 'running' }, version: 1 })
      // Task add v1 (different entity, independent version)
      sm.applyEvent({ type: 'TaskChanged', entityType: 'tasks', entityId: 't1', change: 'added', taskData: { title: 'Deploy' }, version: 1 })
      // Agent patch v2
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: { model: 'gpt-5' }, version: 2 })
      // Perf snapshot
      sm.applyEvent({ type: 'PerformanceSnapshot', entityType: 'performance', data: { cpu: 50 }, version: 1 })
      // Task update v2
      sm.applyEvent({ type: 'TaskChanged', entityType: 'tasks', entityId: 't1', change: 'updated', taskData: { status: 'done' }, version: 2 })

      // Verify final state
      expect(agents.value[0].status).toBe('running')
      expect(agents.value[0].model).toBe('gpt-5')
      expect(tasks.value[0].title).toBe('Deploy')
      expect(tasks.value[0].status).toBe('done')
      expect(perf.value[0].cpu).toBe(50)

      // Version tracking is independent
      expect(sm.getVersion('agents')).toBe(2)
      expect(sm.getVersion('tasks')).toBe(2)
      expect(sm.getVersion('performance')).toBe(1)
    })

    it('should handle bootstrap → many patches → re-bootstrap cycle', () => {
      const agents = sm.getEntityCollection<any[]>('agents')!

      // Bootstrap 1
      sm.bootstrapReplace('agents', [
        { id: 'a1', name: 'Agent 1' },
        { id: 'a2', name: 'Agent 2' },
      ])

      // Apply 10 patches
      for (let i = 1; i <= 10; i++) {
        sm.applyEvent({
          type: 'AgentStateChanged',
          entityType: 'agents',
          entityId: 'a1',
          patch: { patchCount: i },
          version: i,
        })
      }
      expect(agents.value[0].patchCount).toBe(10)

      // Re-bootstrap (simulating page reload)
      sm.resetVersions()
      sm.bootstrapReplace('agents', [
        { id: 'a1', name: 'Fresh Agent 1' },
        { id: 'a2', name: 'Fresh Agent 2' },
        { id: 'a3', name: 'Fresh Agent 3' },  // New agent appeared
      ])
      expect(agents.value).toHaveLength(3)
      expect(agents.value[0].name).toBe('Fresh Agent 1')
      expect(agents.value[0].patchCount).toBeUndefined() // patchCount gone after bootstrap

      // New patches apply
      sm.applyEvent({
        type: 'AgentStateChanged',
        entityType: 'agents',
        entityId: 'a1',
        patch: { status: 'running' },
        version: 1,
      })
      expect(agents.value[0].status).toBe('running')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  5. applyEvent return value correctness
  // ═══════════════════════════════════════════════════════════════════

  describe('applyEvent return values', () => {
    it('should return true for applied events, false for discarded', () => {
      sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: {}, version: 1 }) // true
      expect(sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: {}, version: 1 })).toBe(false) // same version
      expect(sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: {}, version: 0 })).toBe(false) // lower version
      expect(sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: {}, version: 2 })).toBe(true)  // higher version
      expect(sm.applyEvent({ type: 'AgentStateChanged', entityType: 'agents', entityId: 'a1', patch: {} })).toBe(true)             // no version
    })
  })
})
