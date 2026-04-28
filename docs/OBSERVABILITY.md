# FORTIFY 可观测性接入（§9.2）

> 接口已实现；**告警策略按 PRD 表格在运维侧配置**。本节便于对接 Prometheus / Grafana / 云监控。

## 建议抓取指标

|| 路径 | 用途 | 可关注字段 |
||------|------|------------|
|| `GET /api/health/watcher` | 监听模式、降级次数、恢复计数 | `mode`、`status`、`error_count`、`switch_count`、`resume_watchdog_success_count` |
|| `GET /api/cache/stats` | 缓存命中、双验证失效 | `hit_rate`、`cache_double_check`、`fp_probe_interval_sec`、`stats.hits`、`stats.misses`、`stats.fp_invalidations`、`stats.stale_fallback_reads` |
|| `GET /api/errors/stats` | 错误类型与 scope | `framework.total_count`、`framework.by_type`、`framework.totals_consistent`、`framework.retry_budget_blocks` |
| `GET /api/errors/reliability` | 可靠性指标 | `watcher_availability_rate`、`avg_error_recovery_seconds`、`graceful_degradation_rate` |
| `GET /api/logging/config` | 日志配置状态 | `log_retention_days`、`log_max_size_mb`、`log_file_path` |

## 最终一致与轮询（NFR-R-004）

- 文件变更依赖 **watchdog** 或 **5s 轮询** 兜底；缓存 TTL 通过后还可选 **mtime 双验证**（`OPENCLAW_CACHE_DOUBLE_CHECK`）。
- 可选 **`OPENCLAW_CACHE_FP_PROBE_INTERVAL`**（秒）：后台线程周期性调用 **`StatusCache.invalidate_stale_fp_entries`**，在无 API 流量时仍可按 mtime 剔除过期缓存项（默认 0 关闭）。

## API 错误脱敏（NFR-S-001）

- 默认 **`OPENCLAW_API_ERROR_SANITIZE=true`**：HTTP 500 的 **`detail`** 与对外 JSON 错误字段会弱化密钥/路径/邮箱等形态；服务端 **`record_error`** 仍为完整信息。
- 关闭脱敏（仅建议本地调试）：**`OPENCLAW_API_ERROR_SANITIZE=false`**。

## 重试预算（RISK-005）

- **`OPENCLAW_RETRY_BUDGET_PER_MINUTE`**：按 **`ErrorHandler.run_with_retry` 的 `operation` 名字**统计 60s 滑动窗口内的退避重试次数；超限则提前失败并记 **`retry_budget_blocks`**（0 表示不限制）。

## NFR-R 可靠性指标（REQ_001 / REQ_003）

### NFR-R-002 监听成功率（目标 >99%）

路径：`GET /api/health/watcher` → `reliability.watcher_availability_rate`
路径：`GET /api/errors/reliability` → `watcher_availability_rate`

| 告警规则 | 条件 | 严重度 | 说明 |
|----------|------|--------|------|
| `watcher_availability_low` | `reliability.watcher_availability_rate` < 0.99 | Warning | 监听可用率低于 99% |
| `watcher_uptime_percentage_low` | `reliability.watcher_uptime_percentage` < 99% 持续 > 10min | Critical | 监听持续不可用 |

### NFR-R-003 错误恢复时间（目标 <5s）

路径：`GET /api/errors/reliability`

| 告警规则 | 条件 | 严重度 | 说明 |
|----------|------|--------|------|
| `error_recovery_slow` | `reliability.avg_error_recovery_seconds` > 5 | Warning | 平均错误恢复时间超过 5s |
| `error_recovery_p95_slow` | `reliability.p95_error_recovery_seconds` > 10 | Warning | 95% 分位错误恢复时间超过 10s |

### NFR-R-005 优雅降级率（目标 >95%）

路径：`GET /api/errors/reliability`

| 告警规则 | 条件 | 严重度 | 说明 |
|----------|------|--------|------|
| `graceful_degradation_low` | `reliability.graceful_degradation_rate` < 0.95 | Warning | 降级成功率低于 95% |
| `fallback_success_rate_low` | `reliability.graceful_degradation_percentage` < 95% | Warning | 降级成功率百分比低于 95% |

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

