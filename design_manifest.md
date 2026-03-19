# Design Manifest - VERSION_DISPLAY

> **项目名称**: OpenClaw Agent Dashboard  
> **特性标识**: VERSION_DISPLAY  
> **编写日期**: 2026-03-19  
> **编写人员**: 架构师 (SA)  
> **项目模式**: 增量开发（Incremental Mode）

---

## 需求到设计的映射表

| Requirement ID | Target File (Planned) | Change Intent | Allowed Symbols |
|----------------|----------------------|---------------|-----------------|
| [REQ_VERSION_DISPLAY_001] | src/backend/data/version_info_reader.py | CREATE | VersionInfoReader class, readVersionInfo(), _readBuildDate(), _readGitCommit() |
| [REQ_VERSION_DISPLAY_001] | src/backend/api/version.py | CREATE | router, VersionInfo(BaseModel), get_version_info() |
| [REQ_VERSION_DISPLAY_001] | src/backend/main.py | MODIFY | app.include_router(version_router) |
| [REQ_VERSION_DISPLAY_002] | frontend/src/components/common/VersionDisplay.vue | CREATE | VersionDisplay component, setup(), fetchVersionInfo() |
| [REQ_VERSION_DISPLAY_002] | frontend/src/composables/useVersionInfo.ts | CREATE (OPTIONAL) | useVersionInfo() |
| [REQ_VERSION_DISPLAY_002] | frontend/src/App.vue | MODIFY | import VersionDisplay, <VersionDisplay /> |
| [REQ_VERSION_DISPLAY_003] | frontend/src/managers/StateManager.ts | MODIFY | versionInfo field, setVersionInfo(), getVersionInfo() |
| [REQ_VERSION_DISPLAY_003] | frontend/src/managers/RealtimeDataManager.ts | MODIFY | loadVersionInfo(), getVersionInfo() |
| [REQ_VERSION_DISPLAY_004] | src/backend/data/version_info_reader.py | MODIFY | 环境变量读取逻辑 (DASHBOARD_VERSION, DASHBOARD_BUILD_DATE, DASHBOARD_GIT_COMMIT) |
| [REQ_VERSION_DISPLAY_004] | scripts/build-plugin.js | MODIFY (OPTIONAL) | 构建时间注入逻辑 |

---

## 变更类型统计

- **CREATE（新增文件）**: 4 个
- **MODIFY（修改文件）**: 4 个

## 文件清单

### 新增文件（4个）
1. `src/backend/data/version_info_reader.py` - 版本信息读取器
2. `src/backend/api/version.py` - 版本信息 API 路由
3. `frontend/src/components/common/VersionDisplay.vue` - 版本显示组件
4. `frontend/src/composables/useVersionInfo.ts` - 版本信息组合式函数（可选）

### 修改文件（4个）
1. `src/backend/main.py` - 注册版本信息路由
2. `frontend/src/App.vue` - 集成版本显示组件
3. `frontend/src/managers/StateManager.ts` - 新增版本信息状态缓存
4. `frontend/src/managers/RealtimeDataManager.ts` - 新增版本信息加载逻辑

---

## 优先级说明

### P0（必须实现）
- [REQ_VERSION_DISPLAY_001]: 后端版本信息 API
- [REQ_VERSION_DISPLAY_002]: 前端版本信息组件

### P1（建议实现）
- [REQ_VERSION_DISPLAY_003]: 实时数据管理器集成

### P2（可选优化）
- [REQ_VERSION_DISPLAY_004]: 版本信息配置（环境变量支持）
- `frontend/src/composables/useVersionInfo.ts`: 组合式函数（可选，取决于是否需要复用逻辑）

---

## 实施检查清单

### 阶段 1: 后端 API 实现
- [ ] 创建 `src/backend/data/version_info_reader.py`
- [ ] 创建 `src/backend/api/version.py`
- [ ] 修改 `src/backend/main.py` 注册路由
- [ ] 单元测试：验证 API 返回正确的版本信息

### 阶段 2: 前端组件实现
- [ ] 创建 `frontend/src/components/common/VersionDisplay.vue`
- [ ] 修改 `frontend/src/App.vue` 集成组件
- [ ] 本地测试：验证组件渲染和版本号显示

### 阶段 3: 实时数据管理集成
- [ ] 修改 `frontend/src/managers/StateManager.ts` 新增状态缓存
- [ ] 修改 `frontend/src/managers/RealtimeDataManager.ts` 实现自动加载
- [ ] 集成测试：验证应用启动时自动加载

### 阶段 4: 配置和构建优化（可选）
- [ ] 修改 `scripts/build-plugin.js` 确保版本信息正确注入
- [ ] 测试环境变量覆盖功能
- [ ] 端到端测试：验证从构建到部署的完整流程

---

## 设计文档交叉引用

本 manifest 与以下设计文档配套使用：
- **设计文档**: `.staging/design/VERSION_DISPLAY_design.md`
- **需求文档**: `docs/specs/VERSION_DISPLAY_spec.md`
- **存量代码解剖**: `.staging/legacy_code_anatomy.md`

---

**文档版本**: 1.0.0  
**最后更新**: 2026-03-19  
**审核状态**: 待审核
