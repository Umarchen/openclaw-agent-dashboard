# data-readers 模块解剖报告

> **解剖时间**: 2026-05-28 14:34 CST
> **模块路径**: `src/backend/data/`
> **解剖范围**: 10 个文件

## 1. 模块概述

### 职责边界
`data-readers` 是 Dashboard 的**数据访问层（DAL）**，负责从 OpenClaw 状态目录（`~/.openclaw`）下的磁盘文件中读取、解析、聚合运行时数据，提供给上层 `api/` 和 `status/` 模块消费。核心数据源为：
- `agents/{id}/sessions/sessions.json` — 会话索引
- `agents/{id}/sessions/*.jsonl` — 会话消息日志
- `subagents/runs.json` — 子 Agent 运行记录
- `openclaw.json` — 全局配置（Agent 列表、模型白名单等）
- `~/.openclaw-agent-dashboard/task_history.json` — Dashboard 自有持久化（非 OpenClaw 目录）

### 文件数量与代码规模

| 文件 | 行数（约） | 角色 |
|------|-----------|------|
| `session_reader.py` | ~520 | 主 Reader — session JSONL 解析 |
| `subagent_reader.py` | ~250 | 子 Agent 运行记录读取 |
| `timeline_reader.py` | ~870 | 时序步骤构建（最复杂） |
| `chain_reader.py` | ~250 | 任务链路拓扑构建 |
| `config_reader.py` | ~200 | 全局配置读取（纯读） |
| `error_analyzer.py` | ~280 | 错误分类与追溯分析 |
| `version_info_reader.py` | ~130 | 版本元数据读取 |
| `task_history.py` | ~150 | 任务历史持久化（自有数据） |
| `agent_config_manager.py` | ~310 | Agent 配置读取+写入 |
| `__init__.py` | 1 | 模块标识 |
| **合计** | **~2960** | |

---

## 2. 逐文件分析

### 2.1 `config_reader.py` — 全局配置读取器

**核心职责**: 提供 OpenClaw 根目录解析、Agent ID 规范化、配置文件读取的基础设施。

**关键函数/类**:

| 函数 | 职责 |
|------|------|
| `get_openclaw_root()` | 解析 OPENCLAW_STATE_DIR / OPENCLAW_HOME / ~/.openclaw 优先级 |
| `normalize_openclaw_agent_id(value)` | 将 Agent ID 规范化为小写，与 OpenClaw 落盘格式对齐 |
| `agent_ids_equal(a, b)` | 规范化后比较两个 Agent ID |
| `load_config()` | 读取 openclaw.json |
| `get_agents_list()` | 获取 Agent 列表 |
| `get_main_agent_id()` | 获取主 Agent ID（default:true → id=main → 列表首项） |
| `get_agent_config(agent_id)` | 按 ID 查找单个 Agent 配置（大小写不敏感） |
| `get_agent_models(agent_id)` | 获取 Agent 的 primary + fallbacks 模型配置 |
| `get_models_configured_by_agents()` | 收集所有 Agent 实际使用的模型 ID |
| `get_all_models_from_agents()` | 合并白名单 key + Agent 配置的模型 ID |

**数据流向**: `openclaw.json`（磁盘）→ `Dict[str, Any]`（内存）

**依赖**: 无内部模块依赖；被几乎所有其他文件导入。

**性能热点**: `load_config()` 每次调用都读盘（无缓存）。被 `get_agents_list()`、`get_agent_config()`、`get_all_models_from_agents()` 等逐级调用，**一次 API 请求可能触发多次 openclaw.json 读取**。

---

### 2.2 `session_reader.py` — 会话消息读取器

**核心职责**: 从 session JSONL 文件中读取最近消息、检测工作状态、提取错误、解析轮次。

**关键函数/类**:

| 函数 | 职责 |
|------|------|
| `_read_tail_lines(filepath, max_lines)` | 从文件尾部读取最多 max_lines 行（读 512KB） |
| `get_recent_messages(agent_id, limit)` | 获取最近 N 条消息（尾部读取） |
| `get_latest_user_message_text(agent_id)` | 取最近一条 user 消息文本 |
| `has_recent_errors(agent_id, minutes)` | 检查最近 N 分钟是否有错误 |
| `get_last_error(agent_id)` | 获取最近错误（session + runs.json 兜底） |
| `get_session_turns(agent_id, session_key, limit)` | 解析完整轮次（**全量读取 JSONL**） |
| `get_latest_tool_call(agent_id)` | 获取最近的工具调用及完成状态 |
| `has_thinking_block(agent_id)` | 判断是否在思考阶段 |
| `get_session_updated_at(agent_id)` | 从 sessions.json 读取 updatedAt 最大值 |
| `get_session_validation_report(...)` | 校验 session JSONL 完整性 |
| `compute_session_file_integrity(path)` | 计算文件 SHA256（大文件只哈希尾部 512KB） |

**数据流向**:
- `agents/{id}/sessions/*.jsonl` → 消息列表 / 错误 / 轮次
- `agents/{id}/sessions/sessions.json` → 索引解析

**依赖**: `config_reader`（路径解析）、`utils.data_repair`（JSONL 解析）、`core.error_handler`、`core.config_fortify`、`core.schemas`（JSON Schema 校验）、`subagent_reader`（`_get_last_run_error` 兜底）。

**性能热点**:
1. **`get_session_turns()`** — 全量逐行解析 JSONL，无 tail 优化。大 session 文件（数百 MB）是严重瓶颈。
2. **`get_session_updated_at()`** — 每次读取 sessions.json 并遍历所有 entry。
3. `get_recent_messages()` → `_read_tail_lines()` → 再调 `parse_session_jsonl_line()` 逐行解析。每次 API 请求独立 I/O。

---

### 2.3 `subagent_reader.py` — 子 Agent 运行记录读取器

**核心职责**: 从 `subagents/runs.json` 读取子 Agent 运行记录，解析子 Agent 的 session 文件获取输出和文件列表。

**关键函数/类**:

| 函数 | 职责 |
|------|------|
| `load_subagent_runs()` | 加载并校验 runs.json（JSON Schema 校验） |
| `get_active_runs()` | 获取未结束的运行 |
| `get_agent_runs(agent_id, limit)` | 按前缀过滤指定 Agent 的运行 |
| `is_agent_working(agent_id)` | 判断 Agent 是否活跃（作为执行者或派发者） |
| `get_waiting_child_agent(agent_id)` | 获取正在等待的子 Agent ID |
| `get_agent_output_for_run(child_session_key)` | 从子 Agent session 中提取最后一次 assistant 文本 |
| `get_agent_files_for_run(child_session_key)` | 从子 Agent session 中提取 write/edit 工具调用的文件路径 |

**数据流向**:
- `subagents/runs.json` → 运行记录列表
- `agents/{id}/sessions/*.jsonl`（通过 session_key 定位）→ 输出文本 / 文件路径

**依赖**: `config_reader`、`session_reader`（复用 `normalize_sessions_index`、`resolve_session_jsonl_path`、`_load_sessions_index_file`）、`core.schemas`、`core.error_handler`。

**性能热点**:
1. **`load_subagent_runs()`** — 无缓存，每次调用全量读取 runs.json。被 `get_active_runs()`、`get_agent_runs()`、`is_agent_working()`、`get_waiting_child_agent()` 串联调用。一次 `is_agent_working()` 请求 = 1 次全量读盘。
2. **`get_agent_output_for_run()` / `get_agent_files_for_run()`** — **全量逐行解析子 Agent session JSONL**，无 tail 优化。

---

### 2.4 `timeline_reader.py` — 时序步骤构建器（最复杂模块）

