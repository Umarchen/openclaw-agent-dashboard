# OpenClaw 配置中的 models 与 agents 说明 · 模型选项设计

> 目标：明确 openclaw.json 里 `models`、`providers`、`agents`、`defaults` 的含义与使用场景，并规定本工程（Dashboard）如何据此提供「主模型 / 备选模型」下拉选项。

---

## 一、OpenClaw 配置结构（从本工程使用方式归纳）

### 1.1 顶层概览

```text
openclaw.json
├── models          # 可选，模型「目录」：哪些模型可被选为主模型/备选
│   └── providers   # 按供应商组织的模型列表
└── agents         # 多 Agent 组网与默认配置
    ├── list        # Agent 列表（id, name, workspace, model, subagents, ...）
    └── defaults    # 默认值，对 list 中未显式写的字段生效
        ├── model   # 默认主模型与备选
        ├── models  # 可选，model_id -> { alias } 用于展示名
        └── subagents # 如 maxConcurrent, runTimeoutSeconds
```

### 1.2 `models` 与 `providers` 的含义与作用

| 配置路径 | 含义 | 作用 |
|----------|------|------|
| **models** | 顶层「模型目录」 | 定义当前 OpenClaw 实例中**可被选用**的模型集合（不绑定到具体 Agent）。 |
| **models.providers** | 按供应商分组的模型列表 | 每个 key 为 provider 名（如 `zhipu`、`openai`），value 为 `{ models: [ { id, name?, contextWindow?, maxTokens?, ... } ] }`。运行时/配置界面用其生成「主模型 / 备选模型」的可选列表。 |

- **有 `models.providers`**：表示配置了「模型目录」，Dashboard 应优先用这份列表作为下拉选项。
- **无或为空**：很多部署不会配置该块（或仅用 agents 里的 primary/fallbacks），此时 Dashboard 需要从 **agents** 侧推导出可选模型列表，避免下拉为空。

### 1.3 `agents` 与 `defaults` 的含义与作用

| 配置路径 | 含义 | 作用 |
|----------|------|------|
| **agents.list** | Agent 列表 | 定义有哪些 Agent（main、analyst-agent 等），每个可含 `model: { primary, fallbacks }`、`subagents`、`workspace` 等。与组网、派发关系相关。 |
| **agents.defaults** | 默认配置 | 对 `list` 中未显式写的字段提供默认值，减少重复。 |
| **agents.defaults.model** | 默认模型配置 | `{ primary?, fallbacks? }`。某个 Agent 未写 `model` 或只写了部分字段时，用其补全。 |
| **agents.defaults.models** | 模型展示名（可选） | `model_id -> { alias? }`。用于在 UI 中显示模型简称/别名（如 `zhipu/glm-4` → 「GLM-4」），不参与「可选列表」的构成。 |

- **多 Agent 场景**：每个 Agent 可以有自己的 `model.primary` 和 `model.fallbacks`；未配置时继承 `agents.defaults.model`。
- **与组网关系**：组网（谁派发给谁）由 `agents.list` 与各 Agent 的 `subagents` 等决定；**模型配置**描述的是「每个 Agent 使用哪些模型」，不直接决定拓扑，但组网与模型是同一配置文件下的两套维度。

---

## 二、配置场景分类

| 场景 | 特征 | 下拉选项应如何产生 |
|------|------|----------------------|
| **A. 完整目录** | 配置了 `models.providers` 且非空 | 以 `models.providers` 为准，生成「主模型 / 备选模型」下拉。 |
| **B. 仅 agents** | 无 `models.providers` 或为空，但有 `agents.list` 与/或 `agents.defaults.model` | 从**所有已配置的模型**收集：`agents.defaults.model` 的 primary + fallbacks，以及每个 `agents.list[].model` 的 primary + fallbacks，去重后作为可选列表，展示名用 `agents.defaults.models` 或 model_id 解析。 |
| **C. 混合** | 有 `models.providers`，但部分 Agent 曾手写过不在 providers 里的 model_id | 以 `models.providers` 为主列表，并**追加**「已在 agents 中使用但不在 providers 里」的 model_id，保证这些仍可选、不丢。 |

---

## 三、本工程（Dashboard）行为约定

### 3.1 可用模型列表的生成规则（`/api/available-models`）

1. **基础列表**
   - 若 `models.providers` 存在且非空：按其生成列表（每个 model 的 id 格式为 `provider/model_id`，name 等来自 provider 配置）。
   - 否则：基础列表为空。

2. **从 agents 收集的模型**
   - 始终计算：`agents.defaults.model` 的 primary、fallbacks + 每个 `agents.list[].model` 的 primary、fallbacks，去重得到 `used_model_ids`。

3. **合并策略**
   - 若基础列表非空：返回「基础列表」+ 在 `used_model_ids` 中但不在基础列表里的项（这些项用 `get_model_display_name` 等生成 name/provider，避免遗漏手写 model_id）。
   - 若基础列表为空：仅返回由 `used_model_ids` 构成的列表（每项含 id、name、provider 等），保证至少与当前配置一致、下拉不为空。

### 3.2 展示名

- 来自 `models.providers` 的项：用配置中的 `name` 或 `id`。
- 来自 agents 的项：用 `agents.defaults.models[model_id].alias` 或 model_id 的简短形式（如 `provider/model` 取 `model`）。

### 3.3 与组网的关系

- 组网、派发关系由 `agents.list` 与 subagents 等决定，本设计不改变其语义。
- 模型选项仅用于「在配置界面里为任意一个 Agent 选择主模型 / 备选模型」时，保证选项与 OpenClaw 配置一致且不遗漏已在用的模型。

---

## 四、实现要点（代码层）

- **config_reader**：已有 `get_agent_models(agent_id)`（含 defaults 合并）、`get_all_models_from_agents()`、`get_model_display_name(model_id)`，可直接复用。
- **agent_config_manager.get_all_available_models()**：
  - 先按现有逻辑从 `models.providers` 生成列表。
  - 再调用「从 agents 收集的 model_id 集合」。
  - 若 providers 列表非空：对「在 agents 中但不在 providers 列表中的 model_id」逐个追加一项（id、name、provider）。
  - 若 providers 列表为空：仅用「从 agents 收集」的列表作为返回值。
- 不改变现有「保存」逻辑：仍写回 `agents.list[].model.primary / fallbacks`，与 OpenClaw 约定一致。
