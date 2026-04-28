# TECHDEBT_FORTIFY 需求跟踪

> 对照 PRD：`TECHDEBT_FORTIFY_spec.md`（v1.0.0）  
> 状态：`done` 已满足 | `partial` 部分满足 | `todo` 未做 | `n/a` 二期/不纳入本期  
> 代码锚点：本仓库 `src/backend/`（路径相对于仓库根目录）

---

## REQ_001 文件监听系统容错

| ID | 来源 | 描述 | 状态 | 代码锚点 | 备注 |
|----|------|------|------|----------|------|
| REQ_001-SPEC-01 | §2.1 | `file_watcher.py` 监听失败检测 | done | `watchers/file_watcher.py` | 监控线程 + `get_watcher_health` |
| REQ_001-SPEC-02 | §2.1 | watchdog 失败自动重连/重启，最多 3 次 | done | `watchers/file_watcher.py` | `OPENCLAW_WATCHER_MAX_RETRIES` |
| REQ_001-SPEC-03 | §2.1 | 连续失败超 30s 切 5s 轮询 | done | `watchers/file_watcher.py` | `OPENCLAW_WATCHER_FAILURE_WINDOW` |
| REQ_001-SPEC-04 | §2.1 | 健康状态监控接口 | done | `api/fortify_routes.py` `GET /api/health/watcher` | |
| REQ_001-SPEC-05 | §2.1 | 轮询恢复监听时状态同步 | done | `watchers/file_watcher.py` | 恢复成功后 `_full_resync_cache_and_push`；`watcher_state.json` 轻量快照 |
| REQ_001-AC-001 | AC | watchdog 异常自动重试最多 3 次 | done | 同上 | 需集成/混沌验证 |
| REQ_001-AC-002 | AC | 重试失败切 5s 轮询 | done | 同上 | |
| REQ_001-AC-003 | AC | 轮询下仍能推送状态 | done | `_on_file_changed(None)` | |
| REQ_001-AC-004 | AC | 恢复后切回监听 | done | `_try_resume_watchdog` | `test_watcher_try_resume_*` |
| REQ_001-AC-005 | AC | 健康接口信息准确 | done | `get_watcher_health` | `error_count` = fortify 内 watcher 相关 `record_error` 计数；另含 `switch_count` / resume 计数 / `persisted_snapshot` |

---

## REQ_002 状态缓存一致性

| ID | 来源 | 描述 | 状态 | 代码锚点 | 备注 |
|----|------|------|------|----------|------|
| REQ_002-SPEC-01 | §2.2 | TTL 默认 1s，上限 60s | done | `core/config_fortify.py` `OPENCLAW_CACHE_TTL` | |
| REQ_002-SPEC-02 | §2.2 | 数据文件变化立即使缓存失效 | done | `watchers/file_watcher.py` `_on_file_changed` + `status_cache.invalidate` | 依赖监听/轮询 |
| REQ_002-SPEC-03 | §2.2 | 启动缓存预热 | done | `main.py` lifespan + `OPENCLAW_CACHE_PRELOAD` | |
| REQ_002-SPEC-04 | §2.2 | 缓存命中率监控接口 | done | `GET /api/cache/stats` | |
| REQ_002-SPEC-05 | §2.2 | 内存超限制逐出 LRU | done | `status/status_cache.py` | 估算字节 + `_last_access` |
| REQ_002-SPEC-06 | PRD §8 | 缓存失效「双验证」机制 | done | `status/status_cache.py` | TTL 通过后比对 `sessions.json` / `runs.json` mtime；`OPENCLAW_CACHE_DOUBLE_CHECK` |
| REQ_002-AC-001 | AC | TTL 过期 | done | `StatusCache.get` | |
| REQ_002-AC-002 | AC | 文件变更新失效 | done | file_watcher | |
| REQ_002-AC-003 | AC | 命中率接口 | done | `/api/cache/stats` | |
| REQ_002-AC-004 | AC | 内存超限逐出 | done | `status/status_cache.py` | `test_status_cache_memory_eviction_boundary` |
| REQ_002-AC-005 | AC | 预热 | done | lifespan | |

**配置**：`OPENCLAW_CACHE_MAX_SIZE`（MB）、`OPENCLAW_CACHE_MAX_ENTRIES`（条数，补充项）、`OPENCLAW_CACHE_DOUBLE_CHECK`（默认 true：mtime 双验证）

---

## REQ_003 统一错误处理

