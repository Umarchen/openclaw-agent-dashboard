# ECS 需求规格说明书 — 事件驱动 ChangeStream 架构改造

> **项目名称**: openclaw-agent-dashboard  
> **特性标识**: ECS (Event-Driven ChangeStream)  
> **版本**: v1.0.0-draft  
> **编写日期**: 2026-05-28  
> **编写人员**: 业务分析师 (BA)  
> **项目模式**: 🟠 增量模式 (Incremental) — 存量系统架构改造  

---

## 0. 需求澄清记录

> 本文档基于 PM 提供的完整需求输入包编写。需求输入包已包含：项目背景、用户痛点、瓶颈根因（经代码解剖确认）、方案核心需求、分期交付计划、事件协议 schema 定义、约束条件及可复用资产清单。以下为关键决策记录：

| 决策项 | 确认结论 | 依据 |
|--------|---------|------|
| 架构方向 | 统一事件总线 `FileChange → Ingest(增量读) → StateStore(内存) → Diff → Event(type, payload)` | 消除双轨制，根治全量推送瓶颈 |
| 分期策略 | C0→C1→C2→C3 四期渐进交付，每期独立可验收 | 降低改造风险，保证每期有可用产出 |
| C0 范围边界 | 仅改 agents 热路径，禁止 `broadcast_full_state()`，timeline 仍 HTTP 拉 | 最小攻击面，先止血 |
| 保留组件 | ChangeTracker、status_cache、前端 merge 逻辑、ErrorHandler、ConfigFortify、input_safety | 已有高质量资产复用 |
| 部署目标 | 最终 promote 到 `/Users/kevin/openclaw-agent-dashboard` 源码仓库 | 不是 staging 演示 |
| 单进程约束 | 单进程单实例，不支持多实例 | 架构设计不需考虑分布式 |

---

## 1. 需求背景与目标

### 1.1 背景

openclaw-agent-dashboard 是 OpenClaw 的多 Agent 可视化看板插件，采用 FastAPI (Python 后端) + React (前端) 技术栈，实时展示 Agent 状态、任务进度和错误分析。系统规模约 ~8,785 行后端代码（39 文件），监听 OpenClaw 运行时产出的 JSON/JSONL 状态文件并通过 WebSocket 推送给前端。

经代码解剖确认，系统当前存在**双轨制数据推送**：

| 路径 | 触发源 | 推送方式 | 数据量 | 计算量 |
|------|--------|---------|--------|--------|
| **路径 A** (full_state) | 文件变更 (watchdog) | 全量推送 | 7 个子域完整数据 | 极重（串行 7+ 数据源，含 2 次全文件扫盘） |
| **路径 B** (state_update) | ~~定时轮询~~ _periodic_broadcast_loop C0 已移除 | ~~增量推送~~ | 仅变化 Agent（4 字段 diff） | ~~轻（缓存优先）~~ |

**用户可感知的痛点**：

1. **首次打开白屏** — 启动时需等待首次 `broadcast_full_state()` 完成（串行 7+ 数据源）
2. **切换面板卡顿** — 文件变更触发全量推送，计算耗时 = 各数据源耗时之和（collaboration + performance 各需全量扫盘）
3. **用久越来越慢** — 无 jsonl offset 记忆，session 文件增长后 `get_session_turns()` 全量解析耗时线性增长

### 1.2 目标

引入 **事件驱动 ChangeStream (ECS) 架构**，将双轨制统一为单一事件总线 `FileChange → Ingest(增量读) → StateStore(内存) → Diff → Event(type, payload)`，实现以下目标：

1. **消除运行时全量推送**：正常运行时 full_state 推送频率降为 0 次/分钟
2. **降低事件传播延迟**：文件变更到前端感知的端到端延迟 < 200ms (p95)
3. **减少无效计算**：jsonl 增量解析、有界并行计算、按需拉取
4. **渐进式交付**：每期改造独立可验收，不中断现有功能

---

## 2. 功能需求列表

### 2.1 核心功能需求

#### [REQ_ECS_001] 事件总线 (EventBus)

**需求描述**: 引入进程内事件总线，作为 file_watcher 与 WebSocket 推送之间的解耦层。file_watcher 不再直接调用 `broadcast_full_state()`，改为将文件变更事件发布到 EventBus；WebSocket 推送层订阅 EventBus 事件并转化为客户端协议。

**详细规格**:

EventBus 需满足以下契约：

| 维度 | 规格 |
|------|------|
| **进程模型** | 单进程内 async queue，基于 `asyncio.Queue` 实现 |
| **事件分类** | 根据变更文件路径自动分类为事件类型（见 [REQ_ECS_002]） |
| **订阅机制** | 支持按事件类型过滤的订阅；支持通配订阅（`*`） |
| **背压控制** | 事件队列满时丢弃 oldest 并记录 metric `eventbus_dropped_total` |
| **防抖复用** | 复用现有 `DebouncedHandler`（1.5s 窗口），防抖后的事件才进入 EventBus |
| **错误隔离** | 单个 subscriber 异常不影响其他 subscriber |

EventBus 消费者（subscriber）清单：

| Subscriber | 订阅事件类型 | 职责 |
|-----------|------------|------|
| AgentStateIngestor | `agent_session_changed`, `run_changed` | 增量读取变更文件，更新 StateStore 中的 agent 状态，产出 `AgentStateChanged` 事件 |
| WS Broadcaster | `full_state`(bootstrap), `AgentStateChanged`, ...(C2 扩展) | 将事件序列化为 WebSocket 协议帧，推送给所有活跃连接 |

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-001-1 | file_watcher 的 `_on_file_changed()` 不再直接调用 `broadcast_full_state()`，改为 `event_bus.publish(event)` | P0 |
| AC-001-2 | EventBus 事件队列满时，记录 `eventbus_dropped_total` metric，丢弃 oldest，不阻塞生产者 | P0 |
| AC-001-3 | 单个 subscriber 抛出异常时，其他 subscriber 继续正常工作 | P0 |
| AC-001-4 | 事件从 publish 到 subscriber 收到的延迟 < 5ms（单进程内，无可测量 I/O） | P1 |

---

#### [REQ_ECS_002] 文件变更事件分类器 (FileChangeClassifier)

