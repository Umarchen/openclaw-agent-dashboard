# 多需求/多 Feature 文件管理规范

> 问题：多个需求的产出在同一目录（docs/specs、docs/design、.staging）时，任务可能获取错误文档或产出互相覆盖。

---

## 一、风险分析

### 1.1 目录结构现状

| 目录 | 用途 | 多需求风险 |
|------|------|------------|
| `docs/specs/` | PRD 产出 | 多 feature 时存在 `feature_a_spec.md`、`feature_b_spec.md`，子 Agent 若未指定可能读错 |
| `docs/design/` | 设计、清单 | 同上，`timeline-checklist.md` 与 `task-chain-checklist.md` 并存 |
| `docs/reviews/` | CR、QA 报告 | `cr_feature_a.md`、`cr_feature_b.md` |
| `.staging/` | 暂存产出 | **高危**：仅用文件名，`design.md` 会互相覆盖；workflow 状态以 `file_name` 为 key，会冲突 |

### 1.2 典型错误场景

1. **PM 未指定 FEATURE**：派发「根据设计实现」时，Dev 读到 `task-chain-design.md` 而非 `timeline-design.md`
2. **Staging 覆盖**：Feature A 产出 `design.md` 在 .staging，Feature B 也产出 `design.md`，后者覆盖前者
3. **清单混淆**：task 写「需求清单见 docs/design/」，子 Agent 读到错误的 checklist
4. **requirements.md 歧义**：单文件，多需求时无法区分

---

## 二、修复方案

### 2.1 任务模板增加 [FEATURE_ID]（强制）

```
[FEATURE_ID] <feature-slug>   # 如 timeline-view-optimization
[当前步骤] 第 X 项：<步骤描述>
[项目路径] <绝对路径>
[需求清单] <本 feature 的 checklist 绝对路径>
[CONTEXT FILES]
- <本 feature 的上游文件 1 绝对路径>
- <本 feature 的上游文件 2 绝对路径>

<具体任务描述>
```

- **FEATURE_ID**：唯一标识当前需求/feature，用于路径区分和 staging 隔离
- PM 在每次派发前必须确定当前 feature，并注入到 task

### 2.2 Staging 按 Feature 隔离

| 当前 | 修改后 |
|------|--------|
| `.staging/design.md` | `.staging/<FEATURE_ID>/design.md` |
| `.staging/xxx_spec.md` | `.staging/<FEATURE_ID>/xxx_spec.md` |

- 子 Agent 产出必须写入 `.staging/<FEATURE_ID>/`，不得写入 `.staging/` 根目录
- PM 在 task 中显式指定：`[产出路径] <项目路径>/.staging/<FEATURE_ID>/`

### 2.3 文件命名约定（已有，需强化）

| 类型 | 命名 | 示例 |
|------|------|------|
| PRD | `{FEATURE_ID}_spec.md` | `timeline-view-optimization_spec.md` |
| 设计 | `{FEATURE_ID}_design.md` 或 `{FEATURE_ID}.md` | `timeline-view-optimization_design.md` |
| 清单 | `{FEATURE_ID}-checklist.md` | `timeline-view-optimization-checklist.md` |
| CR 报告 | `cr_{FEATURE_ID}.md` | `cr_timeline-view-optimization.md` |
| QA 报告 | `qa_{FEATURE_ID}.md` | `qa_timeline-view-optimization.md` |

### 2.4 子 Agent 读取规则（强制）

- **禁止**：根据目录推断（如「读取 docs/design/ 下的设计」）
- **必须**：仅读取 task 中 `[CONTEXT FILES]` 和 `[需求清单]` 明确列出的**完整绝对路径**文件
- **若 task 仅给目录**：必须向 PM 确认具体文件名，不得自行猜测

### 2.5 单需求项目简化

- 若项目**仅有一个活跃 feature**，可省略 `[FEATURE_ID]`，staging 仍用 `.staging/`（保持兼容）
- 若项目有**多个并发 feature**，必须启用 FEATURE_ID 与 `.staging/<FEATURE_ID>/`

---

## 三、涉及修改

| 层级 | 文件 | 修改内容 |
|------|------|----------|
| PM Skill | project-manager/SKILL.md | 任务模板增加 [FEATURE_ID]、[产出路径]；多 feature 时 staging 隔离规则 |
| 子 Agent Skill | analyst/architect/devops | 禁止目录推断，仅读 task 明确列出的文件 |
| workflow.py | project-manager 脚本 | 支持 `.staging/<FEATURE_ID>/` 路径（若用 Python 管理 staging） |