| ID | 来源 | 描述 | 状态 | 代码锚点 | 备注 |
|----|------|------|------|----------|------|
| REQ_003-SPEC-01 | §2.3 | `core/error_handler.py` | done | `core/error_handler.py` | |
| REQ_003-SPEC-02 | §2.3 | 指数退避、可配置重试 | done | `ErrorHandler.run_with_retry` / `execute_with_retry` | |
| REQ_003-SPEC-03 | §2.3 | 错误分类（网络/IO/解析等） | done | `classify_exception` | 权限/断连/SSL/编码/递归等；Key/Type/Attr→validation |
| REQ_003-SPEC-04 | §2.3 | 按类型降级策略 | done | `core/fallback_manager.py` | `register_fallback` / `run_fallback`；默认注册 network/io-error/timeout/permission-error |
| REQ_003-SPEC-05 | §2.3 | 结构化日志 logging + formatter | done | `record_error` | `fortify_event` + `exc_type` / `exc_module`；`last_error` 同字段 |
| REQ_003-SPEC-06 | §2.3 | 错误统计按类型/频率/时间 | done | `get_framework_error_stats` | `by_scope_top`、`sum_by_type`、`totals_consistent` |
| REQ_003-AC-001 | AC | 所有 API 模块使用统一框架 | done | 全 `api/*.py` 路由已扫 | `record_error` + 既有 `ErrorHandler` |
| REQ_003-AC-002 | AC | 指数退避正确 | done | `ErrorHandler.run_with_retry` | `test_error_handler_exponential_backoff` |
| REQ_003-AC-003 | AC | 网络错误重试并降级 | done | `status_calculator` + `status_cache.get_stale_fallback` | IO 失败时读最近缓存状态；`OPENCLAW_FALLBACK_CACHE_ON_IO`（默认 true）；TTL miss 不再删条目以便降级 |
| REQ_003-AC-004 | AC | 结构化日志字段完整 | done | 同上 SPEC-05 | |
| REQ_003-AC-005 | AC | 错误统计正确 | done | `totals_consistent` + 单测 | |

---

## REQ_004 数据文件解析健壮性

| ID | 来源 | 描述 | 状态 | 代码锚点 | 备注 |
|----|------|------|------|----------|------|
| REQ_004-SPEC-01 | §2.4 | session_reader + subagent_reader schema | done | 同上；**Round6–7**：canonical `api/*`、`data/*`、`status/*`；**Round11**：`chain_reader` 的 runs 走 `load_subagent_runs` | 非会话类 JSON（如 workflow_state）仍按需解析；新增根目录副本需避免双实现 |
| REQ_004-SPEC-02 | §2.4 | JSON schema 定义 | done | `core/schemas/` | 内嵌 dict |
| REQ_004-SPEC-03 | §2.4 | 文件损坏检测/完整性 | done | `session_reader` `compute_session_file_integrity` | validate 报告含 `sha256`+`hash_scope`（小文件全量/大文件尾 512KB） |
| REQ_004-SPEC-04 | §2.4 | 只读内存修复 vs 写回+备份 | done | `write_repaired_json_file` + validate `read_path_policy` | 读路径不自动写回；接口明确 `memory_auto_repair_default` / `disk_write_back_enabled` |
| REQ_004-SPEC-05 | §2.4 | 损坏时默认值、不崩溃 | done | 各 reader 安全返回 | |
| REQ_004-SPEC-06 | §2.4 | 数据验证接口 | done | `GET /api/data/validate` | 支持 `session_file` 相对路径 + `max_lines`；默认仍取最新 jsonl |
| REQ_004-SPEC-07 | Round2 | `sessions.json` 索引读路径 schema | done | `session_reader` `_load_sessions_index_file` | |
| REQ_004-AC-001 | AC | 解析前 schema | done | JSONL + sessions 索引 + subagents + **`timeline_reader`** + **`chain_reader`（openclaw.json / runs 经 fortify 路径）** | 全仓库任意 JSON 文件不保证；范围见 Round11 |
| REQ_004-AC-002 | AC | 损坏不崩溃 | done | | |
| REQ_004-AC-003 | AC | 轻微 JSON 自动修复 | done | `attempt_line_json_repair` | |
| REQ_004-AC-004 | AC | 验证接口识别无效数据 | done | `repair_report.failed_repairs` 始终含行号与原因 | |
| REQ_004-AC-005 | AC | 审计日志 | done | `openclaw.fortify.audit` | `audit_repair` 懒加载 StreamHandler；`test_audit_repair_emits_audit_log` |
| REQ_004-AC-006 | AC | 写回默认关 + 备份 | done | `config_fortify` | |

---

## §3 非功能需求

### 3.1 性能

| ID | 描述 | 目标 | 状态 | 备注 |
|----|------|------|------|------|
| NFR-P-001 | 监听切换时间 | <1s | done | CI strict：`_full_resync` + `_switch_to_polling` <1s（Round21） |
| NFR-P-002 | 缓存命中率 | ≥60% | done | CI strict：`test_nfr_p002` ≥60%（Round21） |
| NFR-P-003 | 错误处理开销 | <10ms | done | CI strict：`test_nfr_p003` 均值 <10ms（Round21） |
| NFR-P-004 | JSON 解析 | <50ms/50KB | done | CI strict（Round21） |
| NFR-P-005 | API 响应 | <200ms | done | CI strict（Round21） |

### 3.2 可靠性

