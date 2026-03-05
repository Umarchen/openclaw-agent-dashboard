# TR-Timeline-00: 时序视图优化 - 汇总与开发计划

**版本**: v1.0  
**日期**: 2026-03-05  
**状态**: 待审核  

---

## 一、文档索引

| 文档 | 内容 | 状态 |
|------|------|------|
| [TR-01](./tr-timeline-optimization-01-requirement-analysis.md) | 需求分析（已实现 vs 待开发） | ✅ 完成 |
| [TR-02](./tr-timeline-optimization-02-llm-round-grouping-design.md) | LLM 轮次分组详细设计 | ✅ 完成 |
| [TR-03](./tr-timeline-optimization-03-tool-chain-visualization.md) | 工具链路可视化详细设计 | ✅ 完成 |

---

## 二、需求实现状态汇总

### 2.1 已完成（P0/P1）

| 模块 | 功能点 | 完成度 |
|------|--------|--------|
| **步骤标签优化** | toolCall 显示「工具名 调用」 | 100% |
| | toolResult 显示「工具名 结果/失败」 | 100% |
| | thinking 添加「LLM 推理」副标题 | 100% |
| | text 添加「LLM 输出」副标题 | 100% |
| | user 区分「用户」/「子Agent回传」 | 100% |
| **失败结果增强** | 展示工具名 | 100% |
| | 展示错误信息 | 100% |
| | 展示建议列表 | 100% |
| | 后端提取 details.error | 100% |
| **折叠摘要优化** | toolCall 显示 path/command | 100% |
| | toolResult 显示行数/错误摘要 | 100% |
| | thinking/text 显示字数 | 100% |
| **顶部图例** | 7 种类型图例 | 100% |

### 2.2 待开发（P2）

| 模块 | 功能点 | 状态 | 设计文档 |
|------|--------|------|---------|
| **LLM 轮次分组** | 按 assistant 消息分组 | ✅ 已完成 | TR-02 |
| | 分组标题「LLM #N」 | ✅ 已完成 | TR-02 |
| | 触发原因标注 | ✅ 已完成 | TR-02 |
| **工具链路可视化** | toolCall ↔ toolResult 连线 | ✅ 已完成 | TR-03 |
| | toolResult 缩进展示 | ✅ 已完成 | TR-03 |
| | 点击高亮配对 | ✅ 已完成 | TR-03 |
| | 执行时间显示 | ✅ 已完成 | TR-03 |

### 2.3 可选（P3）

| 模块 | 功能点 | 优先级 |
|------|--------|--------|
| 子 Agent 回传样式 | 独立图标/颜色 | P3 |
| 折叠联动 | 折叠 toolCall 同时折叠 toolResult | P3 |

---

## 三、开发计划

### 3.1 Sprint 1: LLM 轮次分组（预计 2 天）

**目标**: 实现按 LLM 轮次分组展示

| 任务 | 负责人 | 预估时间 |
|------|--------|---------|
| 后端 LLMRound 数据模型 | - | 0.5h |
| 后端轮次识别算法 | - | 1h |
| 后端 API 响应扩展 | - | 0.5h |
| 前端类型定义 | - | 0.25h |
| TimelineRound 组件 | - | 1.5h |
| TimelineView 集成 | - | 1h |
| 样式调整 | - | 0.5h |
| 测试与调试 | - | 1h |

**验收标准**:
- [ ] user 消息正确开启新轮次
- [ ] toolResult 后的 assistant 步骤开启新轮次
- [ ] 轮次标题显示触发原因
- [ ] 轮次内步骤正确归属

### 3.2 Sprint 2: 工具链路可视化（预计 2 天）

**目标**: 强化 toolCall 与 toolResult 因果关系

| 任务 | 负责人 | 预估时间 |
|------|--------|---------|
| 后端配对逻辑 | - | 1h |
| 后端执行时间计算 | - | 0.5h |
| 前端类型扩展 | - | 0.25h |
| TimelineToolLink 组件 | - | 1.5h |
| TimelineStep 缩进/高亮 | - | 1h |
| TimelineView 集成 | - | 1h |
| 样式调整 | - | 0.5h |
| 测试与调试 | - | 1h |

**验收标准**:
- [ ] toolCall 与 toolResult 正确配对
- [ ] 连接线正确显示
- [ ] toolResult 缩进展示
- [ ] 点击高亮配对功能
- [ ] 执行时间正确显示

---

## 四、影响范围

### 4.1 后端文件

| 文件 | 改动类型 |
|------|---------|
| `src/backend/data/timeline_reader.py` | 修改 |
| `src/backend/api/timeline.py` | 修改 |
| `plugin/dashboard/data/timeline_reader.py` | 同步修改 |
| `plugin/dashboard/api/timeline.py` | 同步修改 |

### 4.2 前端文件

| 文件 | 改动类型 |
|------|---------|
| `frontend/src/components/timeline/types.ts` | 修改 |
| `frontend/src/components/timeline/TimelineView.vue` | 修改 |
| `frontend/src/components/timeline/TimelineStep.vue` | 修改 |
| `frontend/src/components/timeline/TimelineRound.vue` | **新增** |
| `frontend/src/components/timeline/TimelineToolLink.vue` | **新增** |
| `frontend/src/components/timeline/TimelineConnector.vue` | 可能修改 |

---

## 五、测试策略

### 5.1 单元测试

- [ ] 后端轮次识别算法测试
- [ ] 后端配对逻辑测试
- [ ] 前端组件渲染测试

### 5.2 集成测试

- [ ] API 响应格式验证
- [ ] 前后端数据一致性

### 5.3 E2E 测试场景

| 场景 | 验证点 |
|------|--------|
| 用户发起对话 | 轮次分组正确 |
| 多工具调用 | 配对关系正确 |
| 工具执行失败 | 失败增强展示正确 |
| 子 Agent 回传 | 标签/样式区分 |

---

## 六、风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 后端数据结构变更影响现有功能 | 中 | 高 | 保留向后兼容，roundMode 可选 |
| 前端性能问题（大量步骤） | 低 | 中 | 虚拟滚动、懒加载 |
| 配对逻辑边界情况 | 中 | 中 | 充分测试边界场景 |

---

## 七、审核检查清单

### 7.1 需求完整性

- [ ] TR-01 中所有需求点都已覆盖
- [ ] 没有遗漏的需求
- [ ] 优先级划分合理

### 7.2 设计合理性

- [ ] 数据结构设计合理
- [ ] API 设计符合 RESTful 规范
- [ ] 组件划分清晰

### 7.3 实现可行性

- [ ] 后端改动可控
- [ ] 前端改动可控
- [ ] 工作量评估合理

### 7.4 测试覆盖

- [ ] 测试场景完整
- [ ] 边界情况考虑充分

---

## 八、下一步行动

1. **审核**: 请审核以上 TR 文档
2. **确认**: 确认需求点和设计
3. **排期**: 确认开发排期
4. **开发**: 按 Sprint 执行

---

*文档结束*