**需求描述**: 将文件系统变更事件分类为语义化事件类型，驱动下游差异化处理。避免任何文件变更都触发全量重算。

**详细规格**:

分类规则：

| 变更文件模式 | 事件类型 | 说明 |
|------------|---------|------|
| `agents/{id}/sessions/*.jsonl` (修改) | `agent_session_changed` | Agent 会话文件追加（tail-read 增量） |
| `agents/{id}/sessions/*.jsonl` (创建) | `agent_session_changed` | 新会话创建 |
| `agents/{id}/runs.json` (修改) | `run_changed` | Agent 运行记录变更 |
| `agents/{id}/openclaw.json` (修改) | `config_changed` | Agent 配置变更（C2+ 扩展） |
| `subagents/runs.json` (修改) | `run_changed` | 子 Agent 运行记录变更 |
| `model-failures.log` (修改) | `error_log_changed` | 错误日志变更（C2+ 扩展） |
| 其他未匹配 | `unknown_file_changed` | 记录日志，不触发后续处理 |

事件载荷结构：

```python
@dataclass(frozen=True)
class FileChangeEvent:
    event_type: str          # 上述事件类型之一
    filepath: str            # 变更文件的绝对路径
    agent_id: str | None     # 从路径提取的 agent_id，未匹配则为 None
    timestamp: float         # 变更发生的 UTC 时间戳（time.time()）
    change_type: str          # "modified" | "created" | "deleted"
```

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-002-1 | `agents/agent-001/sessions/session-abc.jsonl` 变更产出事件 `agent_session_changed`，`agent_id="agent-001"` | P0 |
| AC-002-2 | `subagents/runs.json` 变更产出事件 `run_changed`，`agent_id=None` | P0 |
| AC-002-3 | 未匹配的文件路径产出 `unknown_file_changed` 事件，仅记录 debug 日志 | P0 |

---

#### [REQ_ECS_003] StateStore — 集中式内存状态存储

**需求描述**: 引入进程内内存状态存储，作为所有 agent 状态的单一真实来源（Single Source of Truth）。替代 `status_cache` 的运行时缓存职责和 `broadcast_full_state()` 的实时计算依赖。

**详细规格**:

| 维度 | 规格 |
|------|------|
| **存储模型** | `dict[agent_id, AgentState]`，进程内纯内存 |
| **AgentState 结构** | 包含 `status`, `current_task`, `last_active_at`, `error`, `subagents`, `runs_snapshot` 等字段 |
| **写入机制** | 仅由 Ingestor 写入（见 [REQ_ECS_004]）；支持 `update_agent(agent_id, partial_state)` 字段级合并 |
| **读取机制** | 提供 `get_agent(agent_id)`, `get_all_agents()`, `get_changed_since(version)` 接口 |
| **Diff 能力** | 写入时自动触发与上次快照的字段级 diff（复用 ChangeTracker 的 diff 逻辑），产出一组变更字段 |
| **版本号** | 每次写入递增全局 monotonic version，用于客户端增量同步 |
| **冷启动** | 进程启动时触发一次全量读取，填充 StateStore（等价于一次 full_state） |
| **与 status_cache 关系** | StateStore 作为运行时主缓存；status_cache 降级为冷启动辅助/降级回退 |

StateStore 接口契约：

```python
class StateStore:
    async def get_agent(self, agent_id: str) -> AgentState | None
    async def get_all_agents(self) -> dict[str, AgentState]
    async def update_agent(self, agent_id: str, partial: dict) -> list[FieldDiff]
    def get_global_version(self) -> int
    async def get_snapshot(self) -> FullSnapshot  # 用于 FullStateSnapshot 事件
```

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-003-1 | 进程启动后 1 次 full_state 读取，StateStore 填充完整 | P0 |
| AC-003-2 | `update_agent()` 返回本次变更的字段 diff 列表 | P0 |
| AC-003-3 | `get_global_version()` 单调递增，不回退 | P0 |
| AC-003-4 | StateStore miss 时自动 fallback 到 status_cache + data reader | P1 |

---

#### [REQ_ECS_004] AgentStateIngestor — 增量状态摄入器

**需求描述**: 消费 EventBus 的 `agent_session_changed` 和 `run_changed` 事件，对变更文件执行**增量读取**（非全量扫盘），将结果写入 StateStore。

**详细规格**:

处理流程：

```
FileChangeEvent(agent_session_changed, filepath, agent_id)
    │
    ├── (1) 读取变更文件的最后 N 行（tail-read）
    │       N 默认 50 行，可通过配置调整
    │       C0 阶段：无 offset 记忆，每次 tail-read 固定行数
    │       C1 阶段：引入 offset 记忆（见 [REQ_ECS_008]）
    │
    ├── (2) 解析 tail 行，提取 agent 状态字段
    │       status / current_task / last_active_at / error
    │
    ├── (3) 调用 StateStore.update_agent(agent_id, partial_state)
    │       StateStore 返回 field_diffs
    │
    └── (4) 发布 AgentStateChanged 事件到 EventBus
            {type: "AgentStateChanged", agent_id, diffs, version}
```

**关键约束**:
- **C0 阶段**：tail-read 行数固定（默认 50 行），不记录 offset。对于大多数场景（agent 运行中，jsonl 持续追加），50 行足以覆盖最新状态变更。
- **禁止全量扫描**：Ingestor 不得读取完整 jsonl 文件。仅读取 tail 部分。

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-004-1 | jsonl 文件追加写入后，Ingestor 仅读取 tail 部分（≤50 行），不读取完整文件 | P0 |
| AC-004-2 | Ingestor 完成后，StateStore 中对应 agent 状态已更新，且产出了 `AgentStateChanged` 事件 | P0 |
| AC-004-3 | Ingestor 处理单个事件的耗时 < 50ms（agent 数 < 20 时） | P0 |
| AC-004-4 | Ingestor 异常时记录到 error_handler，不影响其他事件处理 | P0 |

---

#### [REQ_ECS_005] WS 协议升级 — 统一事件协议

**需求描述**: WebSocket 推送协议从 `full_state` / `state_update` 双轨制，升级为统一事件协议。`full_state` 仅用于初始化 bootstrap，正常运行全部走类型化事件。

**详细规格**:

**C0 阶段支持的事件类型**：