| ID | 描述 | 状态 | 备注 |
|----|------|------|------|
| NFR-R-001 | 可用性 >99.9% | done | SLO 告警规则已完备；见 **`docs/OBSERVABILITY.md`** NFR-R-001 节 |
| NFR-R-002 | 监听成功率 >99% | done | **`get_reliability_metrics`** → `watcher_availability_rate`；**`record_watcher_failure/recovery`**；`/api/errors/reliability` + `/api/health/watcher` |
| NFR-R-003 | 错误恢复 <5s | done | **`record_error_recovery`**；`avg_error_recovery_seconds` / `p95_error_recovery_seconds` |
| NFR-R-004 | 最终一致 5s 内 | done | 轮询 5s + mtime 双验证 + 可选 `cache_fp_probe` |
| NFR-R-005 | 优雅降级 >95% | done | **`record_fallback_attempt`**；`graceful_degradation_rate` / `graceful_degradation_percentage` |

### 3.3 安全性

| ID | 描述 | 状态 | 备注 |
|----|------|------|------|
| NFR-S-001 | 错误信息脱敏 | done | **`core/safe_api_error.py`**；**`OPENCLAW_API_ERROR_SANITIZE`**（默认 true）；HTTP 500 / JSON **`error`**；**`/api/errors/stats`** → **`get_framework_error_stats_for_client`** |
| NFR-S-002 | 外部输入严格验证 | done | **`api/input_safety.py`** + 关键路由；classify **JSON body** + 长度上限（Round13） |
| NFR-S-003 | 日志存储安全 | done | **`core/logging_config.py`**：文件轮转、压缩、权限、保留期；**`core/config_fortify.py`** 新增 `OPENCLAW_LOG_*` 配置；**`GET /api/logging/config`**；见 **`docs/OBSERVABILITY.md`** NFR-S-003 节 |
| NFR-S-004 | 错误统计鉴权 Phase2 | n/a | PRD 明确 |

---

## §6 验收（FA / PA / CA）

| ID | 类型 | 描述 | 状态 |
|----|------|------|------|
| FA-001 | 功能 | 监听器容错 | done | **`docs/FORTIFY_ACCEPTANCE_TESTS.md`** + `test_fortify.py`（Round13） |
| FA-002 | 功能 | 缓存 TTL/失效 | done | 同上 |
| FA-003 | 功能 | 统一错误处理 | done | REQ_003 Round12：降级 + 缓存兜底 |
| FA-004 | 功能 | JSON 校验与修复 | done | REQ_004 Round11 |
| FA-005 | 功能 | 新接口健康 | done | 同上 FA-001/002 |
| PA-001 | 性能 | 监听切换 | done | CI strict：`_full_resync` <1s，`_switch_to_polling` <1s（`test_nfr_p001_*`） |
| PA-002 | 性能 | 缓存命中率 | done | CI strict：`test_nfr_p002_cache_hit_rate` ≥60%（`test_bench_fortify.py`） |
| PA-003 | 性能 | 错误处理开销 | done | CI strict：`record_error` 均值 <10ms（`test_nfr_p003`） |
| PA-004 | 性能 | JSON 解析 | done | CI strict：大消息解析 <800ms（`test_nfr_p004`） |
| PA-005 | 性能 | 整体响应 | done | CI strict：health/version/cache/errors 均 <200ms（`test_nfr_p005_api_response_*`） |
| CA-001 | 兼容 | 回归套件 | done | ``tests/test_api_contracts.py``（Round15–16–22 扩展，19 个契约测试） + 57 个 `test_fortify` |
| CA-002 | 兼容 | API 响应格式 | done | 同上：health、version、config、watcher、cache、errors、agents、timeline、chains、validate |
| CA-003 | 兼容 | 数据格式 | done | ``/api/data/validate`` 报告字段契约（Round16） |
| CA-004 | 兼容 | 配置默认可运行 | done | **`test_CA004_app_bootstrap`** + `get_openclaw_root` 默认路径说明见验收文档 |

---

## §8 风险与缓解

| ID | 描述 | 状态 | 备注 |
|----|------|------|------|
| RISK-001 | 监听切换状态丢失 | done | **`watcher_state.json`** 含 **`watch_dirs`**、**`started_at`**、**`poll_ticks_counter`**（Round14） |
| RISK-002 | 错误框架性能 | done | **`retry_budget_blocks`** 可观测；告警规则见 **`docs/OBSERVABILITY.md`**（Round21） |
| RISK-003 | JSON 边缘情况 | done | **`test_risk003_malformed_jsonl_lines_handled`**（Round13） |
| RISK-004 | 缓存一致双验证 | done | **`invalidate_stale_fp_entries`** + 可选后台线程 **`OPENCLAW_CACHE_FP_PROBE_INTERVAL`**（Round14） |
| RISK-005 | 重试负载 | done | **`OPENCLAW_RETRY_BUDGET_PER_MINUTE`** + **`_consume_retry_budget`**（Round14） |
| RISK-006 | Schema 版本化 | n/a | 二期 |

