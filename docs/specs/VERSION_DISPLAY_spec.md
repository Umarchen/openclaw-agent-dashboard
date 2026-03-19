# 版本号显示需求规格说明书

> **项目名称**: OpenClaw Agent Dashboard  
> **特性标识**: VERSION_DISPLAY  
> **版本**: 1.0.0  
> **编写日期**: 2026-03-19  
> **编写人员**: 业务分析师 (BA)  
> **项目模式**: 增量开发（Incremental Mode）

---

## 1. 需求背景与目标

### 1.1 背景

OpenClaw Agent Dashboard 当前已经部署到生产环境，用户在使用过程中反馈以下问题：

1. **版本信息缺失**：用户无法直观地看到当前 Dashboard 插件的版本号，无法确认是否为最新版本
2. **问题排查困难**：当用户反馈问题时，无法快速提供准确的版本信息给技术支持团队
3. **升级验证不便**：用户升级后无法确认是否成功升级到目标版本

根据摸排报告（`legacy_code_anatomy.md`），Dashboard 项目已有以下基础：
- **前端技术栈**：Vue 3 + TypeScript + Vite 5，组件化架构完善
- **后端技术栈**：FastAPI + Python，已有 API 状态监控功能
- **版本管理**：`package.json` 中已维护版本号（当前为 1.0.10）
- **插件元数据**：`plugin/openclaw.plugin.json` 包含插件版本信息

### 1.2 目标

在 Dashboard 界面显示插件版本号，实现以下目标：

1. **用户体验提升**：用户可在界面上直观地看到当前版本号
2. **问题诊断优化**：用户反馈问题时可快速提供版本信息
3. **升级验证便利**：升级后可立即确认版本号变化
4. **一致性保证**：前端显示的版本号与实际安装版本保持一致

---

## 2. 功能需求列表

### 2.1 核心功能需求

#### [REQ_VERSION_DISPLAY_001] 后端版本信息 API

**需求描述**: 新增 API 端点，返回 Dashboard 插件的版本信息和元数据。

**详细规格**:

1. **新增 API 端点**: `GET /api/version`
   - 读取 `plugin/openclaw.plugin.json` 和 `package.json` 中的版本信息
   - 返回包含版本号、名称、描述等信息的 JSON 响应
   - 支持在应用启动时缓存版本信息，避免每次请求都读取文件

2. **响应数据结构**:
   ```json
   {
     "version": "1.0.10",
     "name": "openclaw-agent-dashboard",
     "description": "多 Agent 可视化看板 - 状态、任务、API、工作流、协作流程",
     "buildDate": "2026-03-19T12:34:56Z",  // 可选：构建时间
     "gitCommit": "abc123def456"  // 可选：Git 提交哈希
   }
   ```

3. **错误处理**:
   - 如果读取文件失败，返回默认版本号（如 "unknown"）
   - 记录错误日志，但不影响应用启动

**技术实现建议**:
- 在 `src/backend/api/` 下新增 `version.py` 模块
- 在 `src/backend/main.py` 中注册路由
- 使用 `pathlib.Path` 读取 JSON 文件
- 可选：在应用启动时读取并缓存，避免每次请求都读取文件

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-001-1 | 访问 `GET /api/version` 返回 200 状态码 | P0 |
| AC-001-2 | 响应中包含 `version` 字段，值与 `package.json` 中的版本一致 | P0 |
| AC-001-3 | 响应中包含 `name` 字段，值为 "openclaw-agent-dashboard" | P1 |
| AC-001-4 | 文件读取失败时返回默认版本号 "unknown" 而不是 500 错误 | P0 |

---

#### [REQ_VERSION_DISPLAY_002] 前端版本信息组件

**需求描述**: 新增 Vue 组件，在 Dashboard 界面显示版本号。

**详细规格**:

1. **组件位置与显示**:
   - **位置**: 在主界面底部（Footer）或右上角工具栏显示
   - **样式**: 小字体（12px）、浅色文字、hover 时显示完整信息
   - **内容**: `v1.0.10` 或 `OpenClaw Dashboard v1.0.10`

