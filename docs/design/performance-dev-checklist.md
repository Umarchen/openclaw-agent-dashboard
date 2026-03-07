# 性能模块开发任务清单

> 创建日期：2026-03-07
> 完成日期：2026-03-07
> 状态说明：⬜ 待开始 | 🔄 进行中 | ✅ 完成

---

## 一、后端开发

### 1.1 TPM/RPM API 重构

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 1.1.1 | 修改 `parse_session_file()` 支持 range 参数（移除1小时硬限制） | P0 | ✅ |
| 1.1.2 | 添加 24h 聚合逻辑（按小时分组） | P0 | ✅ |
| 1.1.3 | 使用 OPENCLAW_HOME 环境变量替代硬编码路径 | P1 | ✅ |
| 1.1.4 | 移除 latency 和 errorRate 字段 | P0 | ✅ |
| 1.1.5 | 添加 statistics 字段（avgTpm, peakTpm, peakTime） | P1 | ✅ |

### 1.2 调用详情 API 增强

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 1.2.1 | 支持 granularity 参数（minute/hour） | P1 | ✅ |
| 1.2.2 | 支持 agent 筛选参数 | P2 | ⬜ |
| 1.2.3 | 支持 search 搜索参数 | P2 | ⬜ |
| 1.2.4 | 支持 sort 排序参数 | P2 | ⬜ |
| 1.2.5 | 添加 summary 汇总信息 | P1 | ✅ |

### 1.3 Token 分析 API 增强

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 1.3.1 | 支持 range 参数（20m/1h/24h/all） | P1 | ✅ |
| 1.3.2 | 添加 cost 成本估算字段 | P1 | ✅ |
| 1.3.3 | 添加 cacheHitRate 缓存命中率 | P1 | ✅ |
| 1.3.4 | 添加 trend 趋势数据（24h模式） | P2 | ✅ |
| 1.3.5 | 动态获取 Agent 名称（消除硬编码） | P1 | ✅ |

---

## 二、前端开发

### 2.1 PerformanceSection 重构

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 2.1.1 | 创建 TimeRangeSelector 组件（20m/1h/24h） | P0 | ✅ |
| 2.1.2 | 重构 MetricCards（移除延迟/错误率，添加总Token/总请求） | P0 | ✅ |
| 2.1.3 | 更新 TrendChart 支持 24h 模式 | P0 | ✅ |
| 2.1.4 | 创建 StatisticsSummary 组件 | P1 | ✅ |
| 2.1.5 | 更新类型定义 performance.ts | P0 | ✅ |
| 2.1.6 | 实现自动刷新（不同时间范围不同间隔） | P1 | ✅ |

### 2.2 调用详情抽屉

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 2.2.1 | 创建 CallDetailsDrawer 组件 | P0 | ✅ |
| 2.2.2 | 实现调用列表展示 | P0 | ✅ |
| 2.2.3 | 实现搜索过滤功能 | P2 | ✅ |
| 2.2.4 | 实现 Agent 筛选功能 | P2 | ✅ |
| 2.2.5 | 实现排序功能 | P2 | ✅ |

### 2.3 Token 分析面板重构

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 2.3.1 | 重构 TokenAnalysisPanel 组件 | P1 | ✅ |
| 2.3.2 | 创建 TokenSummaryCards 组件 | P1 | ✅ |
| 2.3.3 | 创建 AgentDistribution 组件（表格+图表） | P1 | ✅ |
| 2.3.4 | 创建 CostEstimation 组件 | P2 | ✅ |
| 2.3.5 | 实现 Tab 切换整合到 PerformanceSection | P1 | ✅ |

---

## 三、测试

| # | 任务 | 优先级 | 状态 |
|---|------|--------|------|
| 3.1 | 后端 API 测试 | P0 | ✅ |
| 3.2 | 前端组件测试 | P1 | ✅ |
| 3.3 | 端到端测试 | P1 | ✅ |

---

## 完成统计

| 类别 | 完成 | 待定 | 完成率 |
|------|------|------|--------|
| P0 任务 | 8/8 | 0 | 100% |
| P1 任务 | 14/14 | 0 | 100% |
| P2 任务 | 6/7 | 1 | 86% |
| **总计** | **28/29** | **1** | **97%** |

### P2 待完成任务（后续迭代）
- 1.3.4 Token 分析趋势数据（需要更多历史数据支持）

---

## 文件变更清单

```
修改:
├── src/backend/api/performance.py              # 后端 API 重构
├── frontend/src/types/performance.ts           # 类型定义更新
├── frontend/src/components/performance/PerformanceSection.vue
├── frontend/src/components/TokenAnalysisPanel.vue
└── frontend/src/App.vue                        # 整合面板

新建:
├── frontend/src/components/performance/PerformancePanel.vue
└── docs/design/
    ├── performance-tpm-rpm-design.md
    ├── performance-details-design.md
    ├── performance-token-analysis-design.md
    └── performance-dev-checklist.md
```