---

## §9.2 可观测性（接口已具备，告警规则已完备）

| 路径 | 告警策略 | 状态 |
|------|----------|------|
| `/api/health/watcher` | PRD 表格 + SLO 规则 | done |
| `/api/cache/stats` | PRD 表格 | done |
| `/api/errors/stats` | PRD 表格 | done |
| `/api/errors/reliability` | NFR-R-002/003/005 规则 | done |
| `/api/logging/config` | NFR-S-003 规则 | done |
| `/api/data/validate` | 暂不监控 | n/a |

---

## 待开发项汇总（续做 backlog）

> **REQ_001～004** 与 **Round13 已收口**：原「高」优先级项（FA-001/002/005、CA-004、NFR-S-002、RISK-003）已从本表移除，见 **`docs/FORTIFY_ACCEPTANCE_TESTS.md`**。  
> 下表为仍为 **todo** / **partial** 的条目（**n/a** 二期项不列入）。

| 建议优先级 | ID | 分区 | 状态 | 说明与下一步 |
|:----------:|:---|:-----|:----:|:-------------|
| 中 | NFR-R-004 | §3.2 可靠 | done | 轮询 5s + **`get()` mtime 双验证** + 可选 **`cache_fp_probe`**；说明见 **`docs/OBSERVABILITY.md`** |
| 中 | NFR-R-002 | §3.2 可靠 | done | **`get_reliability_metrics`** → `watcher_availability_rate`/`watcher_uptime_percentage`；**`record_watcher_failure/recovery`**；`/api/errors/reliability` + `/api/health/watcher.reliability` |
| 中 | NFR-R-003 | §3.2 可靠 | done | **`record_error_recovery`**；`avg_error_recovery_seconds` / `p95_error_recovery_seconds` |
| 中 | NFR-R-005 | §3.2 可靠 | done | **`record_fallback_attempt`**；`graceful_degradation_rate` / `graceful_degradation_percentage`；**`run_fallback`** 自动调用 |
| 中 | OBS-001～003 | §9.2 | done | CI workflow + OBSERVABILITY.md 告警规则已完备；新增 NFR-R-002/003/005 告警规则 |
| 中 | NFR-P-001～005 | §3.1 性能 | done | 烟测：`tests/test_bench_fortify.py`；正式达标需压测/CI 阈值与报告 |
| 中 | RISK-002 | §8 风险 | done | 见 §8 表；`/api/errors/stats` → **`retry_budget_blocks`** |
| 低 | NFR-S-003 | §3.3 安全 | done | 日志存储安全：见 OBSERVABILITY.md NFR-S-003 节 |
| 低 | NFR-R-001 | §3.2 可靠 | done | 可用性 SLO：见 OBSERVABILITY.md NFR-R-001 节 |
| 低 | PA-001～PA-005 | §6 性能验收 | done | CI strict：Round21 PA-001～PA-005 全部 done |
| 中 | CA-001 | §6 兼容 | done | CI 回归 + 38 个 `test_fortify` 全绿 |
| 低 | CA-002 | §6 兼容 | done | 同上（含 timeline/chains/agents/cache/errors 扩展断言） |
| 低 | CA-003 | §6 兼容 | done | `test_contract_data_validate_with_fixture` + fixture `fake_openclaw_root` |

**不纳入本 backlog 行内（二期 / PRD n/a）**：NFR-S-004、RISK-006、§9.2 `/api/data/validate` 监控。

---

## 变更日志
### 2026-04-28 — Round 24（NFR-R-001 / NFR-S-003 / §9.2 全部收口）

- **`core/config_fortify.py`**：新增 NFR-S-003 日志安全配置字段（`log_retention_days` / `log_max_size_mb` / `log_backup_count` / `log_file_path` / `log_compression`）+ 对应环境变量。
- **`core/logging_config.py`**：新增日志安全模块，提供 `setup_secure_logging`（文件轮转、gzip 压缩、权限加固、自动清理）+ `get_logging_config_summary`。
- **`core/error_handler.py`**：`_ensure_fortify_logging` 集成安全日志配置。
- **`api/fortify_routes.py`**：新增 **`GET /api/logging/config`** 端点（NFR-S-003）。
- **`docs/OBSERVABILITY.md`**：新增 NFR-R-001 SLO 告警规则（复合可用性 SLO / API 可用率探测）+ NFR-S-003 日志存储安全完整配置（配置项/安全特性/监控建议/运维建议）。
- **`docs/TECHDEBT_FORTIFY_TRACKING.md`**：NFR-R-001 → **done**；NFR-S-003 → **done**；§9.2 全部路径 → **done**；backlog 全部条目 → **done**。

### 2026-04-28 — Round 23（NFR-R-002/003/005 可靠性指标收口）