2. **组件设计**:
   - 创建新组件 `frontend/src/components/common/VersionDisplay.vue`
   - 使用 Composition API（`<script setup lang="ts">`）
   - 在组件挂载时调用 `/api/version` 获取版本信息
   - 加载中状态：显示 "加载中..." 或骨架屏
   - 错误状态：显示 "版本信息获取失败"

3. **集成位置**:
   - 在 `frontend/src/App.vue` 中引入并使用该组件
   - 建议放在主布局的底部或右上角

4. **样式规范**:
   - 字体大小：12px
   - 颜色：使用现有的 CSS 变量（如 `--text-color-secondary`）
   - 对齐方式：右对齐或居中对齐（根据布局决定）
   - hover 效果：显示完整的版本信息和描述

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-002-1 | 组件成功渲染并显示版本号 | P0 |
| AC-002-2 | 版本号与 `package.json` 中的版本一致 | P0 |
| AC-002-3 | 加载中状态显示 "加载中..." 或骨架屏 | P1 |
| AC-002-4 | API 调用失败时显示友好的错误提示 | P1 |
| AC-002-5 | hover 时显示完整的版本信息（名称、描述） | P2 |

---

#### [REQ_VERSION_DISPLAY_003] 实时数据管理器集成

**需求描述**: 将版本信息 API 集成到现有的实时数据管理器中，支持 WebSocket 推送或定期刷新。

**详细规格**:

1. **集成到 RealtimeDataManager**:
   - 在 `frontend/src/managers/RealtimeDataManager.ts` 中新增版本信息管理逻辑
   - 应用启动时调用一次 `/api/version`
   - 可选：支持 WebSocket 推送版本变更通知（如果实现了热更新机制）

2. **状态管理**:
   - 在 `frontend/src/managers/StateManager.ts` 中新增版本信息的状态缓存
   - 提供全局访问版本信息的接口

3. **错误处理与重试**:
   - 如果首次加载失败，支持重试机制（最多 3 次）
   - 使用指数退避策略进行重试

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-003-1 | 版本信息在应用启动时自动加载 | P0 |
| AC-003-2 | 状态管理器提供全局访问版本信息的接口 | P1 |
| AC-003-3 | 加载失败时支持重试机制 | P2 |

---

### 2.2 配置需求

#### [REQ_VERSION_DISPLAY_004] 版本信息配置

**需求描述**: 确保版本信息在构建和部署时正确注入到应用中。

**详细规格**:

1. **构建脚本修改**:
   - 在 `scripts/build-plugin.js` 中，构建时将 `package.json` 的版本号写入到可访问的位置
   - 确保后端可以读取到正确的版本信息

2. **环境变量支持**（可选）:
   - 支持通过环境变量 `DASHBOARD_VERSION` 覆盖版本号（用于开发环境）
   - 支持通过环境变量 `DASHBOARD_BUILD_DATE` 注入构建时间

**新增配置项**:

| 配置项 | 环境变量 | 类型 | 默认值 | 说明 |
|-------|---------|------|--------|------|
| 版本号 | `DASHBOARD_VERSION` | String | 从 package.json 读取 | 覆盖版本号（开发环境） |
| 构建时间 | `DASHBOARD_BUILD_DATE` | String | 构建时自动生成 | 构建时间戳 |
| Git 提交哈希 | `DASHBOARD_GIT_COMMIT` | String | 从 git 读取 | Git 提交哈希（可选） |

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-004-1 | 构建后的插件包中包含正确的版本信息 | P0 |
| AC-004-2 | 后端 API 能正确读取到版本信息 | P0 |
| AC-004-3 | 环境变量覆盖版本号功能正常工作（如果实现） | P2 |

---

## 3. 非功能需求

### 3.1 性能指标

