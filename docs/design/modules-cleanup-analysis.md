# Dashboard 模块价值分析与重构需求文档

> 文档版本：1.0
> 分析日期：2026-03-07
> 分析角色：产品经理 + 架构师

---

## 一、背景与目标

### 1.1 背景
OpenClaw Agent Dashboard 是一个 Agent 监控面板，当前包含以下模块：
- 协作流程（CollaborationFlow）
- 任务状态（TaskStatus）
- 性能监控（Performance）
- 机制追踪（MechanismTracking）
- 错误中心（ErrorCenter）
- 项目流水线（WorkflowView）
- API 状态（ApiStatus）

### 1.2 分析目标
1. 评估各模块对用户的实际价值
2. 识别冗余和无效功能
3. 制定重构计划，提升产品聚焦度

---

## 二、用户画像与核心场景

### 2.1 目标用户
| 用户类型 | 关注点 | 技术水平 |
|---------|-------|---------|
| 运维人员 | Agent 是否正常运行？有无报错？ | 中 |
| 开发者 | Agent 在做什么？性能如何？ | 高 |
| 产品/管理者 | 任务完成情况？整体进度？ | 低 |

### 2.2 核心使用场景
1. **日常监控**：快速了解所有 Agent 状态
2. **故障排查**：Agent 出错时定位问题
3. **性能分析**：了解 Token 消耗、响应时间
4. **任务跟踪**：了解任务执行进度

---

## 三、四模块深度分析

### 3.1 机制追踪 (MechanismTrackingPanel)

#### 功能描述
展示每个 Agent 的内部机制配置：
- Memory 文件状态（是否存在）
- Skills 列表
- Channel 类型
- Heartbeat 配置
- Cron 任务数量

#### 数据来源
- `sessions.json` 中的 `systemPromptReport`
- `openclaw.json` 配置文件
- `cron/jobs.json`

#### 价值评估

| 维度 | 评分 | 说明 |
|-----|------|-----|
| 用户需求 | ⭐⭐ | 用户不关心"机制"，关心"能力" |
| 信息可操作性 | ⭐ | 只能看，不能改 |
| 与其他模块重叠 | 高 | AgentDetailPanel 已展示类似信息 |
| 技术复杂度 | 低 | 简单读取配置文件 |

#### 问题清单
1. **概念错位**：展示的是"开发者配置"而非"用户关心的信息"
2. **信息价值低**：知道 Memory 文件存在与否，用户无法做任何操作
3. **误导性展示**：Heartbeat/Cron 是全局配置，展示在 Agent 级别不准确
4. **无业务场景**：什么情况下用户需要看这个面板？

#### 决策：删除

---

### 3.2 错误中心 (ErrorCenterPanel)

#### 功能描述
聚合展示两类错误：
1. **Session 错误**：从 jsonl 日志中提取 stopReason=error 的记录
2. **Model Failures**：解析 model-failures.log 文件

#### 数据来源
- 各 Agent 的 session jsonl 文件
- `memory/model-failures.log`

#### 价值评估

| 维度 | 评分 | 说明 |
|-----|------|-----|
| 用户需求 | ⭐⭐⭐⭐⭐ | 故障排查是核心需求 |
| 信息可操作性 | ⭐⭐⭐ | 可查看详情，但缺少处理动作 |
| 与其他模块重叠 | 中 | 与 API 状态有部分重叠 |
| 技术复杂度 | 中 | 需要解析日志文件 |

#### 问题清单
1. **错误分类粗糙**：仅 4 种类型（rate-limit/token-limit/timeout/unknown）
2. **缺少时间维度**：无法看到错误趋势
3. **缺少操作能力**：无法重试/忽略/标记
4. **与 API 状态重复**：都在读 model-failures.log

#### 决策：保留并增强

#### 增强方向
1. 合并 API 状态模块
2. 增加错误趋势图表
3. 增加按 Agent/时间/类型的筛选
4. 增加错误详情展开

---

### 3.3 项目流水线 (WorkflowView)

#### 功能描述
展示项目的流水线进度：
- 5 个阶段：需求分析 → 系统设计 → 代码开发 → 测试验收 → 部署上线
- 当前阶段状态
- 产出物列表

#### 数据来源
- `projects/{project_id}/.staging/workflow_state.json`

#### 价值评估

| 维度 | 评分 | 说明 |
|-----|------|-----|
| 用户需求 | ⭐⭐ | 概念好但实现有问题 |
| 数据可靠性 | ⭐ | **无数据来源** |
| 实现完整度 | ⭐ | 只有 UI，无后端支持 |
| 技术复杂度 | 低 | 硬编码阶段 |

#### 问题清单
1. **致命问题 - 无数据来源**：
   - 代码期望读取 `workflow_state.json`
   - 但没有任何代码在生成这个文件
   - 这是一个"假功能"