| 事件类型 | 方向 | 触发时机 | payload 结构 |
|---------|------|---------|-------------|
| `full_state` (C0 bootstrap) | 服务端→客户端 | WS 首连 / 进程重启 | `{agents: [...], subagents: [...], collaboration: {...}, tasks: [...], performance: {...}, workflows: [...], apiStatus: [...]}` |
| `FullStateSnapshot` (C1+, 替代 full_state) | 服务端→客户端 | WS 首连 / 进程重启 / schemaVersion mismatch | 同上，新协议格式 `{type, payload, timestamp}` |
| `AgentStateChanged` | 服务端→客户端 | StateStore 检测到 agent 字段变更 | `{agent_id, diffs: [{field, old_value, new_value}], version}` |

**C2 阶段扩展事件类型**（C0 不实现）：

| 事件类型 | 触发时机 | payload 结构 |
|---------|---------|-------------|
| `CollaborationChanged` | collaboration 数据变更 | `{diffs: [{field, old_value, new_value}]}` |
| `TaskChanged` | 任务增/改/删 | `{change: "added"\|"updated"\|"removed", task_id, task_data}` |
| `TimelineAppended` | timeline 按需拉取完成 | `{agent_id, entries: [...]}` |
| `PerformanceSnapshot` | 慢通道定时推送（30s） | `{agents: {...}, global_stats: {...}}` |

**消息帧格式**：

```json
{
  "type": "AgentStateChanged",
  "payload": {
    "agent_id": "agent-001",
    "diffs": [
      {"field": "status", "old_value": "idle", "new_value": "working"}
    ],
    "version": 42,
    "timestamp": "2026-05-28T14:56:00.000Z"
  }
}
```

**允许 `full_state` 推送的场景（C0 硬约束）**：

| 场景 | 说明 | 是否允许 |
|------|------|---------|
| WebSocket 首次连接 | 客户端 connect 时推送一次完整状态 | ✅ 允许 |
| Dashboard 进程重启后 | 恢复后推送一次完整状态，之后恢复增量 | ✅ 允许（仅 1 次） |
| 客户端 schemaVersion mismatch | 客户端报告的 schemaVersion 与服务端不一致 | ✅ 允许 |
| 文件变更触发 | file_watcher 触发后 | ❌ **禁止** |
| 定时轮询 | `_periodic_broadcast_loop` 周期触发 | ❌ **禁止** |
| 用户手动刷新 | 浏览器 F5 重连 | ✅ 允许（等价于 WS 首连） |

**schemaVersion 协商**：

- 客户端连接时发送 `{"type": "hello", "schemaVersion": 1}` 
- 服务端对比 schemaVersion，不一致则推送 `FullStateSnapshot`
- 一致则推送 `{"type": "ready"}` 表示增量模式就绪

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-005-1 | 正常运行时 `full_state` 推送频率 = 0 次/分钟（除 bootstrap 场景外） | P0 |
| AC-005-2 | WebSocket 首连后，客户端收到且仅收到 1 次 `full_state`（C0 旧格式），后续全部为 `AgentStateChanged` | P0 |
| AC-005-3 | C1+: 客户端发送 `schemaVersion` 不匹配时，服务端推送 `FullStateSnapshot` 并记录 metric | P0 |
| AC-005-4 | 消息帧包含 `timestamp` 字段（UTC ISO 8601） | P0 |

---

#### [REQ_ECS_006] broadcast_full_state() 退役改造

**需求描述**: 将现有 `broadcast_full_state()` 从"被 file_watcher 随意调用"改造为"仅在 bootstrap 场景调用"。C0 阶段保留函数签名，但移除 file_watcher 对它的直接调用。

**详细规格**:

改造前调用链：
```
watchdog.on_modified → DebouncedHandler.trigger → _on_file_changed → broadcast_full_state()
```

改造后调用链：
```
watchdog.on_modified → DebouncedHandler.trigger → _on_file_changed → event_bus.publish(FileChangeEvent)
                                                                          │
                                                                          └→ AgentStateIngestor → StateStore.update_agent → event_bus.publish(AgentStateChanged)
                                                                                                                                               │
                                                                                                                                               └→ WS Broadcaster → send to clients
```

保留 `broadcast_full_state()` 的调用点（C0 阶段）：
1. WebSocket 首连（`send_initial_state` / `websocket_endpoint` on_connect）
2. 进程启动完成后的一次性推送
3. 客户端 schemaVersion mismatch

移除的调用点：
1. `watchers/file_watcher.py` 的 `_on_file_changed()`
2. 任何其他非 bootstrap 场景的调用

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-006-1 | `file_watcher.py` 中不再有任何对 `broadcast_full_state` 的调用或 import | P0 |
| AC-006-2 | `broadcast_full_state()` 仅在 WebSocket on_connect 和启动完成时调用 | P0 |
| AC-006-3 | 在 `broadcast_full_state()` 入口处添加 assert/日志，记录调用来源，便于运行时审计 | P0 |

---

#### [REQ_ECS_007] C0 可观测性 — Metrics 前置

**需求描述**: 在 C0 阶段前置埋点关键性能指标，作为改造效果的量化验证依据和运行时监控。

**详细规格**:

| Metric 名称 | 类型 | 说明 | 测量方式 |
|------------|------|------|---------|
| `dashboard_full_state_total` | Counter | `full_state` / `FullStateSnapshot` 推送次数（按 trigger 标签分类） | WS Broadcaster 在推送时 +1，label: `trigger=bootstrap\|reconnect\|schema_mismatch` |
| `dashboard_state_update_total` | Counter | `AgentStateChanged` 推送次数 | WS Broadcaster 在推送时 +1 |
| `dashboard_ingest_lag_ms` | Histogram | 文件变更到 Ingestor 完成的延迟（不含 debounce） | FileChangeEvent.timestamp → Ingestor 完成时刻差值，单位 ms |
| `dashboard_jsonl_bytes_read_total` | Counter | Ingestor 累计读取的 jsonl 字节数 | Ingestor 每次读取后累加 |
| `dashboard_ws_payload_bytes` | Histogram | WebSocket 单帧推送 payload 大小（`len().encode('utf-8')`） | WS Broadcaster 序列化后字节长度 |
| `dashboard_e2e_update_latency_ms` | Histogram | 文件变更 → 前端 UI 更新延迟（含 debounce，C1+） | 端到端测量 |

