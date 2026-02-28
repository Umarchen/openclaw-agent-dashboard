<template>
  <div class="workflow-view">
    <h2>项目流水线</h2>
    
    <div class="project-selector">
      <select v-model="selectedProjectId" @change="loadWorkflow">
        <option value="">选择项目...</option>
        <option v-for="project in projects" :key="project.projectId" :value="project.projectId">
          {{ project.projectName }}
        </option>
      </select>
    </div>

    <div v-if="workflow" class="pipeline">
      <div class="stage" v-for="(stage, key) in stages" :key="key" :class="`status-${stage.status}`">
        <div class="stage-icon">
          <span v-if="stage.status === 'done'">✅</span>
          <span v-else-if="stage.status === 'in-progress'">🔄</span>
          <span v-else>⏳</span>
        </div>
        <div class="stage-info">
          <div class="stage-name">{{ stage.name }}</div>
          <div class="stage-status">{{ stage.statusText }}</div>
        </div>
        <div v-if="stage.status !== 'pending'" class="arrow">→</div>
      </div>
    </div>

    <div v-if="workflow && workflow.artifacts.length > 0" class="artifacts">
      <h3>产出物</h3>
      <ul>
        <li v-for="artifact in workflow.artifacts" :key="artifact">
          {{ artifact }}
        </li>
      </ul>
    </div>

    <div v-if="!workflow" class="no-workflow">
      <p>暂无项目数据</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRealtime } from '../composables'

interface WorkflowStage {
  name: string
  status: 'pending' | 'in-progress' | 'done'
  statusText: string
}

interface Workflow {
  stages: {
    prd?: string
    design?: string
    dev?: string
    qa?: string
    deploy?: string
  }
  currentStage?: string
  artifacts: string[]
}

const { subscribe } = useRealtime()
const projects = ref<any[]>([])
const selectedProjectId = ref('')
const workflow = ref<Workflow | null>(null)

const stages = computed(() => {
  if (!workflow.value) return []

  const stageMap: { [key: string]: string } = {
    'prd': '需求分析',
    'design': '系统设计',
    'dev': '代码开发',
    'qa': '测试验收',
    'deploy': '部署上线'
  }

  const statusMap: { [key: string]: string } = {
    'pending': '待开始',
    'in-progress': '进行中',
    'done': '已完成'
  }

  const result: WorkflowStage[] = []

  for (const [key, status] of Object.entries(workflow.value.stages || {})) {
    result.push({
      name: stageMap[key] || key,
      status: status as any,
      statusText: statusMap[status] || status
    })
  }

  return result
})

async function loadProjects() {
  try {
    const res = await fetch('/api/workflows')
    projects.value = await res.json()
    
    if (projects.value.length > 0) {
      selectedProjectId.value = projects.value[0].projectId
      loadWorkflow()
    }
  } catch (error) {
    console.error('加载项目列表失败:', error)
  }
}

async function loadWorkflow() {
  if (!selectedProjectId.value) return

  try {
    const res = await fetch(`/api/workflow/${selectedProjectId.value}`)
    workflow.value = await res.json()
  } catch (error) {
    console.error('加载工作流失败:', error)
    workflow.value = null
  }
}

function handleWorkflowsUpdate(data: unknown): void {
  if (Array.isArray(data)) {
    projects.value = data as any[]
    if (selectedProjectId.value && projects.value.some((p: any) => p.projectId === selectedProjectId.value)) {
      loadWorkflow()
    }
  }
}

let unsubscribe: (() => void) | null = null

onMounted(() => {
  loadProjects()
  unsubscribe = subscribe('workflows', handleWorkflowsUpdate)
})

onUnmounted(() => {
  unsubscribe?.()
})
</script>

<style scoped>
.workflow-view {
  padding: 1.5rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

h2 {
  margin: 0 0 1.5rem 0;
  font-size: 1.3rem;
  color: #333;
}

.project-selector {
  margin-bottom: 1.5rem;
}

.project-selector select {
  padding: 0.5rem 1rem;
  font-size: 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  background: white;
  min-width: 200px;
}

.pipeline {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.stage {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 6px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}

.stage.status-done {
  background: #d1fae5;
  border-color: #10b981;
}

.stage.status-in-progress {
  background: #fef3c7;
  border-color: #f59e0b;
}

.stage.status-pending {
  background: #f3f4f6;
  border-color: #d1d5db;
}

.stage-icon {
  font-size: 1.5rem;
}

.stage-name {
  font-weight: 600;
  color: #333;
}

.stage-status {
  font-size: 0.85rem;
  color: #666;
}

.arrow {
  color: #999;
  font-size: 1.2rem;
}

.artifacts {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid #e5e7eb;
}

.artifacts h3 {
  margin: 0 0 1rem 0;
  font-size: 1.1rem;
  color: #666;
}

.artifacts ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.artifacts li {
  padding: 0.5rem;
  background: #f9fafb;
  border-radius: 4px;
  margin-bottom: 0.5rem;
  font-size: 0.9rem;
  color: #666;
}

.no-workflow {
  text-align: center;
  padding: 2rem;
  color: #999;
}
</style>