2. **概念错位**：
   - 流水线阶段硬编码（PRD/Design/Dev/QA/Deploy）
   - Agent 任务执行 ≠ 软件工程流水线
   - 不是所有项目都走这 5 步

3. **功能孤立**：
   - 与其他模块无关联
   - 与 Agent 执行的任务脱节

4. **产出物无来源**：
   - `artifacts` 字段无数据来源
   - 纯展示，无实际内容

#### 决策：删除

#### 备选方案（未来考虑）
如果需要项目管理功能，应该：
- 集成外部工具（Jira/GitHub Issues/Linear）
- 或基于 Agent 任务状态构建
- 当前实现应该移除

---

### 3.4 API 状态 (ApiStatusCard)

#### 功能描述
展示各模型 API 的健康状态：
- 状态：healthy / degraded / down
- 最近错误信息
- 错误次数统计

#### 数据来源
- `memory/model-failures.log`（与错误中心相同）

#### 价值评估

| 维度 | 评分 | 说明 |
|-----|------|-----|
| 用户需求 | ⭐⭐⭐ | 有一定价值，快速判断模型问题 |
| 信息可操作性 | ⭐⭐ | 只能看，无法切换模型 |
| 与其他模块重叠 | 高 | 与错误中心共享数据源 |
| 技术复杂度 | 低 | 简单解析日志 |

#### 问题清单
1. **与错误中心重复**：两个模块都在读 `model-failures.log`
2. **状态判断过于简单**：5分钟内有错误 = degraded
3. **无主动健康检查**：只是被动显示错误日志
4. **无自动切换能力**：知道有问题，但无法自动降级

#### 决策：合并到错误中心

#### 合并方案
- API 状态作为错误中心的一个"视图"
- 统一的错误管理入口
- 减少代码重复

---

## 四、重构决策汇总

| 模块 | 决策 | 理由 |
|------|------|------|
| 机制追踪 | **删除** | 非用户关注点，调试工具 |
| 错误中心 | **保留+增强** | 核心价值点 |
| 项目流水线 | **删除** | 无数据来源，假功能 |
| API 状态 | **合并** | 整合到错误中心 |

---

## 五、执行计划

### 5.1 Phase 1：删除无效模块

#### 前端删除
```
frontend/src/components/MechanismTrackingPanel.vue  → 删除
frontend/src/components/WorkflowView.vue            → 删除
frontend/src/components/ApiStatusCard.vue           → 删除
```

#### 后端删除
```
src/backend/api/mechanisms.py    → 删除
src/backend/api/workflow.py      → 删除
src/backend/api/api_status.py    → 删除
src/backend/data/mechanism_reader.py → 删除
```

#### App.vue 清理
- 移除相关组件导入
- 移除相关 section
- 移除 apiStatusList 相关代码

### 5.2 Phase 2：增强错误中心

#### 功能增强
1. 增加 API 错误视图（原 API 状态）
2. 增加错误统计卡片
3. 增加按类型/Agent 筛选
4. 优化错误展示布局

#### 数据层
- 复用现有的 `parse_failure_log` 函数
- 整合到 errors.py API

### 5.3 Phase 3：清理与测试

1. 清理未使用的导入和类型
2. 验证所有页面正常加载
3. 确认无 404 API 调用

---

## 六、预期收益

### 代码层面
- 前端：减少 ~400 行代码
- 后端：减少 ~300 行代码
- API 路由：减少 5 个端点

### 产品层面
- 界面更简洁，减少用户认知负担
- 功能更聚焦，错误管理统一入口
- 维护成本降低

### 用户体验
- 减少无效信息干扰
- 错误信息更集中、更易查找
- 页面加载更快

---

## 七、风险评估

| 风险 | 等级 | 缓解措施 |
|-----|------|---------|
| 用户习惯变化 | 低 | 被删除的功能使用率极低 |
| 功能缺失投诉 | 低 | 可通过配置恢复 |
| 遗留代码引用 | 中 | 全局搜索确认无引用 |

---

## 八、附录

### A. 文件变更清单

#### 删除文件
```
frontend/src/components/MechanismTrackingPanel.vue
frontend/src/components/WorkflowView.vue
frontend/src/components/ApiStatusCard.vue
src/backend/api/mechanisms.py
src/backend/api/workflow.py
src/backend/api/api_status.py
src/backend/data/mechanism_reader.py
```

#### 修改文件
```
frontend/src/App.vue                    # 移除模块引用
src/backend/api/__init__.py             # 移除路由注册
src/backend/api/errors.py               # 增强（可选）
frontend/src/components/ErrorCenterPanel.vue  # 增强（可选）
```

### B. API 变更

#### 删除的 API
```
GET /api/mechanisms
GET /api/mechanisms/{agent_id}
GET /api/workflows
GET /api/workflow/{project_id}
GET /api/api-status
```

#### 保留的 API
```
GET /api/errors              # 错误中心（可增强）
```