**核心职责**: 将 session JSONL 解析为可视化时序步骤（TimelineStep），支持主 Agent 和子 Agent 两种模式，支持 LLM 轮次分组、子 Agent 锚点对齐。

**关键函数/类**:

| 函数 | 职责 |
|------|------|
| `get_timeline_steps(agent_id, session_key, limit)` | 主入口：获取 Agent 时序步骤 |
| `resolve_agent_session_jsonl(agent_id, session_key)` | 定位 session JSONL 文件（sessions.json → glob 兜底） |
| `_parse_session_file(...)` | 解析 session JSONL，含大文件 tail 窗口、子 Agent 锚点、step budget |
| `_parse_session_lines(lines, ...)` | 逐行解析为 TimelineStep 列表 |
| `_build_llm_rounds(steps)` | 根据步骤序列构建 LLM 轮次 |
| `_pair_tool_calls_and_results(steps)` | 建立 toolCall ↔ toolResult 配对 |
| `get_subagent_runs()` | 获取按 agent_id 分组的 runs（带 mtime LRU 缓存） |
| `_get_subagent_timeline(agent_id, limit)` | 子 Agent 时序回退方案（runs.json + 主 session 合并） |
| `_extract_subagent_steps_from_main_session(...)` | 从主 Agent session 中提取子 Agent 相关步骤 |

**数据流向**:
- `agents/{id}/sessions/sessions.json` + `*.jsonl` → 时序步骤 + 轮次 + 统计
- `subagents/runs.json` → 子 Agent 锚点时间 + 运行状态

**依赖**: `config_reader`、`session_reader`（复用索引解析函数）、`subagent_reader`（`load_subagent_runs`）。

**性能热点**:
1. **`_parse_session_lines()`** — 全量逐行解析，每行创建 TimelineStep dataclass。大文件无行数限制（仅有子 Agent 的 `_SUBAGENT_READ_SAFETY_BYTES=32MB` 保护）。
2. **`_get_subagent_timeline()`** — 先尝试从 runs.json 构建，再从主 Agent session 全量解析提取子 Agent 相关步骤。串行阻塞。
3. **`_read_text_lines(path, max_lines)`** — 虽有尾部读取优化，但逻辑复杂（多次 seek + read）。
4. **`_extract_subagent_steps_from_main_session()`** — 全量读取主 Agent session 后逐行扫描。主 session 可能有数百 MB。
5. **`get_subagent_runs()` 依赖 `load_subagent_runs()`** — 而 `load_subagent_runs()` 无缓存，`lru_cache` 仅作用在 `_get_subagent_runs_cached` 的分组逻辑上，原始 I/O 每次重复。

---

### 2.5 `chain_reader.py` — 任务链路读取器

**核心职责**: 解析 `runs.json` 中的派发关系，构建 Agent 间的任务执行链路拓扑图。

**关键函数/类**:

| 函数 | 职责 |
|------|------|
| `build_task_chains(limit)` | 构建任务链路列表（核心函数） |
| `get_task_chain(chain_id)` | 获取单个链路详情 |
| `get_active_chain()` | 获取当前活跃链路 |
| `get_chains_summary()` | 获取链路摘要统计 |

**数据流向**: `subagents/runs.json`（通过 `load_subagent_runs()`）+ `openclaw.json`（通过 `_get_agents_config()`）→ 链路拓扑列表

**依赖**: `config_reader`、`subagent_reader`（`load_subagent_runs`）、`core.error_handler`。

**性能热点**:
1. **`build_task_chains()`** 调用 `_get_agents_config()` 读取 openclaw.json，同时调用 `_load_runs()` → `load_subagent_runs()` 读取 runs.json。两个文件串行读取。
2. **`get_task_chain(chain_id)`** 调用 `build_task_chains(limit=100)` 全量构建后再过滤 — O(N) 遍历所有链路只为找一个。
3. **`get_chains_summary()`** 调用 `build_task_chains(limit=100)` — 构建完整链路仅用于统计数字。

