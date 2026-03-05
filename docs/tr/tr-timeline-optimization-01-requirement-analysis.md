# TR-Timeline-01: 时序视图优化需求分析

**版本**: v1.0  
**日期**: 2026-03-05  
**作者**: TR Analysis  

---

## 一、需求概述

根据 `docs/design/timeline-view-optimization.md` 优化方案，对时序视图进行全面升级，提升用户对 Agent 执行流程的理解。

---

## 二、需求项与实现状态对照表

### 2.1 步骤标签与文案优化（P0）

| 需求ID | 需求描述 | 状态 | 实现位置 | 备注 |
|--------|---------|------|----------|------|
| L1-001 | toolCall 显示为「工具名 + 调用」 | ✅ 已实现 | `TimelineStep.vue:141-142` | `Read 调用` |
| L1-002 | toolResult 成功显示为「工具名 + 结果」 | ✅ 已实现 | `TimelineStep.vue:145-148` | `Read 结果` |
| L1-003 | toolResult 失败显示为「工具名 + 失败」 | ✅ 已实现 | `TimelineStep.vue:145-148` | `Read 失败` |
| L1-004 | thinking 添加副标题「LLM 推理」 | ✅ 已实现 | `TimelineStep.vue:154-158` | stepSubtitle |
| L1-005 | text 添加副标题「LLM 输出」 | ✅ 已实现 | `TimelineStep.vue:154-158` | stepSubtitle |
| L1-006 | user 区分「用户输入」与「子 Agent 回传」 | ✅ 已实现 | `timeline_reader.py:119-154` | _detect_subagent_sender |
| L1-007 | 子 Agent 回传显示为「分析师回传」等 | ✅ 已实现 | `timeline_reader.py:149-154` | 动态标签 |

### 2.2 失败结果增强（P0）

| 需求ID | 需求描述 | 状态 | 实现位置 | 备注 |
|--------|---------|------|----------|------|
| F1-001 | 失败时展示工具名 | ✅ 已实现 | `TimelineStep.vue:55-56` | `❌ 工具执行失败` |
| F1-002 | 失败时展示错误信息 | ✅ 已实现 | `TimelineStep.vue:63-71` | toolResultErrorDisplay |
| F1-003 | 失败时展示建议列表 | ✅ 已实现 | `TimelineStep.vue:66-70` | toolResultErrorSuggestion |
| F1-004 | ENOENT 错误建议 | ✅ 已实现 | `TimelineStep.vue:230-231` | 检查路径、确认存在 |
| F1-005 | 权限错误建议 | ✅ 已实现 | `TimelineStep.vue:233-234` | 检查权限 |
| F1-006 | 超时错误建议 | ✅ 已实现 | `TimelineStep.vue:236-237` | 增加超时、简化任务 |
| F1-007 | 后端提取 details.error 字段 | ✅ 已实现 | `timeline_reader.py:56,532` | toolResultError |

### 2.3 折叠态摘要优化（P1）

| 需求ID | 需求描述 | 状态 | 实现位置 | 备注 |
|--------|---------|------|----------|------|
| C1-001 | toolCall 折叠显示 path/command | ✅ 已实现 | `TimelineStep.vue:166-175` | collapseSummary |
| C1-002 | toolResult 成功显示行数 | ✅ 已实现 | `TimelineStep.vue:181-184` | `342 行` |
| C1-003 | toolResult 失败显示错误摘要 | ✅ 已实现 | `TimelineStep.vue:177-180` | 前30字符 |
| C1-004 | thinking 显示字数 | ✅ 已实现 | `TimelineStep.vue:186-189` | `约 150 字` |
| C1-005 | text 显示字数 | ✅ 已实现 | `TimelineStep.vue:190-193` | `约 80 字` |

### 2.4 顶部图例（P1）

| 需求ID | 需求描述 | 状态 | 实现位置 | 备注 |
|--------|---------|------|----------|------|
| G1-001 | 图例区域 | ✅ 已实现 | `TimelineView.vue:43-51` | timeline-legend |
| G1-002 | 用户/回传图例 | ✅ 已实现 | `TimelineView.vue:44` | 👤 用户/回传 |
| G1-003 | LLM 思考图例 | ✅ 已实现 | `TimelineView.vue:45` | 🧠 LLM 思考 |
| G1-004 | LLM 回复图例 | ✅ 已实现 | `TimelineView.vue:46` | 🤖 LLM 回复 |
| G1-005 | 工具调用图例 | ✅ 已实现 | `TimelineView.vue:47` | 🔧 工具调用 |
| G1-006 | 工具成功图例 | ✅ 已实现 | `TimelineView.vue:48` | ✅ 工具成功 |
| G1-007 | 工具失败图例 | ✅ 已实现 | `TimelineView.vue:49` | ❌ 工具失败 |
| G1-008 | 错误图例 | ✅ 已实现 | `TimelineView.vue:50` | ⚠️ 错误 |