Metric 暴露方式：
- C0 阶段：通过现有 REST 端点暴露（新增 `/api/metrics` 端点，或复用 `/api/status`）
- 不引入 Prometheus SDK，使用简单的进程内 Counter/Histogram 实现（避免新增依赖）

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-007-1 | `dashboard_full_state_total` 计数器存在且在每次 full_state 推送时递增 | P0 |
| AC-007-2 | `dashboard_state_update_total` 计数器存在且在每次 `AgentStateChanged` 推送时递增 | P0 |
| AC-007-3 | `dashboard_ingest_lag_ms` 记录 p50/p95 可通过 `/api/metrics` 端点获取 | P0 |
| AC-007-4 | `dashboard_ws_payload_bytes` 记录 p50/p95 可通过 `/api/metrics` 端点获取 | P0 |

---

#### [REQ_ECS_008] JSONL Offset Ingest + Checkpoint (C1)

**需求描述**: 在 C1 阶段为 Ingestor 引入 jsonl offset 记忆和 checkpoint 持久化，消除重复解析和文件增长后的性能劣化。

**详细规格**:

**Offset 追踪**：

| 维度 | 规格 |
|------|------|
| **offset 存储** | 进程内 dict: `{filepath: byte_offset}` |
| **读取方式** | `seek(offset) → read → parse → update offset` |
| **首读** | 无 checkpoint 时，从文件末尾读取最后 50 行（等价于 C0 行为） |
| **后续读** | 从上次 offset 开始读取到文件末尾 |

**Checkpoint 持久化**：

| 维度 | 规格 |
|------|------|
| **存储路径** | `~/.openclaw-agent-dashboard/checkpoints/` |
| **文件格式** | JSON，每行一个 checkpoint 条目：`{"filepath": "...", "offset": 12345, "inode": 456, "mtime": 1700000000.0, "last_read_ts": 1700000001.0}` |
| **写入频率** | 每 10 秒 flush 一次（不每次写入都 fsync） |
| **启动加载** | 进程启动时加载 checkpoint，验证 inode + mtime 有效性 |

**文件 truncate/rotate 检测**：

| 异常场景 | 检测方法 | 恢复策略 |
|---------|---------|---------|
| 文件被截断（size < checkpoint offset） | 比较当前 file size vs checkpoint offset | 重置 offset 为 0，触发一次 full ingest |
| 文件被替换（inode 变化） | 比较当前 inode vs checkpoint inode | 重置 offset 为 0，丢弃旧 checkpoint |
| 文件被轮转（同名新文件） | inode 变化 + 旧文件不存在 | 重置 offset 为 0，正常 ingest |
| Checkpoint 文件损坏 | JSON 解析失败 | 丢弃损坏条目，fallback 到 C0 行为（tail-read） |

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-008-1 | jsonl 持续追加写入场景：Ingestor 仅读取自上次 offset 之后的增量内容 | P1 |
| AC-008-2 | Dashboard 进程重启后：加载 checkpoint，从上次 offset 恢复读取 | P1 |
| AC-008-3 | 文件被截断后：检测到异常，重置 offset，记录 `checkpoint_reset_total` metric | P1 |
| AC-008-4 | 恢复时间：进程重启后 < 2s 可用（展示已有状态），< 5s 完整（agent 数 < 20） | P1 |

---

#### [REQ_ECS_009] 有界并行计算 (C1)

**需求描述**: 将 `get_agents_with_status()` / `get_changed_agents()` 从串行遍历改为有界并行 `asyncio.gather`。

**详细规格**:

| 维度 | 规格 |
|------|------|
| **并行策略** | `asyncio.gather(*tasks, return_exceptions=True)`，每个 agent 的状态计算为一个独立 task |
| **并发上限** | `max_concurrency=min(len(agents), 8)`，可通过配置调整 |
| **异常处理** | 单个 agent 计算异常不阻塞其他 agent，记录到 error_handler |
| **真异步化** | 使用 `asyncio.to_thread()` 包裹同步 I/O 操作（`data/session_reader`, `data/config_reader` 等） |
| **线程安全** | 确认 data reader 在并发调用下的线程安全性；不可行时退回顺序 `await` |

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-009-1 | 10 个 agent 的状态计算并发执行（至少 2 个 agent 同时在进行 I/O） | P1 |
| AC-009-2 | 单个 agent 计算异常时，其余 agent 计算正常完成 | P1 |
| AC-009-3 | 并发计算耗时 < 串行计算耗时的 50%（agent 数 ≥ 5 时） | P1 |

---

#### [REQ_ECS_010] Collaboration/Performance 解耦 — 增量事件 (C2)

**需求描述**: 将 collaboration 和 performance 从 full_state 的子域拆分为独立增量事件，按需推送。

**详细规格**:

**Collaboration 增量化**：

| 维度 | 规格 |
|------|------|
| **事件类型** | `CollaborationChanged` |
| **diff 粒度** | 字段级 diff（对比上次 collaboration 快照的差异字段） |
| **触发条件** | agent session 变更且影响 collaboration 数据时 |
| **不再走 full_state** | collaboration 数据从 `FullStateSnapshot` payload 中移除，独立为 `CollaborationChanged` 事件 |

**Tasks 增量化**：

| 维度 | 规格 |
|------|------|
| **事件类型** | `TaskChanged` |
| **diff 粒度** | 任务级 diff（add/update/remove 三种操作） |
| **触发条件** | runs.json 变更时，diff 产出新增/更新/移除的任务 |
| **不再走 full_state** | tasks 数据从 `FullStateSnapshot` payload 中移除，独立为 `TaskChanged` 事件 |

**Timeline 按需拉取**：

| 维度 | 规格 |
|------|------|
| **拉取方式** | 前端主动请求（REST 或 WS 请求），不主动推送 |
| **游标参数** | `?since=turnId` 或 `?after_ts=<unix_ts>` |
| **C0/C1 兼容** | C0/C1 阶段 timeline 仍通过 HTTP GET 拉取，保持不变 |

**Performance 慢通道**：