---

### 2.6 `error_analyzer.py` — 错误分析器

**核心职责**: 分析 session 中的错误，进行分类（API 认证、限流、超时等）和严重程度评估，提供修复建议。

**关键函数/类**:

| 函数 | 职责 |
|------|------|
| `classify_error(error_message)` | 基于正则模式匹配分类错误类型和严重程度 |
| `get_error_suggestions(error_type)` | 根据错误类型返回修复建议 |
| `parse_session_for_errors(session_path)` | **全量逐行解析** session 提取错误 |
| `get_tool_call_chain(session_path, before_turn)` | 获取错误发生前的工具调用链（**全量逐行**） |
| `analyze_agent_errors(agent_id)` | 分析单个 Agent 的所有 session 的错误 |
| `analyze_all_agents_errors()` | 分析所有 Agent 的错误（遍历所有 Agent 目录） |
| `get_error_detail(agent_id, session_file, turn_index)` | 获取单个错误的详细信息 |

**数据流向**: `agents/{id}/sessions/*.jsonl` → 错误列表 + 分类 + 建议

**依赖**: `config_reader`、`utils.data_repair`。

**性能热点**:
1. **`parse_session_for_errors()`** — 全量逐行解析 session JSONL。大文件阻塞。
2. **`analyze_agent_errors()`** — 对最近 5 个 session 文件串行全量解析。
3. **`analyze_all_agents_errors()`** — 遍历所有 Agent 目录 + 每个最近的 3 个 session，串行执行。多 Agent 场景下极度缓慢。
4. **`get_tool_call_chain()`** — 全量逐行解析到 `before_turn`，再遍历所有 session 文件为每个错误调用一次。

---

### 2.7 `version_info_reader.py` — 版本信息读取器

**核心职责**: 从 `package.json` / `openclaw.plugin.json` 读取版本信息，支持多路径探测和缓存。

**关键函数/类**:

| 函数 | 职责 |
|------|------|
| `VersionInfoReader.read_version_info()` | 读取版本信息（首次读盘，后续返回缓存） |
| `_candidate_roots()` | 从本文件位置向上枚举候选目录 |
| `_load_metadata_from_files()` | 在候选目录中探测 package.json / openclaw.plugin.json |

**数据流向**: `package.json` / `openclaw.plugin.json` → `{version, name, description, build_date?, git_commit?}`

**依赖**: 无内部模块依赖。

**性能热点**: 无（有缓存机制，仅首次请求读盘）。

---

### 2.8 `task_history.py` — 任务历史持久化

**核心职责**: 将已完成的任务持久化到 Dashboard 自有数据目录，避免 OpenClaw 清空 runs.json 后数据丢失。包含旧路径迁移逻辑。

**关键函数/类**:

| 函数 | 职责 |
|------|------|
| `get_dashboard_data_dir()` | 获取 Dashboard 数据目录（支持 OPENCLAW_AGENT_DASHBOARD_DATA 环境变量） |
| `load_task_history()` | 加载任务历史（含旧路径迁移） |
| `save_task_history(tasks)` | 保存任务历史（限制 200 条） |
| `merge_with_history(current_runs, run_to_task_fn)` | 合并当前 runs 与历史，持久化新完成的任务 |

**数据流向**: `~/.openclaw-agent-dashboard/task_history.json` ↔ `List[Dict]`

**依赖**: 无内部模块依赖。

**性能热点**: `load_task_history()` 和 `save_task_history()` 每次调用都读/写磁盘 JSON。频繁调用时有 I/O 开销，但文件通常很小。

---

### 2.9 `agent_config_manager.py` — Agent 配置管理器

**核心职责**: 读取和**修改** `openclaw.json` 中的 Agent 配置（模型切换、Agent 信息查询）。是 data 模块中唯一的**写操作**模块。

**关键函数/类**:

| 函数 | 职责 |
|------|------|
| `load_full_config()` | 加载完整 openclaw.json（无缓存） |
| `save_full_config(config)` | 保存完整配置（先备份） |
| `update_agent_model(agent_id, primary, fallbacks)` | 更新 Agent 模型配置 |
| `get_agent_config(agent_id)` | 获取单个 Agent 完整配置 |
| `get_all_available_models()` | 获取所有可用模型（白名单/全量/providers 兜底） |
| `get_agent_full_info(agent_id)` | 获取 Agent 完整信息（配置 + 运行状态） |
| `get_all_agents_info()` | 获取所有 Agent 信息 |

**数据流向**: `openclaw.json` ↔ `Dict`（双向读写）+ `sessions.json`（只读状态检查）

**依赖**: `config_reader`、`session_reader`（索引解析）。

**性能热点**:
1. **`load_full_config()`** — 每次调用全量读盘。被 `get_agent_config()`、`get_agent_model_config()`、`get_all_available_models()` 逐级调用。
2. **`get_all_agents_info()`** — 对每个 Agent 调用 `get_agent_full_info()` → `load_full_config()` + 读 `sessions.json`。N 个 Agent = N 次配置文件读取。
3. **`save_full_config()`** — 每次保存先 `shutil.copy2` 备份，串行阻塞。

---

### 2.10 `__init__.py` — 模块标识

仅包含注释 `# Data modules`，无导出。

---

## 3. 数据流拓扑

### 3.1 模块内文件间调用关系

```mermaid
graph TD
    CR[config_reader.py<br/>基础配置路径解析] --> SR[session_reader.py<br/>session 消息读取]
    CR --> SUBR[subagent_reader.py<br/>runs.json 读取]
    CR --> ER[error_analyzer.py<br/>错误分析]
    CR --> ACR[agent_config_manager.py<br/>配置读写]

    SR --> SUBR
    SR --> TR[timeline_reader.py<br/>时序步骤构建]
    SR --> ACR

    SUBR --> TR
    SUBR --> CHR[chain_reader.py<br/>任务链路构建]

    DR[utils.data_repair] -.-> SR
    DR -.-> SUBR
    DR -.-> TR
    DR -.-> ER

    CORE_SCHEMAS[core.schemas] -.-> SR
    CORE_SCHEMAS -.-> SUBR

    TH[task_history.py<br/>自有持久化] -.-> "独立"
    VIR[version_info_reader.py<br/>版本信息] -.-> "独立"
```

### 3.2 与其他模块的交互点

| 外部模块 | 交互方式 | 涉及的 data 文件 |
|---------|---------|----------------|
| `api/` | 直接调用 `data.*` 函数获取数据 | 所有文件 |
| `status/` | 调用 `session_reader`、`subagent_reader`、`chain_reader` 判断 Agent 状态 | session_reader, subagent_reader, chain_reader |
| `watchers/` | 定时轮询，调用 `data.*` 获取最新状态 | session_reader, subagent_reader, chain_reader, timeline_reader |
| `core/error_handler` | 被 data 模块调用记录错误 | session_reader, subagent_reader, chain_reader |
| `core/config_fortify` | 被 data 模块调用获取校验策略 | session_reader, subagent_reader |
| `core/schemas` | JSON Schema 校验 | session_reader, subagent_reader |
| `utils/data_repair` | JSONL 行解析 + 自动修复 | session_reader, subagent_reader, timeline_reader, error_analyzer |

---

## 4. 问题与瓶颈

### 4.1 重复 I/O（同一文件多处读取）

