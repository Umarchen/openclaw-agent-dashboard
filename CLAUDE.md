# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

An OpenClaw plugin that provides a real-time multi-Agent visualization dashboard. It runs as a FastAPI backend (port 38271) serving a Vue 3 SPA, integrated into the OpenClaw gateway as a plugin.

## Commands

### Development Workflow
```bash
# Full build + install as local plugin
npm run deploy

# Build plugin/ only (no install)
npm run pack

# Rebuild and redeploy after code changes
npm run deploy && openclaw gateway restart

# Start dashboard independently (without plugin install)
npm run start
```

### Frontend (from `frontend/`)
```bash
npm install
npm run dev      # Dev server with HMR
npm run build    # Production build to frontend/dist/
```

### Backend Tests (from `src/backend/`)
```bash
# Activate venv first
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# Run main test suites
python -m pytest tests/test_fortify.py tests/test_api_contracts.py -v --tb=short

# Run benchmark probes (SLA tests)
python -m pytest tests/test_bench_fortify.py -v --tb=short -m benchmark

# Run a single test
python -m pytest tests/test_fortify.py::test_status_cache_hits_misses -v
```

### Publishing a Release
Version must be bumped in three files simultaneously: `package.json`, `plugin/package.json`, `plugin/openclaw.plugin.json`. See `docs/plan/release-playbook.md` for the full step-by-step (git tag → GitHub Release → npm publish → self-dependency write-back).

## Architecture

### Build Pipeline
`npm run pack` (via `scripts/build-plugin.js`):
1. Builds frontend (`frontend/`) → `frontend/dist/`
2. Copies `src/backend/` → `plugin/dashboard/`
3. Copies `frontend/dist/` → `plugin/frontend-dist/`
4. Copies `scripts/install-python-deps.js` → `plugin/scripts/`

The `plugin/` directory is what gets published to npm and installed by `openclaw plugins install`.

### Backend (`src/backend/`)
FastAPI app with async lifespan. On startup it launches a file watcher and optionally preloads the status cache.

| Layer | Path | Role |
|-------|------|------|
| Entry | `main.py` | Registers all routers; serves `frontend-dist/` as static fallback |
| API routes | `api/` | One file per domain: `agents`, `timeline`, `chains`, `error_analysis`, `websocket`, `performance`, `collaboration`, `fortify_routes`, etc. |
| Status | `status/` | `status_calculator.py` computes agent status; `status_cache.py` TTL+memory-bounded cache with double-check mtime validation |
| Data readers | `data/` | Read-only access to OpenClaw state files (`config_reader.py`, `session_reader.py`, `subagent_reader.py`, `timeline_reader.py`, etc.) |
| Core | `core/` | `config_fortify.py` (env-driven config singleton), `error_handler.py`, `fallback_manager.py`, `logging_config.py` |
| Watcher | `watchers/file_watcher.py` | Watchdog-based file change detection with automatic fallback to polling; debounced; invalidates cache and broadcasts via WebSocket on change |

**Static file serving:** `main.py` auto-detects plugin layout (`plugin/frontend-dist/`) vs dev layout (`frontend/dist/`) and mounts the correct directory. **API routes must be registered before the static mount** or `/api` requests are swallowed.

**Real-time flow:** File change → `file_watcher` debounce → `status_cache.invalidate()` → `api/websocket.broadcast_full_state()` → all connected clients.

### Frontend (`frontend/src/`)
Vue 3 + TypeScript SPA (no router — single-page with panel switching).

| Layer | Path | Role |
|-------|------|------|
| Entry | `App.vue` | Orchestrates main layout: CollaborationFlow, TaskStatus, Performance, ErrorCenter, detail/settings panels |
| Managers | `managers/` | `RealtimeDataManager` (WebSocket + polling fallback), `StateManager` (reactive key-value store with TTL cache), `EventDispatcher` (pub/sub) |
| Composables | `composables/` | `useRealtime`, `useState`, `useDebounce`, `useThrottle`, `useVirtualScroll` |
| Components | `components/` | Feature subdirs: `collaboration/`, `timeline/`, `tasks/`, `performance/`, `chain/`, `common/` |

WebSocket connects to `/ws`; the frontend falls back to HTTP polling if the connection drops.

### Data Sources
All data is read from `~/.openclaw/` (override via `OPENCLAW_STATE_DIR` or `OPENCLAW_HOME`):
- `openclaw.json` — agent config, model settings
- `agents/<id>/sessions/sessions.json` + `*.jsonl` — session history and messages
- `subagents/runs.json` — sub-agent run records

### Key Environment Variables (Backend)
| Variable | Default | Effect |
|----------|---------|--------|
| `OPENCLAW_STATE_DIR` | — | Overrides all path resolution (highest priority) |
| `OPENCLAW_HOME` | `$HOME` | Sets `~` for `.openclaw` path resolution |
| `OPENCLAW_CACHE_TTL` | `1` (sec) | Status cache TTL |
| `OPENCLAW_CACHE_MAX_SIZE` | `100` (MB) | Cache memory cap |
| `OPENCLAW_AUTO_REPAIR_JSON` | `true` | Auto-repair malformed JSONL lines |
| `OPENCLAW_ENABLE_FALLBACK` | `true` | Serve stale cache on IO errors |

Full list in `src/backend/core/config_fortify.py`.

## Test Fixtures
`src/backend/tests/conftest.py` provides:
- `reset_fortify_state` (autouse) — resets all singletons between tests (cache, error handler, fallback manager, config)
- `fake_openclaw_root` — a `tmp_path`-based fake `.openclaw/` directory with sessions index and JSONL fixtures

When writing tests that start the FastAPI `TestClient`, stub out the file watcher:
```python
monkeypatch.setattr(fw, "start_file_watcher", lambda loop: None)
monkeypatch.setattr(fw, "stop_file_watcher", lambda: None)
```