| 维度 | 规格 |
|------|------|
| **事件类型** | `PerformanceSnapshot` |
| **推送频率** | 30s poll（独立慢通道，不跟随文件变更） |
| **不再走 full_state** | performance 数据从 `FullStateSnapshot` payload 中移除，独立为 `PerformanceSnapshot` 事件 |

**FullStateSnapshot 瘦身**：

C2 完成后，`FullStateSnapshot` 仅包含 bootstrap 必要数据：

```json
{
  "agents": [...],
  "subagents": [...],
  "apiStatus": [...],
  "schemaVersion": 2
}
```

collaboration、tasks、performance、workflows 通过各自增量事件独立交付。

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-010-1 | 文件变更后不再有包含 collaboration/tasks/performance 的 full_state 推送 | P2 |
| AC-010-2 | `CollaborationChanged` 事件仅包含变更字段，payload 大小 < 原全量 collaboration 的 20% | P2 |
| AC-010-3 | `TaskChanged` 事件仅包含 add/update/remove 的任务，不包含未变化的任务 | P2 |
| AC-010-4 | `PerformanceSnapshot` 每 30s 推送一次，不跟随文件变更频率 | P2 |
| AC-010-5 | Timeline 通过 REST 拉取，支持 `?since=turnId` 游标参数 | P2 |

---

#### [REQ_ECS_011] 前端统一 Patch 模型 + 虚拟滚动 (C3)

**需求描述**: 前端从 `full_state` 全量替换模型升级为统一 Patch 模型，所有事件类型共享同一套 state merge 逻辑。对 50+ agent 场景引入虚拟滚动。

**详细规格**:

**统一 Patch 模型**：

| 维度 | 规格 |
|------|------|
| **核心原则** | 所有事件都描述"什么变了"，而非"全部是什么" |
| **merge 策略** | 复用并扩展现有 `agents_update` merge 逻辑到所有 entity 类型 |
| **冲突处理** | 服务端 version 单调递增，客户端丢弃 version ≤ 本地 version 的事件 |
| **bootstrap** | C0: 首连时 `full_state`（旧格式）作为初始状态；C1+: `FullStateSnapshot`（新格式） |

**entity merge 规则**：

| Entity 类型 | merge 策略 | 说明 |
|-----------|----------|------|
| agents | 按 agent_id merge，字段级 patch | 复用现有逻辑 |
| subagents | 按 run_id merge | C2 扩展 |
| tasks | add → 追加, update → 按 task_id 替换, remove → 按 task_id 删除 | C2 扩展 |
| collaboration | 字段级 merge | C2 扩展 |
| performance | 整包替换（30s 快照语义） | C2 扩展 |

**虚拟滚动**：

| 维度 | 规格 |
|------|------|
| **适用场景** | Agent 列表视图（当 agent 数 > 20 时自动启用） |
| **实现** | 固定行高虚拟列表，仅渲染可视区域 + buffer |
| **交互** | 保持键盘导航和搜索过滤功能 |
| **性能目标** | 50+ agent 场景下列表滚动 FPS ≥ 55 |

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-011-1 | 前端所有 entity 类型的状态更新走统一 Patch 模型，无全量替换（bootstrap 除外） | P3 |
| AC-011-2 | 客户端丢弃 version ≤ 本地 version 的事件（防重放/乱序） | P3 |
| AC-011-3 | 50 个 agent 场景下，Agent 列表滚动 FPS ≥ 55 | P3 |
| AC-011-4 | 50 个 agent 场景下，切换 Agent 详情面板无明显卡顿 | P3 |

---

### 2.2 配置需求

#### [REQ_ECS_012] ECS 相关配置项

**需求描述**: 为 ECS 架构引入新的配置项，集成到现有 ConfigFortify 配置中心。

**新增配置项**:

| 配置项 | 环境变量 | 类型 | 默认值 | 说明 |
|-------|---------|------|--------|------|
| `event_bus_queue_size` | `ECS_EVENT_BUS_QUEUE_SIZE` | int | 1024 | EventBus 事件队列容量 |
| `ingest_tail_lines` | `ECS_INGEST_TAIL_LINES` | int | 50 | C0 阶段 tail-read 行数 |
| `ingest_max_concurrency` | `ECS_INGEST_MAX_CONCURRENCY` | int | 8 | C1 阶段有界并行上限 |
| `checkpoint_dir` | `ECS_CHECKPOINT_DIR` | str | `~/.openclaw-agent-dashboard/checkpoints/` | C1 checkpoint 存储目录 |
| `checkpoint_flush_interval_sec` | `ECS_CHECKPOINT_FLUSH_INTERVAL` | float | 10.0 | C1 checkpoint flush 间隔（秒） |
| `performance_snapshot_interval_sec` | `ECS_PERF_SNAPSHOT_INTERVAL` | float | 30.0 | C2 performance 慢通道推送间隔 |
| `full_state_schema_version` | `ECS_SCHEMA_VERSION` | int | 2 | 协议 schema 版本号 |
| `max_agent_parallel` | `ECS_MAX_AGENT_PARALLEL` | int | 8 | C1 状态计算并行上限 |

**验收条件**:
| 编号 | 条件 | 优先级 |
|-----|------|--------|
| AC-012-1 | 所有新配置项集成到 ConfigFortify frozen dataclass，支持环境变量覆盖 | P0 |
| AC-012-2 | 不设置任何环境变量时，所有配置项使用默认值 | P0 |

---

## 3. 非功能需求

### 3.1 性能指标

| 指标 | 目标值 | 测量方法 |
|-----|--------|---------|
| full_state 推送频率（正常运行） | 0 次/分钟 | `dashboard_full_state_total` counter，label=bootstrap 的除外 |
| ingest lag (文件变更→Ingestor 完成) | p95 < 200ms | `dashboard_ingest_lag_ms` histogram |
| WS payload 大小 (state_update) | p95 < 2KB | `dashboard_ws_payload_bytes` histogram |
| WS payload 大小 (full_state bootstrap) | < 500KB（agent 数 < 20） | `dashboard_ws_payload_bytes` histogram |
| 切换 Agent 详情面板响应 | p95 < 200ms | 前端性能 API (PerformanceObserver) |
| 进程启动可用时间 (C1) | < 2s 可用，< 5s 完整 | 端到端测量（agent 数 < 20） |
| 并行计算加速比 (C1) | ≥ 2x vs 串行（agent 数 ≥ 5） | 对比 `get_changed_agents()` 耗时 |