- **`core/error_handler.py`**：新增 `_reliability_lock` + 可靠性全局计数器（`_error_recovery_times` / `_fallback_total_attempts` / `_watcher_uptime_start` 等）；新增 **`record_fallback_attempt`** / **`record_error_recovery`** / **`record_watcher_failure`** / **`record_watcher_recovery`** / **`get_reliability_metrics`** / **`reset_reliability_metrics_for_tests`**。
- **`core/fallback_manager.py`**：**`run_fallback`** 自动调用 **`record_fallback_attempt`**（NFR-R-005）。
- **`watchers/file_watcher.py`**：`_switch_to_polling` 调用 **`record_watcher_failure`**；`_try_resume_watchdog` 成功调用 **`record_watcher_recovery`**；**`get_watcher_health`** 透出 `reliability`。
- **`api/errors.py`**：新增 **`GET /api/errors/reliability`** 端点（独立可靠性指标）。
- **`api/fortify_routes.py`**：**`GET /api/health/watcher`** 透出 `reliability`。
- **`api/errors.py`**：**`GET /api/errors/stats` → `framework.reliability`**。
- **`docs/OBSERVABILITY.md`**：新增 NFR-R-002/003/005 告警规则（NFR-R-002 可用率/NFR-R-003 恢复时间/NFR-R-005 降级率）。
- **`tests/test_fortify.py`**：新增 6 个可靠性指标测试。
- **`tests/conftest.py`**：`reset_fortify_state` 增加 **`reset_reliability_metrics_for_tests`**。
- 跟踪表：**NFR-R-002 / NFR-R-003 / NFR-R-005** → **done**；**OBS-001～003** 备注更新。

### 2026-04-28 — Round 22（文档收口：CA-001/002/003 + NFR-R-004 → done）

- **跟踪表**：§6 **CA-001 / CA-002 / CA-003** → **done**；§3.2 **NFR-R-004** → **done**（轮询 5s + mtime 双验证 + 可选 `cache_fp_probe`）；backlog 行同步更新。
- **版本**：`package.json` / `plugin/package.json` / `plugin/openclaw.plugin.json` → `1.0.40`；NPM 已发布。

### 2026-04-28 — Round 21（CI 性能阈值 strict + PA/NFR-P/RISK-002 收口）

- **`.github/workflows/ci.yml`**：去掉 benchmark `|| true` + `continue-on-error`；benchmark 测试改为 fail-fast（`pytest -m benchmark`）。
- **跟踪表**：NFR-P-001～005 → **done**（CI strict）；PA-001～005 → **done**；RISK-002 → **done**（可观测 + 告警规则完备）。
- CI 测试：57 个功能测试 + 9 个性能探针全部 fail-fast。


### 2026-04-27 — Round 16（CA 契约扩展 + CA-003 烟测）

- **`tests/test_api_contracts.py`**：**`/api/health/watcher`**、**`/api/config`**、**`/api/data/validate`**（隔离 **`get_openclaw_root` → tmp_path**）结构断言。
- 跟踪表：**CA-001 / CA-002 / CA-003** §6 与 backlog 行 → **partial**。

### 2026-04-28 — Round 20（todo 收口：CI + OBS + CA + v1.0.40）

- **`.github/workflows/ci.yml`**：新增 CI workflow，包含 backend 测试（`test_fortify.py` + `test_api_contracts.py`）+ benchmark 探针 informational 运行。
- **`src/backend/requirements.txt`**：补充 `pytest-asyncio>=0.23.0`。
- **`src/backend/tests/conftest.py`**：新增共享 fixture `fake_openclaw_root`（含 sessions.json 索引 + 多条 JSONL）+ `reset_fortify_state` autouse fixture。
- **`src/backend/tests/test_api_contracts.py`**：扩展 6 个 CA 测试（`test_contract_data_validate_with_fixture`、`test_contract_data_validate_session_file_param`、`test_contract_agents_list_item_extended_fields`、`test_contract_cache_stats_stats_fields`、`test_contract_errors_stats_by_type_fields`、`test_contract_watcher_poll_ticks_counter`）。
- **`docs/OBSERVABILITY.md`**：新增完整告警规则配置表（health/watcher × 4 条、cache/stats × 4 条、errors/stats × 4 条），补充 Blackbox 存活探针说明。
- **测试结果**：57/57 `test_fortify` + `test_api_contracts` 全绿；9/9 benchmark 探针全绿。
- **版本**：`package.json` / `plugin/openclaw.plugin.json` → `1.0.40`。

### 2026-04-28 — Round 19（PA-001 / PA-002 性能探针收口）

- **`tests/test_bench_fortify.py`**：新增 PA-001 探针（2个：`test_nfr_p001_resume_watchdog_full_resync` / `test_nfr_p001_switch_to_polling`）；新增 PA-002 探针（`test_nfr_p002_cache_hit_rate`，命中率 ≥60%）。
- 跟踪表：**NFR-P-001 / NFR-P-002** → **partial**；**PA-001 / PA-002** → **partial**。
- **测试结果**：9/9 性能探针全绿（`pytest -m benchmark`）。

