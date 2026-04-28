# FORTIFY 可观测性接入（§9.2）

> 接口已实现；**告警策略按 PRD 表格在运维侧配置**。本节便于对接 Prometheus / Grafana / 云监控。

## 建议抓取指标

|| 路径 | 用途 | 可关注字段 |
||------|------|------------|
|| `GET /api/health/watcher` | 监听模式、降级次数、恢复计数 | `mode`、`status`、`error_count`、`switch_count`、`resume_watchdog_success_count` |
|| `GET /api/cache/stats` | 缓存命中、双验证失效 | `hit_rate`、`cache_double_check`、`fp_probe_interval_sec`、`stats.hits`、`stats.misses`、`stats.fp_invalidations`、`stats.stale_fallback_reads` |
|| `GET /api/errors/stats` | 错误类型与 scope | `framework.total_count`、`framework.by_type`、`framework.totals_consistent`、`framework.retry_budget_blocks` |

## 最终一致与轮询（NFR-R-004）

- 文件变更依赖 **watchdog** 或 **5s 轮询** 兜底；缓存 TTL 通过后还可选 **mtime 双验证**（`OPENCLAW_CACHE_DOUBLE_CHECK`）。
- 可选 **`OPENCLAW_CACHE_FP_PROBE_INTERVAL`**（秒）：后台线程周期性调用 **`StatusCache.invalidate_stale_fp_entries`**，在无 API 流量时仍可按 mtime 剔除过期缓存项（默认 0 关闭）。

## API 错误脱敏（NFR-S-001）

- 默认 **`OPENCLAW_API_ERROR_SANITIZE=true`**：HTTP 500 的 **`detail`** 与对外 JSON 错误字段会弱化密钥/路径/邮箱等形态；服务端 **`record_error`** 仍为完整信息。
- 关闭脱敏（仅建议本地调试）：**`OPENCLAW_API_ERROR_SANITIZE=false`**。

## 重试预算（RISK-005）

- **`OPENCLAW_RETRY_BUDGET_PER_MINUTE`**：按 **`ErrorHandler.run_with_retry` 的 `operation` 名字**统计 60s 滑动窗口内的退避重试次数；超限则提前失败并记 **`retry_budget_blocks`**（0 表示不限制）。

## 告警规则配置

以下为建议告警阈值，可按实际业务调整：

### health/watcher

| 告警规则 | 条件 | 严重度 | 说明 |
|----------|------|--------|------|
| `watcher_error_rate` | `error_count` > 10 / 5min | Warning | 监听异常过多 |
| `watcher_switch_storm` | `switch_count` > 5 / 5min | Warning | 频繁切换监听/轮询 |
| `watcher_down` | `status` != "watching" 且持续 > 2min | Critical | 监听完全失效 |
| `watcher_resume_fail_rate` | `resume_watchdog_failure_count` 持续增长 | Warning | watchdog 恢复失败 |

### cache/stats

| 告警规则 | 条件 | 严重度 | 说明 |
|----------|------|--------|------|
| `cache_hit_rate_low` | `hit_rate` < 50% 持续 > 10min | Warning | 命中率过低（阈值可按 NFR-P-002 ≥60% 调整） |
| `cache_fp_invalidation_spike` | `stats.fp_invalidations` > 100 / 5min | Warning | mtime 双验证频繁失效 |
| `cache_stale_fallback_spike` | `stats.stale_fallback_reads` > 50 / 5min | Warning | IO 降级频繁，读到过期缓存 |
| `cache_memory_high` | `memory_usage_bytes / memory_limit_bytes` > 90% | Warning | 缓存内存接近上限 |

### errors/stats

| 告警规则 | 条件 | 严重度 | 说明 |
|----------|------|--------|------|
| `error_rate_high` | `framework.total_count` > 100 / 5min | Warning | 错误量突增 |
| `retry_budget_exhausted` | `framework.retry_budget_blocks` > 10 / 5min | Warning | 重试预算耗尽（RISK-005） |
| `error_type_spike` | 某 `by_type` 项 > 50 / 5min | Warning | 特定错误类型集中爆发 |
| `critical_error_scope` | scope 含 `main:file_watcher_start` 或 `main:cache_preload` | Critical | 启动关键路径失败 |

## Blackbox 存活探针

对上述三个 `GET` 做 **HTTP 200 + JSON 解析** 即可作为存活与延迟探针。

- 存活：任意接口 HTTP 200
- 延迟：建议 `/api/version` 作为轻量探针（目标 <50ms）
- `GET /api/data/validate` 默认 **不纳入** 高频监控（成本高）