### 3.2 可靠性指标

| 指标 | 目标值 | 说明 |
|-----|--------|------|
| EventBus 事件丢失率 | < 0.01%（队列满丢弃场景） | 仅在极端压力下允许丢弃 |
| StateStore 数据一致性 | 100% 文件系统为最终一致 | StateStore 可能有短暂延迟，但最终一致 |
| Checkpoint 完整性 | 进程崩溃后 ≤ 10s 数据丢失 | 受 flush_interval 约束 |
| 降级可用性 | StateStore 故障时 fallback 到 status_cache + data reader | 不可用优于错误 |

### 3.3 安全性需求

| 需求 | 说明 |
|-----|------|
| 输入校验 | 保留现有 `input_safety` 路径逃逸防御，新增配置项同样通过 ConfigFortify 解析 |
| 错误脱敏 | 保留现有 `safe_api_error` 机制，EventBus 错误信息同样脱敏后输出 |
| Checkpoint 文件权限 | checkpoint 文件权限 0600（仅 owner 可读写） |

---

## 4. 影响范围分析

### 4.1 新增模块

| 模块路径 | 职责 | 说明 |
|---------|------|------|
| `event_bus.py` | 进程内事件总线 | asyncio.Queue + 发布/订阅/分类/背压 |
| `state_store.py` | 集中式内存状态存储 | AgentState CRUD + diff-on-write + 版本管理 |
| `file_change_classifier.py` | 文件变更→语义事件分类 | 路径模式匹配 + FileChangeEvent 构建 |
| `ingest/agent_ingestor.py` | Agent 状态增量摄入 | 消费 EventBus 事件，增量读取 jsonl，写入 StateStore |
| `metrics.py` | 进程内轻量 Metrics | Counter / Histogram 实现 + REST 暴露端点 |

### 4.2 修改模块

| 模块路径 | 修改内容 | 影响程度 |
|---------|---------|---------|
| `watchers/file_watcher.py` | `_on_file_changed()` 改为 `event_bus.publish()`；移除 `broadcast_full_state` 调用 | 🔴 重大 |
| `api/websocket.py` | 新增 EventBus subscriber（WS Broadcaster）；`send_initial_state` 保留为 bootstrap；**`_periodic_broadcast_loop` C0 一并移除**；schemaVersion 协商延到 C1 | 🔴 重大 |
| `status/status_calculator.py` | 数据源从 data reader 切换为 StateStore；`get_changed_agents()` 真异步化 + 有界并行 (C1) | 🟠 中度 |
| `status/status_cache.py` | 降级为冷启动/降级回退缓存，运行时主缓存职责由 StateStore 承担 | 🟡 轻度 |
| `status/change_tracker.py` | MAX_SNAPSHOTS 修复；diff 逻辑复用到 StateStore 的 diff-on-write | 🟡 轻度 |
| `core/error_handler.py` | `run_with_retry()` 异步化 (C1)；统计持久化到 StateStore (C2) | 🟠 中度 |
| `core/config_fortify.py` | 新增 ECS 相关配置项（8 个） | 🟡 轻度 |
| `api/errors.py` | 数据源切换到 StateStore；消除 `parse_failure_log()` 重复调用 | 🟠 中度 |
| `api/collaboration.py` | 拆分为独立事件源 (C2)；消除全量扫盘依赖 | 🟠 中度 |
| `api/performance.py` | 拆分为独立慢通道 (C2)；消除全量扫盘依赖 | 🟠 中度 |
| `data/session_reader.py` | 增加 tail-read 接口 (C0/C1)；全量解析函数增加行数预算 (C2) | 🟡 轻度 |
| `data/config_reader.py` | `load_config()` 增加 TTL 缓存 | 🟡 轻度 |
| `data/subagent_reader.py` | `load_subagent_runs()` 增加 mtime 感知 LRU 缓存 | 🟡 轻度 |
| `mechanism_reader.py` | 数据源切换到 StateStore | 🟠 中度 |

### 4.3 API 变更

| 变更类型 | API | 说明 |
|---------|-----|------|
| **新增** | `GET /api/metrics` | 返回进程内 metrics 快照（JSON） |
| **修改** | WebSocket 消息帧格式 | 从 `{type: "full_state"/"state_update", data: {...}}` 升级为 `{type: "<EventType>", payload: {...}, timestamp: "..."}` |
| **修改** | WebSocket 握手 | 新增 `{"type": "hello", "schemaVersion": N}` 客户端→服务端消息 |
| **修改** | `GET /api/agents` | 内部数据源从 data reader 切换到 StateStore，接口签名不变 |
| **修改** | `GET /api/subagents` | 内部数据源从 data reader 切换到 StateStore，接口签名不变 |
| **修改** (C2) | `GET /api/timeline` | 新增 `?since=turnId` 游标参数 |
| **不变** | 其余 REST 端点 | `/errors`, `/chains`, `/api_status`, `/workflows`, `/mechanisms` 等接口签名不变，内部数据源可能切换 |

### 4.4 数据库变更

N/A (不适用) — 系统无数据库，状态存储为进程内内存。

---

## 5. 兼容性分析

### 5.1 向后兼容

| 维度 | 兼容性策略 |
|------|----------|
| **前端适配** | C0 阶段 bootstrap 仍推 `type: "full_state"`（旧格式）。增量推 `AgentStateChanged`（新格式），前端需约 20 行最小改动（RealtimeDataManager 新增 case，映射到现有 agents_update merge）。`FullStateSnapshot` 延到 C1 引入。 |
| **REST API 向后兼容** | 所有现有 REST 端点接口签名不变。内部实现从 data reader 切换到 StateStore 对调用方透明。 |
| **watchdog 配置兼容** | 现有 watchdog + 轮询降级 + 自动恢复机制完整保留，EventBus 在 watchdog 之上工作，不改变文件监听行为。 |
| **status_cache 兼容** | status_cache 不删除，降级为冷启动辅助。C0 阶段 StateStore miss 时 fallback 到 status_cache + data reader，保证可用性。 |

### 5.2 版本依赖

