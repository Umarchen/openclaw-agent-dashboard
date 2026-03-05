# OpenClaw 多 Agent 配置 · 逐步达成预期分析

> 分析目标：通过 OpenClaw 多团队（virtual-rnd-team）编程，是否能实现一步一步完成、达成预期？有哪些需要修改的地方？

---

## 一、当前架构概览

### 1.1 多 Agent 配置（openclaw.json）


| Agent           | 角色        | 工作区                 | 可派发对象                      |
| --------------- | --------- | ------------------- | -------------------------- |
| main            | 项目经理 (PM) | workspace-main      | analyst, architect, devops |
| analyst-agent   | 分析师 (BA)  | workspace-analyst   | -                          |
| architect-agent | 架构师 (SA)  | workspace-architect | -                          |
| devops-agent    | 开发+QA     | workspace-devops    | -                          |


### 1.2 协作机制

- **派发**：PM 通过 `sessions_spawn` 派发任务
- **回传**：子 Agent 完成后通过 `subagent-announce` 回传结果到 PM
- **模式**：`mode: "run"` 一次性任务，`mode: "session"` 持久会话
- **并发**：`subagents.maxConcurrent: 1`（当前仅 1 个并发子 Agent）

### 1.3 标准流程（PM Skill 定义）

```
需求 → BA(PRD) → SA(设计) → PM 审核 → SA(CR) → Dev(实现) → SA(CR) → QA(测试) → 部署
```

---

## 二、能否实现「一步一步完成」？

### 2.1 已具备的能力 ✅


| 能力        | 说明                                                       |
| --------- | -------------------------------------------------------- |
| **顺序派发**  | PM 可依次派发 BA → SA → Dev → QA，每步等子 Agent 完成后再派下一步          |
| **结果回传**  | 子 Agent 完成后自动 announce，PM 收到结果再决策                        |
| **质量门禁**  | PM Skill 定义了 staging、CR、promote 等流程                      |
| **串行约束**  | `maxConcurrent: 1` 天然保证同一时刻只跑一个子 Agent                   |
| **任务上下文** | PM 在 task 中注入 `[CONTEXT FILES]`、`VRT_WORKSPACE_ROOT` 等路径 |


### 2.2 存在的缺口 ⚠️


| 缺口                         | 影响                                         | 严重程度 |
| -------------------------- | ------------------------------------------ | ---- |
| **无强制步骤清单**                | PM 是 LLM，可能跳过/合并步骤，不严格按 SOP 执行             | 高    |
| **无步骤完成校验**                | 子 Agent 汇报「完成」后，PM 可能未做充分核实就进入下一步          | 中    |
| **需求文档未显式传递**              | 子 Agent 可能拿不到「可执行清单」，产出缺斤少两                | 高    |
| **VRT_WORKSPACE_ROOT 未统一** | 各 Agent 工作区不同，若路径未正确注入，子 Agent 找不到项目       | 中    |
| **超时/重试依赖 PM 自觉**          | runTimeoutSeconds、指数退避等需 PM 在 task 中体现，易遗漏 | 中    |


---

## 三、需要修改的地方

### 3.1 配置层（openclaw.json）


| 修改项                             | 建议                                                 | 说明                                                |
| ------------------------------- | -------------------------------------------------- | ------------------------------------------------- |
| **subagents.runTimeoutSeconds** | 在 `agents.defaults.subagents` 或 per-agent 中设置合理默认值 | 避免 PM 忘记设置导致无限等待                                  |
| **VRT_WORKSPACE_ROOT**          | 确保 Gateway 启动时或各 Agent 的 cwd 能解析该变量                | 当前依赖 project-manager/.env，子 Agent 需通过 task 获得实际路径 |


**示例：**

```json
{
  "agents": {
    "defaults": {
      "subagents": {
        "maxConcurrent": 1,
        "runTimeoutSeconds": 900
      }
    }
  }
}
```

### 3.2 PM Skill 层（project-manager/SKILL.md）


| 修改项           | 建议                                                                                   |
| ------------- | ------------------------------------------------------------------------------------ |
| **步骤清单强制化**   | 在 SOP 开头增加「必须按清单逐项执行，不得跳过」的硬性规则                                                      |
| **任务模板含清单引用** | 派发时 task 必须包含：`[当前步骤] 第 X 项`、`[需求清单] @docs/xxx-checklist.md`                         |
| **核实后才有下一步**  | 明确：收到子 Agent 产出后，必须先执行核实检查清单，通过才派发下一步                                                |
| **可执行清单位置**   | 将可执行清单放在 `${VRT_WORKSPACE_ROOT}/projects/${PROJECT_NAME}/docs/` 下，供 PM 和子 Agent 共同读取 |


### 3.3 子 Agent Skill 层（analyst/architect/devops）