### 2.5 LLM 轮次分组（P2）

| 需求ID | 需求描述 | 状态 | 实现位置 | 备注 |
|--------|---------|------|----------|------|
| R1-001 | 按 LLM 轮次分组展示 | ✅ 已实现 | `TimelineView.vue` | useRoundMode + renderItems |
| R1-002 | 分组标题「LLM 轮次 #N」 | ✅ 已实现 | `TimelineRound.vue` | round-badge |
| R1-003 | 同一 assistant 消息内的 thinking + toolCall + text 归为一组 | ✅ 已实现 | `timeline_reader.py:_build_llm_rounds` | 后端轮次识别 |
| R1-004 | toolResult 作为「工具执行」块 | ✅ 已实现 | `TimelineView.vue` | tool-execution-label |
| R1-005 | 分组框或背景色区分 | ✅ 已实现 | `TimelineRound.vue` | trigger-* 样式类 |

### 2.6 toolCall ↔ toolResult 连线/缩进（P2）

| 需求ID | 需求描述 | 状态 | 实现位置 | 备注 |
|--------|---------|------|----------|------|
| L2-001 | toolCall 与 toolResult 之间连线 | ✅ 已实现 | `TimelineToolLink.vue` | 虚线连接 |
| L2-002 | toolResult 相对 toolCall 缩进 | ✅ 已实现 | `TimelineStep.vue` | is-paired-result 样式 |
| L2-003 | 配对高亮（点击 toolCall 高亮 toolResult） | ✅ 已实现 | `TimelineView.vue` | handleHighlightPair |
| L2-004 | 工具执行时间显示 | ✅ 已实现 | `TimelineToolLink.vue` | executionTime |
| L2-005 | 后端配对逻辑 | ✅ 已实现 | `timeline_reader.py:_pair_tool_calls_and_results` | 双向关联 |
| L2-006 | 折叠联动（可选） | ⏸️ 暂不实现 | - | P3 |

### 2.7 子 Agent 回传单独样式（P3）

| 需求ID | 需求描述 | 状态 | 实现位置 | 备注 |
|--------|---------|------|----------|------|
| S1-001 | 子 Agent 回传使用不同图标/颜色 | ⚠️ 部分实现 | `TimelineStep.vue` | 标签已区分，样式未区分 |
| S1-002 | 回传消息特殊展示 | ⚠️ 部分实现 | - | 标签区分，无特殊样式 |

---

## 三、已完成功能汇总

### 3.1 核心功能（已完成）

| 功能模块 | 完成度 | 说明 |
|---------|-------|------|
| 步骤标签优化 | 100% | 工具名+动作，LLM 标注 |
| 失败结果增强 | 100% | 错误信息+建议 |
| 折叠摘要 | 100% | 关键信息预览 |
| 顶部图例 | 100% | 7 种类型图例 |
| 消息来源识别 | 100% | 区分用户/子Agent |

### 3.2 实现细节

**后端改动**:
- `timeline_reader.py`: 新增 `_detect_subagent_sender()` 检测子 Agent 回传
- `timeline_reader.py`: 新增 `toolResultError` 字段提取
- `timeline_reader.py`: 新增 `senderId`/`senderName` 字段

**前端改动**:
- `TimelineStep.vue`: `stepLabel` 计算逻辑优化
- `TimelineStep.vue`: `stepSubtitle` 副标题
- `TimelineStep.vue`: `collapseSummary` 折叠摘要
- `TimelineStep.vue`: `toolResultErrorDisplay`/`toolResultErrorSuggestion`
- `TimelineView.vue`: 图例区域
- `types.ts`: 新增 `toolResultError`/`senderId`/`senderName`

---

## 四、待开发功能汇总

### 4.1 P2 优先级（待开发）

| 功能ID | 功能名称 | 工作量 | 描述 |
|--------|---------|--------|------|
| R1 | LLM 轮次分组 | 中 | 按 assistant 消息分组展示 |
| L2 | 工具链路可视化 | 中 | 连线、缩进、折叠联动 |

### 4.2 P3 优先级（可选）

| 功能ID | 功能名称 | 工作量 | 描述 |
|--------|---------|--------|------|
| S1 | 子 Agent 回传样式 | 小 | 独立图标/颜色/布局 |

---

## 五、下一步行动

建议优先处理 P2 功能：

1. **R1-LLM轮次分组** - 提升用户对执行流程的理解
2. **L2-工具链路可视化** - 强化 toolCall 与 toolResult 的因果关系

详细设计见后续 TR 文档。