| 文件 | 问题 | 严重度 |
|------|------|--------|
| `openclaw.json` | `config_reader.load_config()` 无缓存，被 `get_agents_list()`、`get_agent_config()`、`get_default_config()` 逐级调用；`agent_config_manager.load_full_config()` 又独立实现一份无缓存读取。**一次请求可能读 5+ 次** | 🔴 高 |
| `subagents/runs.json` | `subagent_reader.load_subagent_runs()` 无缓存，被 `get_active_runs()`、`get_agent_runs()`、`is_agent_working()`、`get_waiting_child_agent()` 串联调用；`timeline_reader.get_subagent_runs()` 虽有 lru_cache 但内部仍调用无缓存的 `load_subagent_runs()`；`chain_reader._load_runs()` 再独立调用一次 | 🔴 高 |
| `agents/{id}/sessions/sessions.json` | `session_reader._load_sessions_index_file()` 无缓存，被 `normalize_sessions_index()`、`resolve_session_jsonl_path()`、`get_session_updated_at()`、`get_session_turns()` 多次独立调用 | 🟡 中 |

### 4.2 全量扫描（无 offset/tail 优化）

| 函数 | 文件 | 问题 | 严重度 |
|------|------|------|--------|
| `get_session_turns()` | session_reader | **全量逐行解析** JSONL，无 tail 窗口 | 🔴 高 |
| `get_agent_output_for_run()` | subagent_reader | **全量逐行解析**子 Agent session | 🟡 中 |
| `get_agent_files_for_run()` | subagent_reader | **全量逐行解析**子 Agent session | 🟡 中 |
| `parse_session_for_errors()` | error_analyzer | **全量逐行解析** session | 🟡 中 |
| `get_tool_call_chain()` | error_analyzer | **全量逐行解析**到指定 turn，再对每个错误调一次 | 🟡 中 |
| `analyze_all_agents_errors()` | error_analyzer | **遍历所有 Agent × 3 个 session** 全量解析 | 🔴 高 |
| `_extract_subagent_steps_from_main_session()` | timeline_reader | **全量读取**主 Agent session 后逐行扫描 | 🔴 高 |
| `_parse_session_file()` | timeline_reader | 子 Agent 小文件全量解析；大文件有 tail 窗口但阈值 32MB 过大 | 🟡 中 |

### 4.3 串行阻塞

| 场景 | 问题 | 严重度 |
|------|------|--------|
| 多 Agent 状态查询 | `get_all_agents_info()` 逐 Agent 串行读取配置 + sessions.json | 🟡 中 |
| `analyze_all_agents_errors()` | 逐 Agent 串行全量解析 session | 🔴 高 |
| `build_task_chains()` | 读 openclaw.json + 读 runs.json 串行 | 🟢 低 |

### 4.4 缺乏增量能力

| 场景 | 问题 |
|------|------|
| 所有 Reader | **纯全量读取**，无 inode/offset 追踪，无法从上次读取位置续读 |
| `has_recent_session_activity()` | 每次重新解析 sessions.json 全部 entry |
| `is_agent_working()` | 每次全量加载 runs.json 再过滤 |
| `get_recent_messages()` | 虽有 tail 优化，但**无持久 offset**，每次仍从文件末尾 512KB 扫描 |

---

## 5. 对方案C（统一事件流 + 内存 StateStore）的适配分析

### 5.1 可被 Ingest 层替代的函数

以下函数的本质是「从磁盘 JSONL 读取最近事件并做状态推断」，可由 Ingest 层写入 StateStore 后直接从内存查询：