| 指标 | 目标值 | 测量方法 |
|-----|--------|---------|
| `/api/version` 响应时间 | < 50ms（缓存后） | 浏览器 Network 面板 |
| 版本信息加载时间 | < 100ms（应用启动时） | 前端性能监控 |
| 版本信息显示延迟 | < 200ms（从启动到显示） | 用户体验测试 |

### 3.2 可靠性指标

| 指标 | 目标值 | 说明 |
|-----|--------|------|
| API 可用性 | 99.9% | 版本信息 API 不应影响整体应用可用性 |
| 降级策略 | 必须实现 | API 失败时显示 "unknown" 或 "v?" 而不是崩溃 |

### 3.3 安全性需求

| 需求 | 说明 |
|-----|------|
| 无敏感信息泄露 | 确保版本信息中不包含敏感信息（如密钥、内部路径） |
| CORS 配置 | 版本信息 API 应遵循现有的 CORS 策略 |

---

## 4. 影响范围分析

### 4.1 新增模块

| 模块路径 | 职责 | 说明 |
|---------|------|------|
| `src/backend/api/version.py` | 版本信息 API | 新增 API 路由模块 |
| `frontend/src/components/common/VersionDisplay.vue` | 版本显示组件 | 新增 Vue 组件 |
| `frontend/src/composables/useVersionInfo.ts` | 版本信息钩子 | 可选：组合式函数 |

### 4.2 修改模块

| 模块路径 | 修改内容 | 影响程度 |
|---------|---------|---------|
| `src/backend/main.py` | 注册版本信息 API 路由 | 低（仅新增一行导入和注册） |
| `frontend/src/App.vue` | 集成版本显示组件 | 低（仅新增组件标签） |
| `frontend/src/managers/RealtimeDataManager.ts` | 新增版本信息管理逻辑 | 中（新增方法） |
| `frontend/src/managers/StateManager.ts` | 新增版本信息状态缓存 | 低（新增字段） |
| `scripts/build-plugin.js` | 确保版本信息正确注入 | 低（可能无需修改） |

### 4.3 API 变更

| 变更类型 | API | 说明 |
|---------|-----|------|
| 新增 | `GET /api/version` | 返回插件版本信息 |

### 4.4 数据库变更

无数据库变更。

---

## 5. 兼容性分析

### 5.1 向后兼容

- **完全兼容**：新增功能不影响现有功能和 API
- **可选功能**：如果版本信息获取失败，不影响其他功能的正常使用
- **降级显示**：API 失败时显示 "unknown" 而不是报错

### 5.2 版本依赖

- **前端依赖**：无新增第三方依赖
- **后端依赖**：无新增 Python 依赖（使用现有的 FastAPI、Pydantic）
- **OpenClaw 依赖**：无额外依赖，兼容 OpenClaw 现有版本

### 5.3 升级路径

- **升级影响**：升级后版本号自动更新为新版本号
- **配置迁移**：无需配置迁移
- **数据迁移**：无需数据迁移

---

## 6. 验收标准

### 6.1 功能验收

| 编号 | 验收项 | 验收方法 | 责任方 |
|-----|--------|---------|--------|
| FAT-001 | 后端 API 正常返回版本信息 | 使用 curl 或 Postman 访问 `/api/version` | 后端开发 |
| FAT-002 | 前端组件正常显示版本号 | 在浏览器中打开 Dashboard，检查版本号显示 | 前端开发 |
| FAT-003 | 版本号与 package.json 一致 | 对比前端显示、API 返回、package.json 三者版本号 | QA |
| FAT-004 | API 失败时降级显示 | 模拟 API 失败场景（如删除版本文件），检查前端显示 | QA |
| FAT-005 | 加载状态正确显示 | 清除浏览器缓存，刷新页面，检查加载中状态 | QA |

### 6.2 性能验收