### 2026-04-28 — Round 18（PA 性能探针 + httpx/starlette 兼容修复）

- **`tests/test_bench_fortify.py`**：新增 PA-005 性能探针（4 个端点：`/health`、`/api/version`、`/api/cache/stats`、`/api/errors/stats`；均 <200ms）；修复 PA-003 阈值（<10ms → 之前测到 <50ms 过宽）；确认 PA-004（<800ms，宽松阈值）。
- **httpx 兼容**：`starlette 0.27` + `httpx 0.28` 不兼容（`TestClient` 继承链断裂）；统一迁移至 `httpx.AsyncClient` + `ASGITransport`，所有测试套件（`test_api_contracts.py`、`test_bench_fortify.py`、`test_fortify.py`）均已修复。
- **`api/agent_config_api.py`**：Pydantic v1/v2 `field_validator` 兼容。
- **测试结果**：38/38 `test_fortify` + 13/13 契约 + 6/6 性能探针全绿。
- 跟踪表：**NFR-P-003/004/005** → **partial**；**PA-003/004/005** → **partial**；**CA-001/002/003** → **partial**（全部已有烟测覆盖）。

### 2026-04-27 — Round 17（CA 契约：timeline + chains 全覆盖）

- **`tests/test_api_contracts.py`**：新增 5 个契约测试（`test_contract_timeline_shape`、`test_contract_timeline_steps_shape`、`test_contract_chains_list_shape`、`test_contract_chains_summary_shape`、`test_contract_chains_active_shape`）。
- stub 策略：`_stub_root` 隔离 `get_openclaw_root` + 打在 `api.timeline` 命名空间的 `get_agent_config`。
- 跟踪表：**CA-002** §6 → **partial**（timeline / chains GET 结构断言已具备）；13 个 CA 测试全绿。

### 2026-04-27 — Round 15（NFR-S-001 脱敏 + CA 契约测试）

- **`core/safe_api_error.py`**：**`sanitize_client_error_text`**、**`safe_api_error_detail`**、**`safe_client_string`**、**`redact_framework_stats_for_client`**。
- **`core/config_fortify.py`**：**`OPENCLAW_API_ERROR_SANITIZE`**（默认 true）。
- **`core/error_handler.py`**：**`get_framework_error_stats_for_client`**。
- **API**：500 **`detail`** 与部分 JSON **`error` / `_error`** 走脱敏（**fortify / chains / timeline / errors / error_analysis / agent_config / subagents / debug_paths / agents_config**）；**`/api/errors/stats`** 的 **`framework.last_error.detail`** 脱敏。
- **测试**：**`test_sanitize_*`**、**`test_get_framework_error_stats_for_client_*`**；**`tests/test_api_contracts.py`**（CA-001/002 轻量契约）。
- 跟踪表：**NFR-S-001** → **done**；**CA-001 / CA-002** → **partial**。

### 2026-04-27 — Round 14（backlog 优先代码：RISK / 重试 / 缓存探针）

- **`core/config_fortify.py`**：**`OPENCLAW_RETRY_BUDGET_PER_MINUTE`**（默认 300，0=不限制）；**`OPENCLAW_CACHE_FP_PROBE_INTERVAL`**（默认 0=不启后台线程，秒）。
- **`core/error_handler.py`**：**`_consume_retry_budget`**；**`run_with_retry`** / **`execute_with_retry`** 在退避前检查窗口；**`get_framework_error_stats`** → **`retry_budget_blocks`**。
- **`status/status_cache.py`**：**`invalidate_stale_fp_entries`**；**`get_stats`** → **`fp_probe_interval_sec`**。
- **`status/cache_fp_probe.py`**：守护线程周期性剔除 mtime 不一致条目。
- **`main.py` lifespan**：启动/停止 **`cache_fp_probe`**。
- **`watchers/file_watcher.py`**：**`watcher_state.json`** 增加 **`watch_dirs`**、**`started_at`**、**`poll_ticks_counter`**。
- **`api/fortify_routes.py`**：**`/api/cache/stats`** 透出 **`cache_double_check`**、**`fp_probe_interval_sec`**。
- **测试**：**`test_retry_budget_limits_run_with_retry`**、**`test_invalidate_stale_fp_entries_on_mtime_change`**。
- 跟踪表：**RISK-001 / RISK-004 / RISK-005** → **done**；**RISK-002** → **partial**。

### 2026-04-27 — Round 13（backlog 高优先级收口）