| 当前函数 | 当前数据源 | StateStore 替代方式 |
|---------|-----------|-------------------|
| `get_recent_messages()` | session JSONL tail | StateStore.recent_messages[agent_id] |
| `get_latest_user_message_text()` | session JSONL tail | StateStore.latest_user_msg[agent_id] |
| `has_recent_errors()` | session JSONL tail | StateStore.last_error[agent_id] |
| `get_last_error()` | session JSONL tail + runs.json | StateStore.last_error[agent_id] |
| `has_thinking_block()` | session JSONL tail | StateStore.current_state[agent_id].phase |
| `get_latest_tool_call()` | session JSONL tail | StateStore.pending_tool[agent_id] |
| `is_agent_working()` | runs.json | StateStore.active_runs[agent_id] |
| `get_active_runs()` | runs.json | StateStore.active_runs |
| `get_waiting_child_agent()` | runs.json | StateStore.active_runs[agent_id].waiting_for |
| `has_recent_session_activity()` | sessions.json | StateStore.last_activity_ts[agent_id] |
| `get_session_updated_at()` | sessions.json | StateStore.last_activity_ts[agent_id] |
| `get_timeline_steps()` | session JSONL 全量/tail | StateStore.timeline[agent_id] |
| `build_task_chains()` | runs.json | StateStore.chains |
| `get_active_chain()` | runs.json | StateStore.chains.active |

**预估可替代**: 约 14 个高频读取函数 → StateStore 内存查询，延迟从 ~10-100ms I/O 降至 ~0.01ms 内存访问。

### 5.2 应保留为降级/冷启动路径的函数

| 函数 | 保留原因 |
|------|---------|
| `config_reader.get_openclaw_root()` | 基础设施，Ingest 层也依赖 |
| `config_reader.normalize_openclaw_agent_id()` | 基础工具函数 |
| `config_reader.load_config()` | 冷启动时首次加载配置；运行时由 StateStore 缓存 |
| `session_reader.get_session_turns()` | 全量轮次解析（含 usage 统计），Ingest 层可增量维护但冷启动需全量 |
| `session_reader.get_session_validation_report()` | 诊断工具，非热路径 |
| `session_reader.resolve_session_jsonl_path()` | 路径解析基础设施 |
| `subagent_reader.load_subagent_runs()` | 冷启动全量加载；运行时由 Ingest 层增量维护 |
| `subagent_reader.get_agent_output_for_run()` | 按需历史查询，不适合全量 Ingest |
| `subagent_reader.get_agent_files_for_run()` | 按需历史查询 |
| `error_analyzer.parse_session_for_errors()` | 诊断工具，全量扫描特性 |
| `error_analyzer.analyze_all_agents_errors()` | 批量诊断，非热路径 |
| `task_history.*` | Dashboard 自有持久化，独立于 OpenClaw 状态 |
| `version_info_reader.*` | 启动时读取一次即可 |
| `agent_config_manager.save_full_config()` | 写操作，不涉及 Ingest |

### 5.3 模块间接口改造建议

1. **引入 StateStore 层**: 新建 `state_store.py` 作为模块内共享的内存状态容器，持有 `per_agent` 和 `global` 两个命名空间。

2. **Ingest 入口**: 新建 `ingest/` 目录，监听 OpenClaw 状态文件变化（fsnotify 或轮询 tail），将事件写入 StateStore。data-readers 中的高频查询函数改为优先查 StateStore，miss 时 fallback 到磁盘读取。

3. **config_reader 缓存化**: `load_config()` 增加 TTL 缓存（~5s），`agent_config_manager` 写入时主动失效缓存。

4. **subagent_reader 缓存化**: `load_subagent_runs()` 增加 mtime 感知的 LRU 缓存（类似 `timeline_reader._get_subagent_runs_cached` 的模式，但缓存原始数据而非分组结果）。

5. **error_analyzer 增量化**: Ingest 层在解析 JSONL 时同步提取错误信息写入 StateStore，`analyze_agent_errors()` 改为从 StateStore 聚合而非全量扫描。

6. **timeline_reader 轻量化**: Ingest 层增量维护 `timeline[agent_id]`（append-only），`get_timeline_steps()` 直接从 StateStore 返回，仅在冷启动或 miss 时走全量解析。

7. **chain_reader 重构**: `build_task_chains()` 改为从 StateStore 的 runs 数据构建，而非每次读磁盘。`get_task_chain(chain_id)` 改为直接索引查询（StateStore.chains_map[chain_id]），而非全量构建后过滤。
