# FORTIFY 功能验收与单测对照（FA / CA）

> 对应 **`TECHDEBT_FORTIFY_TRACKING.md`** §6；自动化用例位于 `src/backend/tests/test_fortify.py`。  
> 执行：`cd src/backend && .venv/bin/python -m pytest tests/test_fortify.py -v`（需已安装 `requirements.txt`）。

## FA-001 监听器容错

| 验收点 | 自动化覆盖 |
|--------|------------|
| 健康接口字段 | `test_fortify_api_routes`：`GET /api/health/watcher` 含 `mode`、`status`、`switch_count`、`error_count`、`persisted_snapshot` |
| 恢复 watchdog | `test_watcher_try_resume_watchdog_success`、`test_watcher_try_resume_watchdog_failure_increments_counter` |

## FA-002 缓存 TTL / 失效

| 验收点 | 自动化覆盖 |
|--------|------------|
| 命中/未命中 | `test_status_cache_hits_misses` |
| mtime 双验证失效 | `test_status_cache_double_check_mtime_invalidation`、`test_status_cache_double_check_disabled_skips_mtime` |
| LRU 逐出 | `test_status_cache_memory_eviction_boundary` |
| 统计接口 | `test_fortify_api_routes`：`GET /api/cache/stats` |

## FA-003 统一错误处理

| 验收点 | 自动化覆盖 |
|--------|------------|
| 分类与统计 | `test_classify_exception_permission_and_decode`、`test_framework_error_stats`、`test_record_error_includes_exc_metadata` |
| 退避重试 | `test_error_handler_exponential_backoff` |
| IO 降级读缓存 | `test_calculate_agent_status_io_fallback_uses_stale_cache`、`test_calculate_agent_status_io_fallback_disabled` |

## FA-004 JSON 校验与修复

| 验收点 | 自动化覆盖 |
|--------|------------|
| 行修复 | `test_attempt_line_json_repair_trailing_comma` |
| JSONL 解析 | `test_parse_session_jsonl_line_message`、`test_performance_parse_session_file_uses_fortify_parser` |
| 校验接口 | `test_data_validate_requires_agent`、`test_data_validate_session_file_query_param`、`test_get_session_validation_report_*` |

## FA-005 新接口健康（fortify 路由）

| 验收点 | 自动化覆盖 |
|--------|------------|
| watcher / cache / errors 统计 | `test_fortify_api_routes` |
| validate | `test_data_validate_*` |

## CA-004 配置默认可运行

| 验收点 | 自动化覆盖 |
|--------|------------|
| 应用可导入、根路径可访问 | `test_CA004_app_bootstrap`（见 `test_fortify.py`） |
| 数据目录 | 运行时设置 **`OPENCLAW_STATE_DIR`** 或默认 **`~/.openclaw`**（见 `data/config_reader.get_openclaw_root`） |

## NFR-S-002 / RISK-003

| 验收点 | 自动化覆盖 |
|--------|------------|
| 路径类参数拒绝逃逸 | `test_input_safety_rejects_traversal_in_agent_path` 等（见 `test_fortify.py`） |
| 畸形 JSONL | `test_risk003_malformed_jsonl_lines_handled`（见 `test_fortify.py`） |
