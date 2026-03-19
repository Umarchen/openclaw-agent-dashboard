# OpenClaw Agent Dashboard 版本号显示 架构设计

> **项目名称**: OpenClaw Agent Dashboard  
> **特性标识**: VERSION_DISPLAY  
> **版本**: 1.0.0  
> **编写日期**: 2026-03-19  
> **编写人员**: 架构师 (SA)  
> **项目模式**: 增量开发（Incremental Mode）

---

## 1. 设计概述

### 1.1 设计目标

在 OpenClaw Agent Dashboard 中新增版本号显示功能，使用户能够在界面上直观地查看当前插件的版本信息。具体目标包括：

1. **提供版本信息 API**：新增 `GET /api/version` 端点，返回插件版本号、名称、描述等元数据
2. **实现前端显示组件**：创建 Vue 3 组件，在 Dashboard 主界面显示版本号
3. **集成实时数据管理**：将版本信息纳入现有的实时数据管理机制
4. **确保版本一致性**：保证前端显示、API 返回、实际安装版本三者完全一致

### 1.2 设计原则

1. **最小侵入原则**：对现有代码的修改范围最小化，优先通过新增模块实现功能
2. **降级优先原则**：版本信息获取失败时必须有合理的降级方案，不影响系统核心功能
3. **单一数据源原则**：版本号仅从 `package.json` 读取，避免多源数据导致的不一致
4. **性能优先原则**：使用缓存机制，避免频繁读取文件，确保响应时间 < 50ms

### 1.3 架构分层

```
┌─────────────────────────────────────────────────────────────┐
│  表现层 (Presentation Layer)                                │
│  └── VersionDisplay.vue (版本显示组件)                      │
├─────────────────────────────────────────────────────────────┤
│  数据管理层 (Data Management Layer)                         │
│  ├── StateManager.ts (状态缓存)                             │
│  └── RealtimeDataManager.ts (实时数据管理)                  │
├─────────────────────────────────────────────────────────────┤
│  通信层 (Communication Layer)                                │
│  └── HTTP Client (调用 GET /api/version)                    │
├─────────────────────────────────────────────────────────────┤
│  API 层 (API Layer)                                          │
│  └── /api/version (版本信息端点)                            │
├─────────────────────────────────────────────────────────────┤
│  数据访问层 (Data Access Layer)                               │
│  └── version_info_reader.py (版本信息读取)                  │
├─────────────────────────────────────────────────────────────┤
│  数据源层 (Data Source Layer)                                 │
│  └── package.json (版本号单一数据源)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 模块设计

### 2.1 新增模块

#### 2.1.1 version.py `[src/backend/api/version.py]`

**职责**: 提供 `GET /api/version` 端点，返回插件版本信息。从 `package.json` 读取版本号，支持应用启动时缓存。

**导出接口**:
```python
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api", tags=["version"])

class VersionInfo(BaseModel):
    version: str  # 版本号，如 "1.0.10"
    name: str  # 插件名称
    description: str  # 插件描述
    build_date: Optional[str] = None  # 构建时间（可选）
    git_commit: Optional[str] = None  # Git 提交哈希（可选）

@router.get("/version", response_model=VersionInfo)
async def get_version_info() -> VersionInfo:
    """获取插件版本信息"""
    ...
```

**降级策略**:
- 如果 `package.json` 读取失败，返回 `version="unknown"`，其他字段填充默认值
- 记录错误日志，但不抛出异常，确保 API 始终返回 200 状态码

**需求追溯**: 
- [REQ_VERSION_DISPLAY_001]

---

#### 2.1.2 VersionInfoReader `[src/backend/data/version_info_reader.py]`

**职责**: 负责从文件系统读取版本信息，支持缓存机制。在应用启动时读取并缓存，后续请求直接返回缓存数据。

**类设计**:

```python
from pathlib import Path
from typing import Optional
import json
from datetime import datetime

class VersionInfoReader:
    """版本信息读取器，支持缓存"""
    
    def __init__(self, package_json_path: Optional[Path] = None):
        self.package_json_path = package_json_path or Path(__file__).parent.parent.parent / "package.json"
        self._cached_info: Optional[dict] = None
    
    def read_version_info(self) -> dict:
        """
        读取版本信息（带缓存）
        
        Returns:
            dict: 包含 version, name, description 等字段的字典
        """
        if self._cached_info is not None:
            return self._cached_info
        
        try:
            with open(self.package_json_path, 'r', encoding='utf-8') as f:
                package_data = json.load(f)
            
            self._cached_info = {
                "version": package_data.get("version", "unknown"),
                "name": package_data.get("name", "openclaw-agent-dashboard"),
                "description": package_data.get("description", ""),
            }
            
            # 可选：读取构建时间（从环境变量或文件）
            build_date = self._read_build_date()
            if build_date:
                self._cached_info["build_date"] = build_date
            
            # 可选：读取 Git 提交哈希
            git_commit = self._read_git_commit()
            if git_commit:
                self._cached_info["git_commit"] = git_commit
            
            return self._cached_info
            
        except Exception as e:
            # 降级：返回默认值
            self._cached_info = {
                "version": "unknown",
                "name": "openclaw-agent-dashboard",
                "description": "",
            }
            # 记录错误日志
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to read version info: {e}", exc_info=True)
            return self._cached_info
    
    def _read_build_date(self) -> Optional[str]:
        """读取构建时间（可选）"""
        import os
        return os.getenv("DASHBOARD_BUILD_DATE")
    
    def _read_git_commit(self) -> Optional[str]:
        """读取 Git 提交哈希（可选）"""
        import os
        return os.getenv("DASHBOARD_GIT_COMMIT")