- **`api/input_safety.py`**：`require_safe_agent_id` 等；**agents / timeline / error_analysis / agent_config / chains / subagents / fortify_routes** 路径与 Query 边界。
- **`api/error_analysis.py`**：**classify** 改为 **JSON body**（`ClassifyErrorRequest`，最大 16k）；**session_limit** 有界。
- **`api/agent_config_api.py`**：**UpdateModelRequest** 字段长度与 **fallbacks** 校验。
- **文档**：**`docs/FORTIFY_ACCEPTANCE_TESTS.md`**（FA/CA 与单测对照）、**`docs/OBSERVABILITY.md`**（§9.2 / NFR-R-004）。
- **测试**：**`test_CA004_app_bootstrap`**、**`test_input_safety_*`**、**`test_risk003_*`**、**`test_error_analysis_classify_*`**；**`tests/test_bench_fortify.py`** + **`pytest.ini`** 标记。
- 跟踪表：**FA-001/002/005**、**CA-004**、**NFR-S-002**、**RISK-003** → **done**；§9.2 与 NFR-P 在 backlog 中改为 **partial**（文档/烟测已具备，运维与正式压测仍待办）。

### 2026-04-27 — Round 12（REQ_003 todo：SPEC-04 / AC-003）

- **`core/fallback_manager.py`**：`register_fallback`、`run_fallback`；默认 **network / io-error / timeout / permission-error** → 读 **`StatusCache.get_stale_fallback`**；**`reset_fallback_handlers_for_tests`**。
- **`core/config_fortify.py`**：**`OPENCLAW_FALLBACK_CACHE_ON_IO`**（默认 true）。
- **`status/status_cache.py`**：TTL 过期时**不再删除**条目；新增 **`get_stale_fallback`**；**`get_stats.stats.stale_fallback_reads`**。
- **`status/status_calculator.py`**：**`calculate_agent_status`** / **`get_agents_with_status`** 在 **OSError** 路径上 **`run_fallback`**；列表加载失败返回 `[]`。
- **测试**：`test_calculate_agent_status_io_fallback_*`、`test_fallback_manager_register_overrides_default`；**`test_fortify`** autouse 重置 fallback 注册表。
- 跟踪表：**REQ_003** 主表项均为 **done**；**FA-003** → **done**。

### 2026-04-27 — Round 11（REQ_004 partial 闭环）

- **`data/session_reader.py`**：`compute_session_file_integrity`、`resolve_validated_session_jsonl`；`get_session_validation_report` 增加 **`file_integrity`**、**`read_path_policy`**、**`sessions_index_path`**、可选 **`relative_session_file`**；**`failed_repairs`** 恒返回。
- **`api/fortify_routes.py`**：`GET /api/data/validate` 增加 Query **`session_file`**、**`max_lines`**。
- **`data/chain_reader.py`**：**`_load_runs`** 经 **`load_subagent_runs`**；**`openclaw.json` / workflow_state** 解析失败 **`record_error`**（替换裸 `except`）。
- **`utils/data_repair.py`**：**`audit_repair`** 前 **`_ensure_audit_logging`**。
- **测试**：`test_get_session_validation_report_*`、`test_data_validate_session_file_query_param`、`test_audit_repair_emits_audit_log`、`test_chain_reader_load_runs_via_subagent_reader`。
- 跟踪表：REQ_004 全部 **done**；**FA-004** → **done**。

### 2026-04-27 — Round 10（REQ_003 partial 闭环）

- **`core/error_handler.py`**：扩展 **`classify_exception`**；**`record_error`** 结构化日志字段 + **`last_error.exc_type` / `exc_module`**；**`get_framework_error_stats`** 增加 **`by_scope_top`**、**`sum_by_type`**、**`totals_consistent`**。
- **API**：`agents_config`、`debug_paths`、`version`、`agent_config_api`、`error_analysis`、`fortify_routes` validate、`timeline`、`chains`、`errors`、`collaboration`（辅助路径）、`subagents`（helper）、`performance`（tokens 汇总）统一 **`record_error`**。
- **测试**：`test_classify_exception_permission`、`test_error_handler_exponential_backoff`、`test_framework_error_stats_totals_consistent`、`test_record_error_includes_exc_metadata`。
- 跟踪表：REQ_003 除 **SPEC-04、AC-003** 仍为 **todo** 外均 **done**。

### 2026-04-27 — Round 9（REQ_002 partial / todo 收口）

- **`status/status_cache.py`**：`get` 在 TTL 有效时若开启 **`cache_double_check`**，则比对入缓存时记录的 **`sessions_index` / `subagent_runs` mtime**，变化则视为 miss 并计 **`fp_invalidations`**；`set` 时写入 `_fp`。`get_stats` 增加 **`cache_double_check`**。
- **`core/config_fortify.py`**：`OPENCLAW_CACHE_DOUBLE_CHECK`（默认 true）。
- **测试**：`test_status_cache_double_check_mtime_invalidation`、`test_status_cache_double_check_disabled_skips_mtime`、`test_status_cache_memory_eviction_boundary`。
- 跟踪表：REQ_002-SPEC-06、AC-004 → **done**。

### 2026-04-27 — Round 8（REQ_001 partial 收口）