| 编号 | 验收项 | 目标 | 验收方法 |
|-----|--------|-----|---------|
| PAT-001 | API 响应时间 | < 50ms | 浏览器 Network 面板测量 |
| PAT-002 | 版本信息加载时间 | < 100ms | 前端性能监控工具 |
| PAT-003 | 应用启动延迟 | < 200ms | 对比添加版本显示前后的启动时间 |

### 6.3 兼容性验收

| 编号 | 验收项 | 验收方法 |
|-----|--------|---------|
| CAT-001 | Chrome 浏览器兼容 | 在 Chrome 最新版本中测试 |
| CAT-002 | Firefox 浏览器兼容 | 在 Firefox 最新版本中测试 |
| CAT-003 | Safari 浏览器兼容 | 在 Safari 最新版本中测试（如有 macOS 环境） |
| CAT-004 | 移动端浏览器兼容 | 在移动端 Chrome/Safari 中测试响应式布局 |

---

## 7. 依赖关系

### 7.1 需求依赖图

```
[REQ_VERSION_DISPLAY_001] 后端版本信息 API
         ↓
[REQ_VERSION_DISPLAY_002] 前端版本信息组件
         ↓
[REQ_VERSION_DISPLAY_003] 实时数据管理器集成
         
[REQ_VERSION_DISPLAY_004] 版本信息配置（可并行）
```

### 7.2 实施优先级

| 优先级 | 需求 ID | 说明 |
|-------|---------|------|
| P0 | [REQ_VERSION_DISPLAY_001] | 必须先实现后端 API |
| P0 | [REQ_VERSION_DISPLAY_002] | 前端组件依赖后端 API |
| P1 | [REQ_VERSION_DISPLAY_003] | 可后期优化，提升代码组织性 |
| P2 | [REQ_VERSION_DISPLAY_004] | 可选优化，支持环境变量覆盖 |

---

## 8. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 版本文件读取失败 | 低 | 中 | 实现降级策略，返回 "unknown" 版本号 |
| 前端组件渲染错误 | 低 | 低 | 添加错误边界，确保不影响主应用 |
| 版本信息不一致 | 低 | 中 | 在构建脚本中确保版本号来源唯一（package.json） |
| 性能影响 | 极低 | 低 | 使用缓存机制，避免频繁读取文件 |
| 浏览器兼容性问题 | 低 | 低 | 使用标准 Vue 3 和 TypeScript 特性，避免实验性 API |

---

## 9. 附录

### 9.1 技术选型说明

1. **后端技术选择**：
   - 使用 FastAPI 路由，符合现有架构
   - 使用 Pydantic 模型进行数据验证（可选，因为响应结构简单）
   - 使用 `pathlib.Path` 进行文件操作，符合 Python 3 最佳实践

2. **前端技术选择**：
   - 使用 Vue 3 Composition API，符合项目现有风格
   - 使用 TypeScript，确保类型安全
   - 不引入新的第三方依赖，使用现有的状态管理和数据管理机制

### 9.2 相关文件路径

| 文件 | 路径 |
|-----|------|
| 摸排报告 | `/home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard/.staging/legacy_code_anatomy.md` |
| package.json | `/home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard/package.json` |
| 插件元数据 | `/home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard/plugin/openclaw.plugin.json` |
| 后端主入口 | `/home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard/src/backend/main.py` |
| 前端主应用 | `/home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard/frontend/src/App.vue` |
| 实时数据管理器 | `/home/ubuntu/vrt-projects/projects/openclaw-agent-dashboard/frontend/src/managers/RealtimeDataManager.ts` |

### 9.3 参考文档

- [OpenClaw Agent Dashboard 存量代码摸排报告](.staging/legacy_code_anatomy.md)
- [TR3: 安装系统技术需求分析](docs/specs/tr3-install-system.md)
- [Vue 3 官方文档 - Composition API](https://vuejs.org/guide/extras/composition-api-faq.html)
- [FastAPI 官方文档](https://fastapi.tiangolo.com/)

---

**文档版本**: 1.0.0  
**最后更新**: 2026-03-19  
**审核状态**: 待审核

---