```

**降级策略**:
- 文件读取失败时返回默认值，不抛出异常
- 错误日志记录，便于排查问题

**需求追溯**: 
- [REQ_VERSION_DISPLAY_001]
- [REQ_VERSION_DISPLAY_004]

---

#### 2.1.3 VersionDisplay.vue `[frontend/src/components/common/VersionDisplay.vue]`

**职责**: Vue 3 组件，在界面上显示版本号。使用 Composition API，在组件挂载时调用 API 获取版本信息，支持加载中、错误等状态。

**代码设计**:

```vue
<template>
  <div class="version-display">
    <template v-if="loading">
      <span class="loading-text">加载中...</span>
    </template>
    <template v-else-if="error">
      <span class="error-text">版本信息获取失败</span>
    </template>
    <template v-else>
      <span class="version-text" @mouseenter="showTooltip = true" @mouseleave="showTooltip = false">
        {{ displayText }}
      </span>
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
import { ref, onMounted, computed } from 'vue';

interface VersionInfo {
  version: string;
  name: string;
  description: string;
  build_date?: string;
  git_commit?: string;
}

const loading = ref(true);
const error = ref(false);
const versionInfo = ref<VersionInfo>({
  version: '',
  name: '',
  description: '',
});
const showTooltip = ref(false);

const displayText = computed(() => {
  if (versionInfo.value.name && versionInfo.value.version) {
    return `${versionInfo.value.name} v${versionInfo.value.version}`;
  }
  return versionInfo.value.version || 'v?';
});

const formatBuildDate = (dateStr: string) => {
  try {
    return new Date(dateStr).toLocaleString('zh-CN');
  } catch {
    return dateStr;
  }
};

const fetchVersionInfo = async () => {
  try {
    const response = await fetch('/api/version');
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    versionInfo.value = await response.json();
  } catch (err) {
    console.error('Failed to fetch version info:', err);
    error.value = true;
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchVersionInfo();
});
</script>