| 组件 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.9+ | 维持不变（asyncio.Queue, dataclass, typing 为标准库） |
| FastAPI | 维持现有版本 | 不引入新依赖 |
| watchdog | 维持现有版本 | 不改变文件监听依赖 |
| React (前端) | 维持现有版本 | C0/C1 前端改动极小，C2/C3 需前端适配 |

**不新增外部依赖**：C0/C1/C2 不引入新的第三方库。Metrics 使用进程内简单实现，不引入 Prometheus SDK。

### 5.3 升级路径

```
当前状态 ──→ C0 完成 ──→ C1 完成 ──→ C2 完成 ──→ C3 完成
   │             │            │            │            │
   │             │            │            │            └─ 前端全面适配
   │             │            │            └─ collaboration/tasks/performance 增量化
   │             │            └─ jsonl offset + checkpoint + 并行计算
   │             └─ agents 热路径增量化，禁止运行时 full_state
   └─ 双轨制，full_state + state_update 并存
```

每期升级：
1. **无破坏性变更**：每期改造完成后，系统功能与改造前等价
2. **可独立回滚**：每期改造在独立 git 分支/commit 集中，可独立 revert
3. **前端渐进适配**：C0/C1 前端仅新增事件类型处理（可选），C2/C3 前端才需要强制适配

---

## 6. 验收标准

### 6.1 功能验收

| 编号 | 验收项 | 验收方法 | 责任方 |
|-----|--------|---------|--------|
| FV-001 | 文件变更后只推送 `AgentStateChanged`，不推送 `FullStateSnapshot` | 模拟 agent 运行（jsonl 追加），观察 WS 消息流，确认无 full_state | Dev + QA |
| FV-002 | C0: WebSocket 首连后收到且仅收到 1 次 `full_state`（旧格式）；C1+: 收到 1 次 `FullStateSnapshot` | 新建 WS 连接，记录所有收到的消息类型 | Dev + QA |
| FV-003 | 进程重启后允许 1 次 `FullStateSnapshot`，之后恢复增量 | 重启 Dashboard，观察 WS 消息流 | Dev + QA |
| FV-004 | `file_watcher` 不再调用 `broadcast_full_state` | 代码审查：grep `broadcast_full_state` in `watchers/` 应返回 0 结果 | Dev |
| FV-005 | EventBus 事件队列满时丢弃 oldest，记录 metric | 压力测试：高频文件变更淹没 EventBus，确认 metric 递增 | QA |
| FV-006 | schemaVersion mismatch 触发 full_state | 客户端发送旧版 schemaVersion，确认服务端推送 full_state | Dev + QA |
| FV-007 | Metrics 端点 `/api/metrics` 返回所有 5 个 metric 的当前值 | curl `/api/metrics`，验证 JSON 结构和数值 | QA |
| FV-008 | jsonl offset checkpoint 正确读写 (C1) | 重启 Dashboard，对比 checkpoint 文件 offset 与实际文件大小 | Dev + QA |
| FV-009 | 文件 truncate 后自动恢复 (C1) | 手动截断 jsonl 文件，确认 offset 重置和重新 ingest | Dev + QA |
| FV-010 | collaboration/tasks/performance 独立事件 (C2) | 模拟文件变更，确认收到对应增量事件而非 full_state | Dev + QA |
| FV-011 | Timeline 支持 `?since=turnId` 游标 (C2) | curl `/api/timeline?since=<turnId>`，验证返回结果从指定 turnId 之后 | Dev + QA |
| FV-012 | 50+ agent 虚拟滚动流畅 (C3) | 构造 50 个 agent 场景，验证列表滚动 FPS ≥ 55 | QA |

### 6.2 性能验收

| 编号 | 验收项 | 目标 | 验收方法 |
|-----|--------|-----|---------|
| PV-001 | 正常运行 full_state 推送频率 | 0 次/分钟 | `dashboard_full_state_total` counter 观察 5 分钟，增量 = 0（排除 bootstrap） |
| PV-002 | ingest lag (p95) | < 200ms | `dashboard_ingest_lag_ms` histogram p95 |
| PV-003 | WS payload AgentStateChanged 大小 (p95) | < 2KB | `dashboard_ws_payload_bytes` histogram p95 |
| PV-004 | 切换 Agent 详情面板延迟 (p95) | < 200ms | 前端 PerformanceObserver 测量 |
| PV-005 | 进程启动可用时间 (C1) | < 2s 可用，< 5s 完整 | 端到端测量 |
| PV-006 | 并行计算加速比 (C1) | ≥ 2x vs 串行 | 对比串行/并行 `get_changed_agents()` 耗时 |
| PV-007 | 50+ agent 滚动 FPS (C3) | ≥ 55 | 前端 PerformanceObserver |

### 6.3 兼容性验收

| 编号 | 验收项 | 验收方法 |
|-----|--------|---------|
| CV-001 | C0 前端约 20 行最小改动后 AgentStateChanged 可增量更新 | RealtimeDataManager 新增 AgentStateChanged case，agent card 增量刷新 |
| CV-002 | 所有 REST 端点接口签名不变 | 对比改造前后 Swagger/OpenAPI spec |
| CV-003 | 现有 watchdog + 轮询降级 + 自动恢复机制正常 | 模拟 watchdog 故障，确认自动降级和恢复 |

---

## 7. 依赖关系

### 7.1 需求依赖图

```
[REQ_ECS_001] EventBus
    │
    ├── [REQ_ECS_002] FileChangeClassifier
    │       │
    │       └── [REQ_ECS_004] AgentStateIngestor
    │               │
    │               └── [REQ_ECS_003] StateStore
    │                       │
    │                       └── [REQ_ECS_005] WS 协议升级
    │                               │
    │                               └── [REQ_ECS_006] broadcast_full_state 退役
    │
    └── [REQ_ECS_012] 配置项 ──→ ConfigFortify

[REQ_ECS_007] Metrics (与 C0 功能需求并行开发)

C1 依赖:
    [REQ_ECS_008] JSONL Offset + Checkpoint (依赖 [REQ_ECS_003], [REQ_ECS_004])
    [REQ_ECS_009] 有界并行计算 (依赖 [REQ_ECS_003])

C2 依赖:
    [REQ_ECS_010] Collaboration/Performance 解耦 (依赖 C0 全部 + [REQ_ECS_003])

C3 依赖:
    [REQ_ECS_011] 前端 Patch 模型 + 虚拟滚动 (依赖 C2 全部)
```