---

## NFR-R-001 SLO 告警配置（可用性目标 >99.9%）

NFR-R-001 为运维侧 SLO 配置，以下为建议的 SLO 告警规则。

### 复合 SLO 计算

整体可用性 SLO = 监听可用率 × API 可用率

| SLO 规则 | 条件 | 严重度 | 说明 |
|----------|------|--------|------|
| `slo_availability_999` | `watcher_availability_rate * api_uptime_rate` >= 0.999 | OK | SLO 达标 |
| `slo_availability_warning` | SLO < 0.999 且 >= 0.99 | Warning | SLO 接近突破 |
| `slo_availability_critical` | SLO < 0.99 | Critical | SLO 突破 |
| `slo_downtime_budget` | 月累计宕机时间 > 43.8min (99.9% 月可用性预算) | Warning | 宕机预算消耗过快 |

### API 可用率探测

| 探测规则 | 条件 | 严重度 | 说明 |
|----------|------|--------|------|
| `api_health_degraded` | `/api/health/watcher` 响应 > 500ms | Warning | API 响应延迟 |
| `api_health_down` | 任意核心 API 连续 3 次 HTTP 5xx | Critical | API 服务不可用 |

---

## NFR-S-003 日志存储安全

日志存储安全由运维侧和代码配置共同保障。

### 代码配置项

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| 日志保留天数 | `OPENCLAW_LOG_RETENTION_DAYS` | 30 | 超过此天数的日志将被清理 |
| 单个日志文件大小上限 | `OPENCLAW_LOG_MAX_SIZE_MB` | 100 | 超过此大小触发轮转 |
| 备份文件数量 | `OPENCLAW_LOG_BACKUP_COUNT` | 5 | 保留的轮转备份数量 |
| 日志文件路径 | `OPENCLAW_LOG_FILE_PATH` | `logs/openclaw.log` | 自定义日志路径 |
| 日志压缩 | `OPENCLAW_LOG_COMPRESSION` | true | 轮转日志 gzip 压缩 |

### 日志安全特性

- **文件权限**：日志文件权限设置为 0o600（仅所有者读写）
- **轮转机制**：基于文件大小的自动轮转，防止磁盘空间耗尽
- **压缩存储**：轮转的日志自动 gzip 压缩，减少存储空间
- **自动清理**：启动时自动清理超过保留期的日志（建议生产环境配合 logrotate/cron）
- **审计日志**：JSON 修复操作写入 `openclaw.fortify.audit` 日志（SHA256 去重敏感信息）

### 日志监控建议

| 告警规则 | 条件 | 严重度 | 说明 |
|----------|------|--------|------|
| `log_file_size_high` | 单个日志文件 > 90MB | Warning | 接近轮转阈值 |
| `log_disk_space_low` | 日志目录所在磁盘 < 1GB | Critical | 磁盘空间不足 |
| `log_rotation_failure` | 连续 3 次日志写入失败 | Critical | 日志写入异常 |
| `audit_log_spike` | `openclaw.fortify.audit` 频率突增 | Warning | 可能有异常修复操作 |

### API 端点

`GET /api/logging/config` - 返回当前日志配置状态

```json
{
  "status": "ok",
  "config": {
    "log_retention_days": 30,
    "log_max_size_mb": 100,
    "log_backup_count": 5,
    "log_file_path": "/path/to/logs/openclaw.log",
    "log_compression": true,
    "log_directory_exists": true,
    "current_log_size_bytes": 52428800,
    "current_log_size_mb": 50.0
  }
}
```

### 运维建议

1. **logrotate 补充**：代码日志轮转仅基于大小，建议生产环境额外配置 logrotate 按天/按周轮转
2. **集中日志**：将 `logs/` 目录配置到 ELK/Loki/Graylog 等集中日志系统
3. **日志加密传输**：日志收集 agent 到日志服务器的传输应使用 TLS
4. **定期审计**：定期检查 `openclaw.fortify.audit` 审计日志中的修复操作
