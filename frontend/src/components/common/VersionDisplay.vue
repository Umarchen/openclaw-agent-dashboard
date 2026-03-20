<template>
  <!-- 版本号显示组件 -->
  <div class="version-display">
    <!-- 加载中状态 -->
    <template v-if="loading">
      <span class="loading-text">加载中...</span>
    </template>
    
    <!-- 错误状态 -->
    <template v-else-if="error">
      <span class="error-text">版本信息获取失败</span>
    </template>
    
    <!-- 正常显示 -->
    <template v-else>
      <span 
        class="version-text" 
        @mouseenter="showTooltip = true" 
        @mouseleave="showTooltip = false"
      >
        {{ displayText }}
      </span>
      
      <!-- hover 提示框 -->
      <div v-if="showTooltip" class="tooltip">
        <div class="tooltip-item"><strong>名称:</strong> {{ versionInfo.name }}</div>
        <div class="tooltip-item"><strong>版本:</strong> {{ versionInfo.version }}</div>
        <div class="tooltip-item"><strong>描述:</strong> {{ versionInfo.description }}</div>
        <div v-if="versionInfo.build_date" class="tooltip-item">
          <strong>构建时间:</strong> {{ formatBuildDate(versionInfo.build_date) }}
        </div>
        <div v-if="versionInfo.git_commit" class="tooltip-item">
          <strong>Git 提交:</strong> {{ versionInfo.git_commit }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * 版本号显示组件
 * 
 * 功能：
 * 1. 从 /api/version 接口获取版本信息
 * 2. 由父级布局放置（通常顶栏 controls 内）
 * 3. hover 时显示完整的版本信息（名称、描述、构建时间等）；置于顶栏时使用向下展开的提示框
 * 4. 支持加载中、错误等状态显示
 */
import { ref, onMounted, computed } from 'vue'

// 版本信息接口定义
interface VersionInfo {
  version: string
  name: string
  description: string
  build_date?: string
  git_commit?: string
}

// 状态定义
const loading = ref(true)
const error = ref(false)
const versionInfo = ref<VersionInfo>({
  version: '',
  name: '',
  description: '',
})
const showTooltip = ref(false)

// 计算显示文本
const displayText = computed(() => {
  if (versionInfo.value.name && versionInfo.value.version) {
    return `${versionInfo.value.name} v${versionInfo.value.version}`
  }
  return versionInfo.value.version || 'v?'
})

/**
 * 格式化构建时间
 * @param dateStr 时间字符串
 * @returns 格式化后的时间字符串
 */
const formatBuildDate = (dateStr: string) => {
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return dateStr
  }
}

/**
 * 从 API 获取版本信息
 */
const fetchVersionInfo = async () => {
  try {
    loading.value = true
    error.value = false

    // 与页面同源显式拼接，避免子路径 / 代理环境下相对 URL 解析异常
    const url = `${window.location.origin}/api/version`
    const response = await fetch(url, {
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    })
    if (!response.ok) {
      const hint = await response.text().catch(() => '')
      throw new Error(`HTTP ${response.status}${hint ? `: ${hint.slice(0, 120)}` : ''}`)
    }

    versionInfo.value = await response.json()
  } catch (err) {
    console.error('获取版本信息失败:', err)
    error.value = true
  } finally {
    loading.value = false
  }
}

// 组件挂载时获取版本信息
onMounted(() => {
  fetchVersionInfo()
})
</script>

<style scoped>
.version-display {
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.65);
  display: inline-block;
  position: relative;
  z-index: 1000;
  flex-shrink: 0;
}

.loading-text,
.error-text {
  color: rgba(255, 255, 255, 0.5);
}

.version-text {
  cursor: pointer;
  transition: color 0.2s;
  user-select: none;
}

.version-text:hover {
  color: rgba(255, 255, 255, 0.95);
}

.tooltip {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 8px 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  white-space: nowrap;
  z-index: 1001;
  min-width: 200px;
}

.tooltip-item {
  margin: 4px 0;
  font-size: 12px;
  color: #333;
}

.tooltip-item strong {
  color: #666;
  margin-right: 4px;
}

/* 响应式调整 */
@media (max-width: 640px) {
  .version-display {
    font-size: 0.7rem;
  }

  .tooltip {
    min-width: 160px;
    font-size: 11px;
  }
}
</style>