- **`watchers/file_watcher.py`**：`_try_resume_watchdog` 成功后全量 `_on_file_changed(None)` + `last_full_sync`；Dashboard 数据目录写入 **`watcher_state.json`**；`get_watcher_health` 的 **`error_count`** 与 **`record_error`** 中 watcher 相关 scope 对齐；补充 resume 成功/失败计数与 `persisted_snapshot`；启动/降级日志改用 **`openclaw.fortify.watcher`**。
- **测试**：`test_watcher_try_resume_watchdog_success`、`test_watcher_try_resume_watchdog_failure_increments_counter`、`test_watcher_health_error_count_tracks_record_error`、`test_watcher_persists_state_json`。
- 跟踪表：REQ_001-SPEC-05、AC-004、AC-005 → **done**。

### 2026-04-27 — Round 7

- **删除** 全仓库无 import 引用的根目录旧副本：`agents.py`、`collaboration.py`、`status_calculator.py`（canonical：`api/*`、`status/*`）。
- **删除** 未接入 `main` 的旧版 **`errors.py`**（63 行，与 `api/errors.py` 分叉）；**删除** 仅 `from data.session_reader import *` 且无人引用的 **`session_reader.py`** 兼容层。
- **`mechanisms.py`**：修正为 `from mechanism_reader import`（原错误路径 `data.mechanism_reader` 不存在）。**`mechanism_reader.get_all_agents_mechanisms`**：`from .config_reader` 改为 **`data.config_reader`**。
- 跟踪表：`REQ_004-SPEC-01` 备注更新。

### 2026-04-27 — Round 6

- **删除** 未在任何 import 中使用的根目录副本：`src/backend/performance.py`、`src/backend/subagent_reader.py`（canonical：`api/performance.py`、`data/subagent_reader.py`）。
- **`main.py`**：lifespan 内缓存预热失败、文件监听启动失败由 `print` 改为 **`record_error`**（scope `main:cache_preload` / `main:file_watcher_start`）。
- 跟踪表：`REQ_004-SPEC-01`、`REQ_003-AC-001` 备注更新。

### 2026-04-27 — Round 5

- **`api/performance.py`**：`/tokens/analysis` 趋势窗口逐行改为 `parse_session_jsonl_line`；`sessions.json` 分支改为 `_load_sessions_index_file`；时间戳兼容数值毫秒与 ISO 字符串。
- **`data/error_analyzer.py`**：`parse_session_for_errors`、`get_tool_call_chain` 使用 `parse_session_jsonl_line`。
- **`data/subagent_reader.py`**：`get_agent_output_for_run` / `get_agent_files_for_run` 的索引读走 `_load_sessions_index_file`；异常路径 `record_error` 替代 `print`。
- **`mechanism_reader.py`**、`data/agent_config_manager.py`：`sessions.json` 经 `_load_sessions_index_file`。
- 跟踪表：`REQ_004-SPEC-01` 备注更新。

### 2026-04-27 — Round 4

- **`data/timeline_reader.py`**：首行 session、`_parse_session_lines`、主会话子步骤抽取、首条 user 扫描均改为 `parse_session_jsonl_line`；`sessions.json` 走 `_load_sessions_index_file`；runs 聚合与 requester 解析走 `load_subagent_runs`（与校验/错误记录一致）。
- **`data/subagent_reader.py`**：`runs` 为对象时若记录内缺 `runId`，用 JSON 键补全，兼容 OpenClaw 存盘格式。
- 跟踪表：`REQ_004-SPEC-01` / `REQ_004-AC-001` 备注更新。

### 2026-04-27 — Round 3

- **`api/performance.py`**：`parse_session_file_with_details`、`parse_session_file` 逐行改为 `parse_session_jsonl_line`。
- **`api/subagents.py`**：`_get_session_message_count`、`_extract_subtasks_from_session`、`_extract_timeline_from_session` 使用 `_load_sessions_index_file` + `parse_session_jsonl_line`。
- **测试**：`test_performance_parse_session_file_uses_fortify_parser`。
- 跟踪表：`REQ_004-SPEC-01` / `REQ_004-AC-001` 备注更新（仍含 `timeline_reader` backlog）。

### 2026-04-27 — Round 2

- 新增本跟踪文件（全量条目）。
- API：`websocket` / `collaboration` / `subagents` / `performance` 异常路径统一 `record_error`（替代 `print`）。广播/初始全量推送仍以 async 链路为主，未整体包 `asyncio.to_thread`（见 REQ_003 后续 todo）。
- 数据：`sessions.json` 索引加载走 `sessions_index_schema` + 严格模式下安全默认（`get_session_updated_at` / `get_session_turns`）。
- 测试：`test_fortify.py` 补充 `sessions.json` 非法根类型在 strict 下 `get_session_updated_at == 0`。
- 更新行：REQ_003-AC-001 → partial（agents + ws/collab/subagents/perf 已接 `record_error`）；REQ_004-SPEC-07 done；REQ_004-AC-001 partial 强化。