| 修改项      | 建议                                           |
| -------- | -------------------------------------------- |
| **输入要求** | 在 SKILL 中明确：若 task 含 `[需求清单]` 路径，必须完整阅读并逐项实现 |
| **产出自检** | 产出前必须对照清单做自检，缺失项需在汇报中说明                      |


### 3.4 可选：OpenProse 流程固化

若希望**流程由程序而非 LLM 决定**，可考虑：

- 用 OpenProse 编写 `.prose` 流程：`session "BA" -> session "SA" -> session "Dev" -> session "QA"`
- 通过 `prose run feature-xxx.prose` 执行，由 OpenProse VM 按顺序执行
- 优点：步骤顺序固定，难以跳过
- 缺点：与当前 PM 主导的对话式协作需整合

---

## 四、推荐实施顺序

1. **P0**：在 PM Skill 中增加「步骤清单强制」「任务含清单引用」「核实后才有下一步」规则
2. **P0**：确保每个项目的 `docs/` 下有可执行清单，PM 派发时显式引用
3. **P1**：配置 `runTimeoutSeconds` 默认值，避免长时间卡死
4. **P1**：在子 Agent 的 SKILL 中增加「按清单实现、自检后汇报」规则
5. **P2**：评估 OpenProse 集成，用于标准化流程

---

## 五、小结


| 问题            | 结论                                                          |
| ------------- | ----------------------------------------------------------- |
| **能否一步一步完成？** | 可以，当前架构支持顺序派发和结果回传                                          |
| **能否达成预期？**   | 有风险，依赖 PM 和子 Agent 严格按 SOP 与清单执行                            |
| **核心改进点**     | 将「可执行清单」显式纳入流程，任务中引用、核实后推进下一步                               |
| **配置补充**      | 设置 `runTimeoutSeconds`，确保 `VRT_WORKSPACE_ROOT` 在各 Agent 间一致 |


---

## 六、缺口修复方案（已实施）

### 6.1 缺口 1+2+3：步骤清单强制、核实后才有下一步、需求文档显式传递

**修改文件**：`virtual-rnd-team/skills/project-manager/SKILL.md`

- 新增 **2.0 步骤清单强制与核实门禁**：
  - 有清单必按清单执行，严禁跳过
  - 任务模板必须含 `[当前步骤]`、`[项目路径]`、`[需求清单]`、`[CONTEXT FILES]`
  - 核实通过后才可派发下一步

### 6.2 缺口 3：子 Agent 按清单实现与自检

**修改文件**：
- `virtual-rnd-team/skills/analyst-agent/SKILL.md`
- `virtual-rnd-team/skills/architect-agent/SKILL.md`
- `virtual-rnd-team/skills/devops-agent/SKILL.md`

- 新增 **需求清单与自检** 规则：
  - 若 task 含 `[需求清单]` 路径，必须完整阅读并逐项实现
  - 产出前对照清单自检，缺失项在汇报中说明
  - 使用 task 中的 `[项目路径]` 绝对路径

### 6.3 缺口 4+5：超时默认值、VRT 路径统一

**修改文件**：`~/.openclaw/openclaw.json`

- 在 `agents.defaults.subagents` 中增加 `runTimeoutSeconds: 900`（15 分钟默认超时）

**VRT_WORKSPACE_ROOT 配置**（需人工确认）：
- 在 `skills/project-manager/.env` 中设置 `VRT_WORKSPACE_ROOT`，指向项目根目录（如 `/home/ubuntu/.openclaw/workspace-main`）
- PM 派发时从该变量拼出绝对路径注入 task，子 Agent 通过 `[项目路径]` 获得，无需各自配置

### 6.4 使用流程（修复后）

1. 在项目 `docs/` 下创建可执行清单（如 `docs/design/xxx-checklist.md`）
2. PM 派发时按 2.0.2 模板填写 task，显式引用清单路径
3. 子 Agent 收到 task 后阅读清单，逐项实现，自检后汇报
4. PM 收到回执后执行核实，通过才派下一步

### 6.5 多需求文件管理（避免拿错文档）

**问题**：多个需求产出在同一目录时，任务可能获取错误文档或 staging 互相覆盖。

**修复**：见 `multi-feature-file-management.md`。要点：
- 任务模板增加 `[FEATURE_ID]`、`[产出路径]`
- 多 feature 时 staging 用 `.staging/<FEATURE_ID>/` 隔离
- 子 Agent **仅**读 task 中 `[CONTEXT FILES]` 和 `[需求清单]` 列出的文件，**禁止**目录推断

---

## 七、参考文档

- `timeline-view-optimization-checklist.md`：可执行清单示例
- `OpenClaw-Agent协作组网形式.md`：主从、嵌套、对等模式
- `docs.openclaw.ai/tools/subagents`：sessions_spawn 与 announce 机制
- `virtual-rnd-team/DEPLOY.md`：VRT_WORKSPACE_ROOT 配置说明
- `multi-feature-file-management.md`：多需求文件管理规范