<style scoped>
.version-display {
  font-size: 12px;
  color: var(--text-color-secondary, #666);
  display: inline-block;
  position: relative;
}

.loading-text,
.error-text {
  color: var(--text-color-muted, #999);
}

.version-text {
  cursor: pointer;
  transition: color 0.2s;
}

.version-text:hover {
  color: var(--text-color-primary, #333);
}

.tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  background: var(--tooltip-bg, #fff);
  border: 1px solid var(--border-color, #ddd);
  border-radius: 4px;
  padding: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  white-space: nowrap;
  z-index: 1000;
  margin-bottom: 4px;
}

.tooltip-item {
  margin: 4px 0;
}
</style>
```

**需求追溯**: 
- [REQ_VERSION_DISPLAY_002]

---

#### 2.1.4 useVersionInfo.ts `[frontend/src/composables/useVersionInfo.ts]`（可选）

**职责**: 组合式函数，提供版本信息获取和状态管理的复用逻辑。

**代码设计**:

```typescript
import { ref, Ref } from 'vue';

export interface VersionInfo {
  version: string;
  name: string;
  description: string;
  build_date?: string;
  git_commit?: string;
}

export function useVersionInfo() {
  const loading = ref(true);
  const error = ref(false);
  const versionInfo = ref<VersionInfo>({
    version: '',
    name: '',
    description: '',
  });

  const fetchVersionInfo = async () => {
    try {
      const response = await fetch('/api/version');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      versionInfo.value = await response.json();
    } catch (err) {
      console.error('Failed to fetch version info:', err);
      error.value = true;
    } finally {
      loading.value = false;
    }
  };

  return {
    loading,
    error,
    versionInfo,
    fetchVersionInfo,
  };
}
```

**需求追溯**: 
- [REQ_VERSION_DISPLAY_002]

---

### 2.2 修改模块

#### 2.2.1 main.py `[src/backend/main.py]`

**修改内容**: 在 FastAPI 应用中注册版本信息 API 路由。

**修改前**:
```python
from fastapi import FastAPI
from src.backend.api.agents import router as agents_router
from src.backend.api.websocket import router as websocket_router
# ... 其他路由

app = FastAPI(title="OpenClaw Agent Dashboard API")

app.include_router(agents_router)
app.include_router(websocket_router)
# ... 其他路由
```

**修改后**:
```python
from fastapi import FastAPI
from src.backend.api.agents import router as agents_router
from src.backend.api.websocket import router as websocket_router
from src.backend.api.version import router as version_router  # 新增
# ... 其他路由

app = FastAPI(title="OpenClaw Agent Dashboard API")

app.include_router(agents_router)
app.include_router(websocket_router)
app.include_router(version_router)  # 新增：注册版本信息路由
# ... 其他路由
```

**数据流变化**:

```
修改前:
前端 → 其他 API 路由

修改后:
前端 → GET /api/version → version.py → version_info_reader.py → package.json
前端 → 其他 API 路由
```

**需求追溯**: [REQ_VERSION_DISPLAY_001]

---

#### 2.2.2 App.vue `[frontend/src/App.vue]`

**修改内容**: 在主应用中引入并使用 `VersionDisplay` 组件。

**修改前**:
```vue
<template>
  <div id="app">
    <Header />
    <MainContent />
    <Footer />
  </div>
</template>

<script setup lang="ts">
import Header from './components/Header.vue';
import MainContent from './components/MainContent.vue';
import Footer from './components/Footer.vue';
</script>
```

**修改后**:
```vue
<template>
  <div id="app">
    <Header />
    <MainContent />
    <Footer />
    <VersionDisplay />  <!-- 新增：版本显示组件 -->
  </div>
</template>

<script setup lang="ts">
import Header from './components/Header.vue';
import MainContent from './components/MainContent.vue';
import Footer from './components/Footer.vue';
import VersionDisplay from './components/common/VersionDisplay.vue';  // 新增
</script>
```

**数据流变化**: 无数据流变化，仅新增 UI 组件渲染

**需求追溯**: [REQ_VERSION_DISPLAY_002]

---

#### 2.2.3 RealtimeDataManager.ts `[frontend/src/managers/RealtimeDataManager.ts]`

**修改内容**: 新增版本信息管理逻辑，在应用启动时调用一次 `/api/version`。

**修改前**:
```typescript
export class RealtimeDataManager {
  private stateManager: StateManager;
  
  constructor(stateManager: StateManager) {
    this.stateManager = stateManager;
    this.initialize();
  }
  
  private async initialize() {
    // 现有的初始化逻辑
    await this.connectWebSocket();
    // ...
  }
}
```

**修改后**:
```typescript
export interface VersionInfo {
  version: string;
  name: string;
  description: string;
  build_date?: string;
  git_commit?: string;
}

export class RealtimeDataManager {
  private stateManager: StateManager;
  
  constructor(stateManager: StateManager) {
    this.stateManager = stateManager;
    this.initialize();
  }
  
  private async initialize() {
    // 现有的初始化逻辑
    await this.connectWebSocket();
    // 新增：加载版本信息
    await this.loadVersionInfo();
  }
  
  /**
   * 加载版本信息
   * @private
   */
  private async loadVersionInfo(retryCount = 0, maxRetries = 3): Promise<void> {
    try {
      const response = await fetch('/api/version');
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const versionInfo: VersionInfo = await response.json();
      
      // 缓存到 StateManager
      this.stateManager.setVersionInfo(versionInfo);
      
    } catch (err) {
      console.error('Failed to load version info:', err);
      
      // 重试机制（指数退避）
      if (retryCount < maxRetries) {
        const delay = Math.pow(2, retryCount) * 1000; // 1s, 2s, 4s
        await new Promise(resolve => setTimeout(resolve, delay));
        await this.loadVersionInfo(retryCount + 1, maxRetries);
      } else {
        // 最终失败，设置默认版本信息
        this.stateManager.setVersionInfo({
          version: 'unknown',
          name: 'openclaw-agent-dashboard',
          description: '',
        });
      }
    }
  }
  
  /**
   * 获取缓存的版本信息
   */
  public getVersionInfo(): VersionInfo | null {
    return this.stateManager.getVersionInfo();
  }
}
```

**数据流变化**:

```
修改前:
应用启动 → RealtimeDataManager.initialize() → WebSocket 连接

修改后:
应用启动 → RealtimeDataManager.initialize() → WebSocket 连接
                                        → loadVersionInfo() → GET /api/version → StateManager.setVersionInfo()
```

**需求追溯**: [REQ_VERSION_DISPLAY_003]

---

#### 2.2.4 StateManager.ts `[frontend/src/managers/StateManager.ts]`

**修改内容**: 新增版本信息的缓存字段和访问方法。

**修改前**:
```typescript
export class StateManager {
  private agentStates: Map<string, AgentState> = new Map();
  private taskHistory: TaskHistory[] = [];
  
  constructor() {
    // ...
  }
  
  // ... 现有方法
}
```

**修改后**:
```typescript
export interface VersionInfo {
  version: string;
  name: string;
  description: string;
  build_date?: string;
  git_commit?: string;
}

export class StateManager {
  private agentStates: Map<string, AgentState> = new Map();
  private taskHistory: TaskHistory[] = [];
  private versionInfo: VersionInfo | null = null;  // 新增：版本信息缓存
  
  constructor() {
    // ...
  }
  
  /**
   * 设置版本信息
   */
  public setVersionInfo(versionInfo: VersionInfo): void {
    this.versionInfo = versionInfo;
    // 可选：触发版本信息更新事件
    this.eventDispatcher.dispatch('version-info-updated', versionInfo);
  }
  
  /**
   * 获取版本信息
   */
  public getVersionInfo(): VersionInfo | null {
    return this.versionInfo;
  }
  
  // ... 现有方法
}
```

**数据流变化**: 无数据流变化，仅新增状态字段和访问方法

**需求追溯**: [REQ_VERSION_DISPLAY_003]

---

#### 2.2.5 build-plugin.js `[scripts/build-plugin.js]`

**修改内容**: 确保构建脚本在构建时正确处理版本信息。

**修改前**:
```javascript
// 现有构建逻辑
async function build() {
  // 构建前端
  await exec('npm run build');
  
  // 复制后端文件
  await copyFiles('src/backend/', 'plugin/dashboard/');
  
  // 复制前端构建产物
  await copyFiles('frontend/dist/', 'plugin/frontend-dist/');
}
```

**修改后**:
```javascript
// 可选：在构建时注入构建时间
async function build() {
  // 设置构建时间环境变量（可选）
  const buildDate = new Date().toISOString();
  process.env.DASHBOARD_BUILD_DATE = buildDate;
  
  // 构建前端
  await exec('npm run build');
  
  // 复制后端文件
  await copyFiles('src/backend/', 'plugin/dashboard/');
  
  // 复制前端构建产物
  await copyFiles('frontend/dist/', 'plugin/frontend-dist/');
  
  // 验证版本信息是否正确（可选）
  const packageJson = JSON.parse(await fs.readFile('package.json', 'utf-8'));
  console.log(`Building version: ${packageJson.version}`);
}
```

**需求追溯**: [REQ_VERSION_DISPLAY_004]

---

## 3. 类设计

### 3.1 新增类清单

| 类名 | 所在模块 | 职责 | 依赖 |
|-----|---------|------|------|
| VersionInfoReader | src/backend/data/version_info_reader.py | 从 package.json 读取版本信息，支持缓存 | pathlib, json, logging |
| VersionInfo | src/backend/api/version.py (Pydantic Model) | 版本信息数据模型 | pydantic |
| VersionDisplay.vue | frontend/src/components/common/VersionDisplay.vue | 前端版本显示组件 | Vue 3 Composition API |
| useVersionInfo | frontend/src/composables/useVersionInfo.ts (可选) | 版本信息组合式函数 | Vue 3, TypeScript |

### 3.2 修改类清单

| 类名 | 所在模块 | 修改内容 | 影响程度 |
|-----|---------|---------|---------|
| FastAPI App | src/backend/main.py | 新增 version_router 注册 | 低（仅新增一行） |
| App.vue | frontend/src/App.vue | 新增 VersionDisplay 组件引入和使用 | 低（仅新增导入和标签） |
| RealtimeDataManager | frontend/src/managers/RealtimeDataManager.ts | 新增 loadVersionInfo() 方法和 getVersionInfo() 方法 | 中（新增方法） |
| StateManager | frontend/src/managers/StateManager.ts | 新增 versionInfo 字段和 setVersionInfo()/getVersionInfo() 方法 | 低（新增字段和方法） |

### 3.3 类关系图

```
┌─────────────────────────────────────────────────────────────┐
│                         前端层                                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐     使用     ┌──────────────────────┐  │
│  │ VersionDisplay  │─────────────▶│  useVersionInfo      │  │
│  │    .vue         │              │   (可选)             │  │
│  └─────────────────┘              └──────────────────────┘  │
│         │                                                 │
│         │ 调用                                            │
│         ▼                                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │             RealtimeDataManager                      │  │
│  │  + loadVersionInfo()                                │  │
│  │  + getVersionInfo()                                 │  │
│  └───────────────┬─────────────────────────────────────┘  │
│                  │ 管理                                    │
│                  ▼                                         │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                StateManager                          │  │
│  │  - versionInfo: VersionInfo | null                   │  │
│  │  + setVersionInfo(versionInfo)                       │  │
│  │  + getVersionInfo(): VersionInfo | null              │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP GET
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         后端层                                │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐     调用     ┌──────────────────────┐  │
│  │  FastAPI App    │─────────────▶│ version.py (router)   │  │
│  │  (main.py)      │             └──────────┬───────────┘  │
│  └─────────────────┘                        │              │
│                                            │ 使用           │
│                                            ▼               │
│  ┌─────────────────────────────────────────────────────┐  │
│  │            VersionInfoReader                         │  │
│  │  - _cached_info: dict | null                        │  │
│  │  + readVersionInfo(): dict                          │  │
│  │  + _readBuildDate(): str | null                     │  │
│  │  + _readGitCommit(): str | null                    │  │
│  └───────────────────┬─────────────────────────────────┘  │
│                      │ 读取                                 │
│                      ▼                                      │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              package.json                            │  │
│  │  - version: "1.0.10"                                │  │
│  │  - name: "openclaw-agent-dashboard"                 │  │
│  │  - description: "..."                               │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 数据流设计

### 4.1 版本信息加载流程

```
应用启动
   │
   ├─▶ RealtimeDataManager.initialize()
   │      │
   │      ├─▶ connectWebSocket() (现有逻辑)
   │      │
   │      └─▶ loadVersionInfo()
   │             │
   │             ├─▶ fetch('/api/version')
   │             │      │
   │             │      ▼
   │             │   FastAPI: GET /api/version
   │             │      │
   │             │      ├─▶ version_info_reader.readVersionInfo()
   │             │      │      │
   │             │      │      ├─▶ [首次] 读取 package.json
   │             │      │      │      │
   │             │      │      │      ├─▶ 解析 JSON
   │             │      │      │      │
   │             │      │      │      ├─▶ 读取环境变量（可选）
   │             │      │      │      │
   │             │      │      │      └─▶ 缓存到 _cached_info
   │             │      │      │
   │             │      │      └─▶ [后续] 返回缓存
   │             │      │
   │             │      └─▶ 返回 VersionInfo JSON
   │             │
   │             └─▶ StateManager.setVersionInfo(versionInfo)
   │                    │
   │                    └─▶ 触发 'version-info-updated' 事件
   │
   └─▶ App.vue 渲染
          │
          └─▶ VersionDisplay 组件挂载
                 │
                 └─▶ onMounted() → fetchVersionInfo()
                        │
                        └─▶ 从 StateManager 获取版本信息
                               │
                               └─▶ 显示版本号
```

### 4.2 降级流程（API 失败）

```
loadVersionInfo()
   │
   ├─▶ fetch('/api/version') 失败
   │      │
   │      ├─▶ 捕获异常
   │      │
   │      ├─▶ 检查重试次数 < maxRetries (3次)
   │      │      │
   │      │      ├─▶ 是：延迟后重试（指数退避：1s, 2s, 4s）
   │      │      │
   │      │      └─▶ 否：设置默认版本信息
   │      │             │
   │      │             └─▶ StateManager.setVersionInfo({
   │      │                   version: "unknown",
   │      │                   name: "openclaw-agent-dashboard",
   │      │                   description: ""
   │      │                 })
   │      │
   │      └─▶ 记录错误日志
   │
   └─▶ VersionDisplay 组件显示
          │
          └─▶ 显示 "v?" 或 "openclaw-agent-dashboard vunknown"
```

### 4.3 降级流程（文件读取失败）

```
version_info_reader.readVersionInfo()
   │
   ├─▶ 尝试读取 package.json
   │      │
   │      ├─▶ 失败（文件不存在、权限错误等）
   │      │      │
   │      │      ├─▶ 捕获异常
   │      │      │
   │      │      ├─▶ 返回默认值
   │      │      │      │
   │      │      │      └─▶ {
   │      │      │            version: "unknown",
   │      │      │            name: "openclaw-agent-dashboard",
   │      │      │            description: ""
   │      │      │          }
   │      │      │
   │      │      └─▶ 记录错误日志
   │      │
   │      └─▶ API 返回 200 OK（降级响应）
   │
   └─▶ 前端正常显示 "unknown" 版本号
```

---

## 5. 配置设计

### 5.1 环境变量配置

| 环境变量 | 类型 | 默认值 | 说明 | 对应需求 |
|---------|------|--------|------|---------|
| `DASHBOARD_VERSION` | String | 从 package.json 读取 | 覆盖版本号（用于开发环境） | [REQ_VERSION_DISPLAY_004] |
| `DASHBOARD_BUILD_DATE` | String | 构建时自动生成 | 构建时间戳（ISO 8601 格式） | [REQ_VERSION_DISPLAY_004] |
| `DASHBOARD_GIT_COMMIT` | String | 从 git 读取 | Git 提交哈希（短格式，如 abc123d） | [REQ_VERSION_DISPLAY_004] |

### 5.2 配置文件示例

**package.json**（现有文件，无需修改）:
```json
{
  "name": "openclaw-agent-dashboard",
  "version": "1.0.10",
  "description": "多 Agent 可视化看板 - 状态、任务、API、工作流、协作流程",
  ...
}
```

---

## 6. 降级策略

### 6.1 降级场景

| 场景 | 触发条件 | 降级行为 | 影响范围 |
|-----|---------|---------|---------|
| 文件读取失败 | package.json 文件不存在、权限不足、格式错误 | 返回 `version="unknown"`，记录错误日志 | 仅影响版本信息显示 |
| API 调用失败 | 网络错误、后端服务不可用 | 前端重试 3 次后显示 "版本信息获取失败" | 仅影响版本信息显示 |
| JSON 解析失败 | package.json 格式错误 | 返回 `version="unknown"`，记录错误日志 | 仅影响版本信息显示 |
| 超时 | 文件读取或 API 响应时间超过阈值 | 返回缓存数据（如果有）或默认值 | 仅影响版本信息显示 |

### 6.2 降级实现

**后端降级** (src/backend/data/version_info_reader.py):
```python
try:
    with open(self.package_json_path, 'r', encoding='utf-8') as f:
        package_data = json.load(f)
    # 正常处理
except Exception as e:
    # 降级：返回默认值
    logger.error(f"Failed to read version info: {e}", exc_info=True)
    return {
        "version": "unknown",
        "name": "openclaw-agent-dashboard",
        "description": "",
    }
```

**前端降级** (frontend/src/managers/RealtimeDataManager.ts):
```typescript
private async loadVersionInfo(retryCount = 0, maxRetries = 3): Promise<void> {
  try {
    const response = await fetch('/api/version');
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const versionInfo: VersionInfo = await response.json();
    this.stateManager.setVersionInfo(versionInfo);
  } catch (err) {
    console.error('Failed to load version info:', err);
    
    if (retryCount < maxRetries) {
      // 指数退避重试
      const delay = Math.pow(2, retryCount) * 1000;
      await new Promise(resolve => setTimeout(resolve, delay));
      await this.loadVersionInfo(retryCount + 1, maxRetries);
    } else {
      // 最终降级：设置默认值
      this.stateManager.setVersionInfo({
        version: 'unknown',
        name: 'openclaw-agent-dashboard',
        description: '',
      });
    }
  }
}
```

### 6.3 降级告警

- **日志级别**: ERROR（当降级发生时记录错误日志）
- **告警内容**: 包含降级原因（文件路径、错误信息）、时间戳
- **告警渠道**: 后端日志（可接入日志聚合平台如 ELK）
- **告警频率**: 避免重复告警，可使用去重机制

---

## 7. API 设计

### 7.1 新增 API 清单

| 方法 | 路径 | 描述 | 请求体 | 响应体 | 需求追溯 |
|-----|------|------|--------|--------|---------|
| GET | /api/version | 获取插件版本信息 | 无 | VersionInfo JSON | [REQ_VERSION_DISPLAY_001] |

### 7.2 API 详细设计

#### 7.2.1 GET /api/version

**接口描述**: 获取 OpenClaw Agent Dashboard 插件的版本信息，包括版本号、名称、描述等元数据。

**请求参数**: 无

**请求示例**:
```http
GET /api/version HTTP/1.1
Host: localhost:8000
Accept: application/json
```

**响应示例**（成功）:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "version": "1.0.10",
  "name": "openclaw-agent-dashboard",
  "description": "多 Agent 可视化看板 - 状态、任务、API、工作流、协作流程",
  "build_date": "2026-03-19T12:34:56Z",
  "git_commit": "abc123def456"
}
```

**响应示例**（降级）:
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "version": "unknown",
  "name": "openclaw-agent-dashboard",
  "description": ""
}
```

**响应字段说明**:

| 字段 | 类型 | 必填 | 说明 |
|-----|------|------|------|
| version | string | 是 | 版本号，如 "1.0.10" |
| name | string | 是 | 插件名称 |
| description | string | 是 | 插件描述 |
| build_date | string | 否 | 构建时间（ISO 8601 格式） |
| git_commit | string | 否 | Git 提交哈希（短格式） |

**错误处理**: 本接口始终返回 200 状态码，文件读取失败时返回降级数据（`version="unknown"`），错误信息通过后端日志记录。

**性能指标**:
- 首次请求（无缓存）: < 100ms（文件读取 + JSON 解析）
- 后续请求（有缓存）: < 50ms（内存读取）

**需求追溯**: [REQ_VERSION_DISPLAY_001]

---

## 8. 需求追溯表

### 8.1 需求 → 设计映射

| 需求 ID | 需求描述 | 设计章节 | 实现模块 |
|---------|---------|---------|---------|
| [REQ_VERSION_DISPLAY_001] | 后端版本信息 API | 2.1.1, 2.1.2, 2.2.1, 7.2.1 | src/backend/api/version.py, src/backend/data/version_info_reader.py |
| [REQ_VERSION_DISPLAY_002] | 前端版本信息组件 | 2.1.3, 2.1.4, 2.2.2 | frontend/src/components/common/VersionDisplay.vue, frontend/src/composables/useVersionInfo.ts |
| [REQ_VERSION_DISPLAY_003] | 实时数据管理器集成 | 2.2.3, 2.2.4 | frontend/src/managers/RealtimeDataManager.ts, frontend/src/managers/StateManager.ts |
| [REQ_VERSION_DISPLAY_004] | 版本信息配置 | 2.1.2, 2.2.5, 5.1 | src/backend/data/version_info_reader.py, scripts/build-plugin.js, 环境变量 |

### 8.2 验收条件追溯

| 验收条件 | 对应设计 | 验证方法 |
|---------|---------|---------|
| AC-001-1: GET /api/version 返回 200 | 7.2.1 | 使用 curl 访问 API，检查状态码 |
| AC-001-2: version 字段与 package.json 一致 | 2.1.2, 7.2.1 | 对比 API 返回值与 package.json |
| AC-001-3: name 字段值为 "openclaw-agent-dashboard" | 7.2.1 | 检查 API 响应的 name 字段 |
| AC-001-4: 文件读取失败时返回 "unknown" | 6.2 | 删除 package.json，检查 API 响应 |
| AC-002-1: 组件成功渲染并显示版本号 | 2.1.3 | 在浏览器中打开 Dashboard，检查 UI |
| AC-002-2: 版本号与 package.json 一致 | 2.1.3 | 对比前端显示与 package.json |
| AC-002-3: 加载中状态显示 "加载中..." | 2.1.3 | 清除缓存，刷新页面，检查 UI |
| AC-002-4: API 失败时显示友好提示 | 2.1.3, 6.2 | 模拟 API 失败，检查错误提示 |
| AC-002-5: hover 显示完整信息 | 2.1.3 | 鼠标悬停版本号，检查 Tooltip |
| AC-003-1: 版本信息在应用启动时自动加载 | 2.2.3, 4.1 | 检查应用启动日志，确认调用时机 |
| AC-003-2: 状态管理器提供全局访问接口 | 2.2.4 | 测试 StateManager.getVersionInfo() |
| AC-003-3: 加载失败时支持重试机制 | 2.2.3, 6.2 | 模拟 API 失败，检查重试逻辑 |
| AC-004-1: 构建后插件包包含正确版本信息 | 2.2.5 | 构建插件，检查打包文件 |
| AC-004-2: 后端 API 能正确读取版本信息 | 2.1.2 | 运行后端服务，访问 API |
| AC-004-3: 环境变量覆盖功能正常 | 2.1.2, 5.1 | 设置环境变量，验证覆盖效果 |

---

## 9. 设计评审点

### 9.1 关键技术决策

| 决策点 | 选择 | 理由 | 风险 |
|-------|------|------|------|
| 版本号数据源 | 仅从 package.json 读取 | 单一数据源避免不一致，符合 npm 生态规范 | 需确保 package.json 版本号同步更新 |
| 缓存策略 | 应用启动时读取并缓存 | 减少文件 I/O，提升响应性能（< 50ms） | 升级后需重启应用才能看到新版本号（可接受） |
| API 设计 | GET /api/version，始终返回 200 | 简化前端错误处理，降级策略在后端实现 | 需通过日志记录降级事件 |
| 前端组件位置 | 放在 App.vue 全局显示 | 一次性集成，所有页面都能看到版本号 | 可能占用屏幕空间（可通过样式调整） |
| 重试机制 | 指数退避，最多 3 次 | 平衡可靠性和用户体验，避免无限重试 | 网络不稳定时可能导致较长的加载时间 |
| 降级显示 | 显示 "unknown" 或 "v?" | 避免空白显示，给用户明确反馈 | 可能掩盖真实问题（需配合日志） |

### 9.2 风险点

| 风险 | 影响 | 缓解措施 | 优先级 |
|-----|------|---------|--------|
| package.json 版本号未同步更新 | 前端显示的版本号与实际安装版本不一致 | 在发布流程中增加版本号检查步骤 | 高 |
| 版本文件读取失败率高 | 频繁触发降级，影响用户体验 | 在 CI/CD 中验证文件完整性，添加健康检查 | 中 |
| 缓存导致升级后版本号不更新 | 用户升级后仍显示旧版本号 | 在文档中说明需重启应用，或提供刷新按钮 | 低 |
| 前端组件渲染错误 | 导致整个 Dashboard 页面崩溃 | 使用 Vue 错误边界捕获异常，隔离组件错误 | 中 |
| 环境变量被滥用 | 开发环境覆盖版本号后误发布到生产环境 | 在构建脚本中检查环境，生产环境禁止覆盖 | 中 |

### 9.3 待确认事项

| 事项 | 选项 | 建议 | 状态 |
|-----|------|------|------|
| 版本信息显示位置 | Footer / 右上角工具栏 / 其他 | 建议 Footer，不占用主要操作区域 | 待确认 |
| 是否支持手动刷新版本号 | 是 / 否 | 建议不实现（需重启应用即可） | 待确认 |
| 是否显示 Git 提交哈希 | 是 / 否 | 建议显示，方便问题排查 | 待确认 |
| 降级时是否显示详细错误信息 | 是 / 否 | 建议否，仅显示 "unknown"，错误信息在日志中 | 待确认 |

---

## 10. 依赖变更

### 10.1 新增依赖

**后端依赖**: 无新增依赖。仅使用 Python 标准库（`pathlib`、`json`、`logging`、`os`）和现有依赖（`fastapi`、`pydantic`）。

**前端依赖**: 无新增 npm 包。仅使用 Vue 3 和 TypeScript 标准特性。

### 10.2 版本兼容性

| 依赖 | 版本要求 | 兼容性说明 |
|-----|---------|-----------|
| Python | ≥ 3.8 | 使用标准库特性，兼容性良好 |
| FastAPI | ≥ 0.109.0 | 使用现有版本，无变更 |
| Pydantic | ≥ 2.5.0 | 使用现有版本，无变更 |
| Vue | 3.4.0+ | 使用现有版本，无变更 |
| TypeScript | 5.3+ | 使用现有版本，无变更 |

---

## 11. 实施建议

### 11.1 实施顺序

**阶段 1: 后端 API 实现（P0）**
1. 创建 `src/backend/data/version_info_reader.py`，实现版本信息读取和缓存
2. 创建 `src/backend/api/version.py`，实现 GET /api/version 端点
3. 修改 `src/backend/main.py`，注册 version_router
4. 单元测试：验证 API 返回正确的版本信息

**阶段 2: 前端组件实现（P0）**
1. 创建 `frontend/src/components/common/VersionDisplay.vue`
2. 修改 `frontend/src/App.vue`，集成版本显示组件
3. 本地测试：验证组件渲染和版本号显示

**阶段 3: 实时数据管理集成（P1）**
1. 修改 `frontend/src/managers/StateManager.ts`，新增版本信息缓存
2. 修改 `frontend/src/managers/RealtimeDataManager.ts`，实现自动加载和重试机制
3. 集成测试：验证应用启动时自动加载版本信息

**阶段 4: 配置和构建优化（P2）**
1. 修改 `scripts/build-plugin.js`，确保版本信息正确注入（可选）
2. 测试环境变量覆盖功能（可选）
3. 端到端测试：验证从构建到部署的完整流程

### 11.2 测试策略

| 测试类型 | 测试内容 | 工具 |
|---------|---------|------|
| 单元测试 | VersionInfoReader 读取逻辑、缓存机制、降级策略 | pytest |
| 单元测试 | VersionDisplay 组件渲染、状态切换、交互逻辑 | Vue Test Utils |
| 集成测试 | API 端点响应、数据流完整链路 | pytest + httpx |
| 手动测试 | 浏览器中验证 UI 显示、hover 效果 | Chrome DevTools |
| 性能测试 | API 响应时间（首次/缓存）、内存占用 | locust / Apache Bench |
| 兼容性测试 | Chrome、Firefox、Safari 下的组件渲染 | BrowserStack（可选） |

---

## 12. 附录

### 12.1 文件变更清单

| 变更类型 | 文件路径 | 说明 |
|---------|---------|------|
| **新增** | src/backend/data/version_info_reader.py | 版本信息读取器（支持缓存） |
| **新增** | src/backend/api/version.py | 版本信息 API 路由 |
| **新增** | frontend/src/components/common/VersionDisplay.vue | 版本显示 Vue 组件 |
| **新增** | frontend/src/composables/useVersionInfo.ts | 版本信息组合式函数（可选） |
| **修改** | src/backend/main.py | 注册 version_router（新增一行） |
| **修改** | frontend/src/App.vue | 集成 VersionDisplay 组件（新增导入和标签） |
| **修改** | frontend/src/managers/RealtimeDataManager.ts | 新增 loadVersionInfo() 方法 |
| **修改** | frontend/src/managers/StateManager.ts | 新增版本信息缓存字段和方法 |
| **修改** | scripts/build-plugin.js | 确保版本信息正确注入（可选） |

### 12.2 架构图

**系统整体架构**（包含版本显示功能）:

```
┌─────────────────────────────────────────────────────────────┐
│                    用户浏览器                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  App.vue                                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │  │
│  │  │ Header       │  │ MainContent  │  │ Footer       │  │  │
│  │  └──────────────┘  └──────────────┘  └─────────────┘  │  │
│  │  ┌─────────────────────────────────────────────────────┐│  │
│  │  │ VersionDisplay: "openclaw-agent-dashboard v1.0.10" ││  │
│  │  └─────────────────────────────────────────────────────┘│  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  StateManager (状态缓存)                                 │  │
│  │  - versionInfo: { version, name, description, ... }    │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  RealtimeDataManager (实时数据管理)                     │  │
│  │  - loadVersionInfo(): 调用 /api/version                │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP GET /api/version
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI 后端服务                            │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  main.py (应用入口)                                     │  │
│  │  - app.include_router(version_router)                   │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  version.py (API 路由)                                  │  │
│  │  - @router.get("/version")                              │  │
│  │  - 返回 VersionInfo 响应模型                            │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  version_info_reader.py (数据读取)                     │  │
│  │  - _cached_info: 缓存的版本信息                        │  │
│  │  - readVersionInfo(): 读取 package.json                 │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ 读取文件
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    文件系统                                  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  package.json                                           │  │
│  │  {                                                     │  │
│  │    "name": "openclaw-agent-dashboard",                 │  │
│  │    "version": "1.0.10",                                │  │
│  │    "description": "..."                                │  │
│  │  }                                                     │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

**文档版本**: 1.0.0  
**最后更新**: 2026-03-19  
**审核状态**: 待审核