### 7.2 实施优先级

| 分期 | REQ 范围 | 优先级 | 预估工作量 | 核心交付 |
|------|---------|--------|----------|---------|
| **C0** | REQ_ECS_001~007, REQ_ECS_012 | P0 | 中 | EventBus + StateStore + Ingestor + WS 协议 + broadcast 退役 + Metrics |
| **C1** | REQ_ECS_008, REQ_ECS_009 | P1 | 中 | JSONL offset + checkpoint + 并行计算 |
| **C2** | REQ_ECS_010 | P2 | 中 | collaboration/tasks/performance 增量化 + timeline 按需拉 |
| **C3** | REQ_ECS_011 | P3 | 中 | 前端 Patch 模型 + 虚拟滚动 |

---

## 8. 风险与缓解

| # | 风险 | 严重度 | 描述 | 缓解措施 | 关联 REQ |
|---|------|--------|------|---------|---------|
| R-01 | **前端适配遗漏** | 🔴 高 | 细粒度事件拆分后，前端遗漏处理某类事件导致状态不一致 | C0 阶段 bootstrap 仍推 `full_state`（旧格式），前端约 20 行最小改动处理 `AgentStateChanged`；遗漏处理时下次文件变更会重新触发摄入 | REQ_ECS_005 |
| R-02 | **error_handler 异步化影响面** | 🔴 高 | `run_with_retry()` 被 14+ 文件使用，异步化后所有调用方必须 `await` | 提供同步 (`run_with_retry`) 和异步 (`run_with_retry_async`) 两个版本；同步版本保留，不破坏现有调用方 | REQ_ECS_009 |
| R-03 | **StateStore 数据一致性** | 🟡 中 | EventBus 事件驱动更新，文件变化到 StateStore 更新存在延迟窗口 | 保留 status_cache 作为 fallback；REST 端点查询 StateStore miss 时直接读 data reader | REQ_ECS_003 |
| R-04 | **jsonl offset 错乱** | 🟡 中 | checkpoint 损坏或文件操作导致 offset 跳过/重复数据 | offset 溢出检测（offset > file size 则重置）；checkpoint JSON 校验；损坏时 fallback 到 C0 行为 | REQ_ECS_008 |
| R-05 | **并发文件 I/O 线程安全** | 🟡 中 | C1 并行化后多个 agent 同时读取文件，data reader 无锁机制 | C1 优先验证 data reader 线程安全性；不可行时退回顺序 `await` 保持串行语义 | REQ_ECS_009 |
| R-06 | **改造回归** | 🟡 中 | 15+ 文件改造范围大，回归测试覆盖难度高 | 每期独立 commit/分支；改造前建立现有 API 契约测试套件 | 全局 |
| R-07 | **内存占用增长** | 🟢 低 | StateStore 在内存中维护所有 agent 状态 | Agent 数 < 20 时内存增量 < 1MB；复用 status_cache 的 RSS 保护机制 | REQ_ECS_003 |

---

## 9. 附录

### 9.1 技术选型说明

| 选型 | 决策 | 理由 |
|------|------|------|
| EventBus 实现 | asyncio.Queue | 单进程内足够，无跨进程需求；零新增依赖 |
| StateStore 实现 | 纯内存 dict + dataclass | 性能最优；Agent 数 < 20 时数据量极小（< 1MB） |
| Metrics 实现 | 进程内 Counter/Histogram | 避免 Prometheus SDK 依赖；通过 REST 端点暴露足够 |
| 前端虚拟滚动 | 复用现有列表组件 + 虚拟化层 | 最小改动；固定行高降低实现复杂度 |
| Checkpoint 格式 | JSON 文本文件 | 人类可读可调试；文件小（< 10KB），性能不是问题 |

### 9.2 相关文件路径

| 文件 | 路径 | 说明 |
|-----|------|------|
| 源码仓库 | `/Users/kevin/openclaw-agent-dashboard` | 最终 promote 目标 |
| VRT 工作区 | `/Users/kevin/.openclaw/workspace/virtual-rnd-team/projects/openclaw-agent-dashboard/` | 开发工作区 |
| 解剖报告 | `.staging/legacy_code_anatomy.md` | 存量代码解剖 |
| 本规格说明书 | `.staging/specs/ECS_spec.md` | 本文档 |
| Checkpoint 目录 | `~/.openclaw-agent-dashboard/checkpoints/` | C1 checkpoint 存储 |

### 9.3 参考文档

| 文档 | 说明 |
|------|------|
| `.staging/legacy_code_anatomy.md` | openclaw-agent-dashboard 全局存量代码解剖报告（2026-05-28） |
| 现有 `watchers/file_watcher.py` | watchdog 文件监听 + 防抖 + 轮询降级 + 自动恢复实现 |
| 现有 `status/change_tracker.py` | Agent 状态 diff 检测实现（将被复用/升级） |
| 现有 `status/status_cache.py` | TTL + mtime 双验证缓存（将降级为冷启动辅助） |
| 现有 `core/config_fortify.py` | frozen dataclass + lru_cache 配置中心（将扩展） |
| 现有 `core/error_handler.py` | 统一错误处理框架（将异步化） |

### 9.4 术语表

| 术语 | 定义 |
|------|------|
| **ECS** | Event-Driven ChangeStream，本改造项目的架构代号 |
| **EventBus** | 进程内事件总线，解耦文件监听与数据推送 |
| **StateStore** | 集中式内存状态存储，所有 agent 状态的 Single Source of Truth |
| **Ingestor** | 增量状态摄入器，消费文件变更事件并更新 StateStore |
| **FullStateSnapshot** | 初始化/恢复场景使用的全量状态快照事件 |
| **AgentStateChanged** | Agent 状态字段变更的增量事件 |
| **Checkpoint** | jsonl 读取 offset 的持久化记录 |
| **Bootstrap** | WebSocket 首连/重启时的初始化全量状态推送 |
| **双轨制** | 当前系统的 full_state + state_update 两条独立推送路径 |

---

**文档版本**: v1.0.0-draft  
**最后更新**: 2026-05-28  
**审核状态**: 待 PM 审核  
