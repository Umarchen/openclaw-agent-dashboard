/**
 * C3-5: StateManager.patchMerge 单元测试
 *
 * 覆盖所有 5 种 entity 的 merge 策略：
 * - agents: 按 agent_id 字段级 patch
 * - subagents: 按 run_id merge
 * - tasks: add → 追加, update → 替换, remove → 删除
 * - collaboration: 字段级 merge
 * - performance: 整包替换
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import { StateManager } from '../managers/StateManager'
import type { Ref } from 'vue'

describe('StateManager.patchMerge', () => {
  let sm: StateManager

  beforeEach(() => {
    sm = new StateManager()
  })

  // ═══════════════════════════════════════════════════════════════════
  //  helpers
  // ═══════════════════════════════════════════════════════════════════

  /** 创建并注册一个空的 entity 集合 */
  function setupEmpty(entityType: Parameters<typeof sm.registerEntity>[0]): Ref<unknown[]> {
    const col = ref<unknown[]>([])
    sm.registerEntity(entityType, col)
    return col
  }

  /** 创建并注册一个有初始数据的 entity 集合 */
  function setupWith(
    entityType: Parameters<typeof sm.registerEntity>[0],
    data: unknown[]
  ): Ref<unknown[]> {
    const col = ref<unknown[]>(data)
    sm.registerEntity(entityType, col)
    return col
  }

  // ═══════════════════════════════════════════════════════════════════
  //  agents: 按 agent_id 字段级 patch
  // ═══════════════════════════════════════════════════════════════════

  describe('agents', () => {
    it('should add a new agent when collection is empty', () => {
      const col = setupEmpty('agents')
      sm.patchMerge('agents', 'agent-1', { name: 'Test Agent', status: 'running' })

      expect(col.value).toHaveLength(1)
      expect((col.value[0] as any).id).toBe('agent-1')
      expect((col.value[0] as any).name).toBe('Test Agent')
      expect((col.value[0] as any).status).toBe('running')
    })

    it('should add a new agent to existing collection', () => {
      const col = setupWith('agents', [
        { id: 'agent-1', name: 'Agent One', status: 'idle' },
      ])
      sm.patchMerge('agents', 'agent-2', { name: 'Agent Two', status: 'running' })

      expect(col.value).toHaveLength(2)
      expect((col.value[1] as any).id).toBe('agent-2')
      // existing should be unchanged
      expect((col.value[0] as any).name).toBe('Agent One')
    })

    it('should patch existing agent fields', () => {
      const col = setupWith('agents', [
        { id: 'agent-1', name: 'Agent One', status: 'idle', model: 'gpt-4' },
      ])
      sm.patchMerge('agents', 'agent-1', { status: 'running', model: 'gpt-5' })

      expect(col.value).toHaveLength(1)
      const agent = col.value[0] as any
      expect(agent.id).toBe('agent-1')
      expect(agent.name).toBe('Agent One')   // unchanged
      expect(agent.status).toBe('running')    // updated
      expect(agent.model).toBe('gpt-5')       // updated
    })

    it('should patch only specified fields (not affect others)', () => {
      const col = setupWith('agents', [
        { id: 'a1', name: 'X', status: 'idle', tags: ['dev'], score: 10 },
      ])
      sm.patchMerge('agents', 'a1', { score: 99 })

      const agent = col.value[0] as any
      expect(agent.name).toBe('X')
      expect(agent.status).toBe('idle')
      expect(agent.tags).toEqual(['dev'])
      expect(agent.score).toBe(99)
    })

    it('should handle empty patch data (no-op)', () => {
      const col = setupWith('agents', [
        { id: 'a1', name: 'X', status: 'idle' },
      ])
      // patchMerge with empty patch should not crash
      sm.patchMerge('agents', 'a1', {})
      expect(col.value).toHaveLength(1)
      expect((col.value[0] as any).name).toBe('X')
    })

    it('should not add duplicate agent with same id', () => {
      const col = setupWith('agents', [
        { id: 'a1', name: 'X' },
      ])
      // patching existing agent merges, does not add duplicate
      sm.patchMerge('agents', 'a1', { name: 'Y' })
      expect(col.value).toHaveLength(1)
      expect((col.value[0] as any).name).toBe('Y')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  subagents: 按 run_id merge
  // ═══════════════════════════════════════════════════════════════════

  describe('subagents', () => {
    it('should add a new subagent', () => {
      const col = setupEmpty('subagents')
      sm.patchMerge('subagents', 'run-1', { taskName: 'Deploy', status: 'completed' })

      expect(col.value).toHaveLength(1)
      const sub = col.value[0] as any
      expect(sub.runId).toBe('run-1')
      expect(sub.id).toBe('run-1')
      expect(sub.taskName).toBe('Deploy')
    })

    it('should patch existing subagent by runId', () => {
      const col = setupWith('subagents', [
        { runId: 'run-1', id: 'run-1', taskName: 'Deploy', status: 'running' },
      ])
      sm.patchMerge('subagents', 'run-1', { status: 'completed', result: 'success' })

      const sub = col.value[0] as any
      expect(sub.runId).toBe('run-1')
      expect(sub.taskName).toBe('Deploy')   // unchanged
      expect(sub.status).toBe('completed')  // updated
      expect(sub.result).toBe('success')    // new field
    })

    it('should patch existing subagent by id (fallback)', () => {
      const col = setupWith('subagents', [
        { id: 'run-1', taskName: 'Build', status: 'running' },
      ])
      sm.patchMerge('subagents', 'run-1', { status: 'failed' })

      expect((col.value[0] as any).status).toBe('failed')
    })

    it('should add multiple subagents', () => {
      const col = setupEmpty('subagents')
      sm.patchMerge('subagents', 'run-1', { taskName: 'Build' })
      sm.patchMerge('subagents', 'run-2', { taskName: 'Test' })
      sm.patchMerge('subagents', 'run-3', { taskName: 'Deploy' })

      expect(col.value).toHaveLength(3)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  tasks: add → 追加, update → 替换, remove → 删除
  // ═══════════════════════════════════════════════════════════════════

  describe('tasks', () => {
    it('should add a new task', () => {
      const col = setupEmpty('tasks')
      sm.patchMerge('tasks', 'task-1', {}, { change: 'added', taskData: { title: 'Setup CI' } })

      expect(col.value).toHaveLength(1)
      const task = col.value[0] as any
      expect(task.id).toBe('task-1')
      expect(task.title).toBe('Setup CI')
    })

    it('should not add duplicate task with same id', () => {
      const col = setupWith('tasks', [
        { id: 'task-1', title: 'Existing' },
      ])
      sm.patchMerge('tasks', 'task-1', {}, { change: 'added', taskData: { title: 'Duplicate' } })

      // should not add duplicate
      expect(col.value).toHaveLength(1)
      expect((col.value[0] as any).title).toBe('Existing')
    })

    it('should update an existing task', () => {
      const col = setupWith('tasks', [
        { id: 'task-1', title: 'Setup CI', status: 'pending' },
      ])
      sm.patchMerge('tasks', 'task-1', {}, { change: 'updated', taskData: { status: 'done', result: 'ok' } })

      const task = col.value[0] as any
      expect(task.title).toBe('Setup CI')    // unchanged
      expect(task.status).toBe('done')       // updated
      expect(task.result).toBe('ok')         // new field
    })

    it('should update non-existent task (no-op)', () => {
      const col = setupWith('tasks', [
        { id: 'task-1', title: 'A' },
      ])
      sm.patchMerge('tasks', 'task-99', {}, { change: 'updated', taskData: { title: 'B' } })

      // task-99 doesn't exist, update is no-op
      expect(col.value).toHaveLength(1)
      expect((col.value[0] as any).title).toBe('A')
    })

    it('should remove an existing task', () => {
      const col = setupWith('tasks', [
        { id: 'task-1', title: 'A' },
        { id: 'task-2', title: 'B' },
        { id: 'task-3', title: 'C' },
      ])
      sm.patchMerge('tasks', 'task-2', {}, { change: 'removed' })

      expect(col.value).toHaveLength(2)
      expect((col.value as any[]).map((t: any) => t.id)).toEqual(['task-1', 'task-3'])
    })

    it('should remove non-existent task (no-op)', () => {
      const col = setupWith('tasks', [
        { id: 'task-1', title: 'A' },
      ])
      sm.patchMerge('tasks', 'task-99', {}, { change: 'removed' })
      expect(col.value).toHaveLength(1)
    })

    it('should handle task add without taskData', () => {
      const col = setupEmpty('tasks')
      sm.patchMerge('tasks', 'task-1', {}, { change: 'added' })

      // should add entry with just the id
      expect(col.value).toHaveLength(1)
      expect((col.value[0] as any).id).toBe('task-1')
    })

    it('should not apply task operation without change type', () => {
      const col = setupWith('tasks', [{ id: 'task-1', title: 'A' }])
      // no change specified → no-op
      sm.patchMerge('tasks', 'task-1', {})
      expect(col.value).toHaveLength(1)
      expect((col.value[0] as any).title).toBe('A')
    })

    it('should not apply task operation without taskId (key)', () => {
      const col = setupEmpty('tasks')
      // no entityId → no-op
      sm.patchMerge('tasks', undefined, {}, { change: 'added', taskData: { title: 'X' } })
      expect(col.value).toHaveLength(0)
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  collaboration: 字段级 merge
  // ═══════════════════════════════════════════════════════════════════

  describe('collaboration', () => {
    it('should patch collaboration fields on existing data', () => {
      const col = setupWith('collaboration', [
        { activeAgents: 3, totalMessages: 10, lastActive: '2026-01-01' },
      ])
      sm.patchMerge('collaboration', undefined, { activeAgents: 5, totalMessages: 20 })

      const data = col.value[0] as any
      expect(data.activeAgents).toBe(5)
      expect(data.totalMessages).toBe(20)
      expect(data.lastActive).toBe('2026-01-01')  // unchanged
    })

    it('should handle empty collaboration array (no-op)', () => {
      const col = setupEmpty('collaboration')
      sm.patchMerge('collaboration', undefined, { activeAgents: 1 })
      expect(col.value).toHaveLength(0)
    })

    it('should add new fields to collaboration', () => {
      const col = setupWith('collaboration', [
        { activeAgents: 1 },
      ])
      sm.patchMerge('collaboration', undefined, { newField: 'hello', anotherField: 42 })

      const data = col.value[0] as any
      expect(data.activeAgents).toBe(1)
      expect(data.newField).toBe('hello')
      expect(data.anotherField).toBe(42)
    })

    it('should overwrite existing fields in collaboration', () => {
      const col = setupWith('collaboration', [
        { field1: 'old', field2: 'old' },
      ])
      sm.patchMerge('collaboration', undefined, { field1: 'new' })

      const data = col.value[0] as any
      expect(data.field1).toBe('new')
      expect(data.field2).toBe('old')
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  performance: 整包替换
  // ═══════════════════════════════════════════════════════════════════

  describe('performance', () => {
    it('should replace performance data entirely', () => {
      const col = setupWith('performance', [
        { cpu: 50, memory: 1024, agents: 5 },
      ])
      sm.patchMerge('performance', undefined, {}, {
        data: { cpu: 80, memory: 2048, agents: 10, disk: 500 },
      })

      const data = col.value[0] as any
      expect(data.cpu).toBe(80)
      expect(data.memory).toBe(2048)
      expect(data.agents).toBe(10)
      expect(data.disk).toBe(500)
      // old values are gone (replaced, not merged)
    })

    it('should add performance data to empty collection', () => {
      const col = setupEmpty('performance')
      sm.patchMerge('performance', undefined, {}, {
        data: { cpu: 25, memory: 512 },
      })

      expect(col.value).toHaveLength(1)
      const data = col.value[0] as any
      expect(data.cpu).toBe(25)
      expect(data.memory).toBe(512)
    })

    it('should replace with completely different fields', () => {
      const col = setupWith('performance', [
        { metricA: 1, metricB: 2 },
      ])
      sm.patchMerge('performance', undefined, {}, {
        data: { metricX: 'hello', metricY: [1, 2, 3] },
      })

      const data = col.value[0] as any
      expect(data.metricA).toBeUndefined()
      expect(data.metricB).toBeUndefined()
      expect(data.metricX).toBe('hello')
      expect(data.metricY).toEqual([1, 2, 3])
    })

    it('should not modify data when no data option provided', () => {
      const col = setupWith('performance', [
        { cpu: 50 },
      ])
      sm.patchMerge('performance', undefined, {})
      expect((col.value[0] as any).cpu).toBe(50)
    })

    it('should handle multiple rapid performance replacements (snapshot semantics)', () => {
      const col = setupEmpty('performance')
      sm.patchMerge('performance', undefined, {}, { data: { v: 1 } })
      sm.patchMerge('performance', undefined, {}, { data: { v: 2 } })
      sm.patchMerge('performance', undefined, {}, { data: { v: 3 } })

      expect(col.value).toHaveLength(1)
      expect((col.value[0] as any).v).toBe(3) // only last snapshot
    })
  })

  // ═══════════════════════════════════════════════════════════════════
  //  edge cases
  // ═══════════════════════════════════════════════════════════════════

  describe('edge cases', () => {
    it('should no-op when entity is not registered', () => {
      // 'agents' not registered — should not throw
      sm.patchMerge('agents', 'agent-1', { name: 'X' })
      // No assertion needed — just that it doesn't crash
    })

    it('should handle patching entity with no matching strategy', () => {
      // This test assumes the entity type is valid. The strategy map
      // covers all 5 types, so this tests the unreachable branch safety.
      const col = setupEmpty('agents')
      sm.patchMerge('agents', 'a1', { name: 'Test' })
      expect(col.value).toHaveLength(1)
    })
  })
})
