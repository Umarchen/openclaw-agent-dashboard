# OpenClaw Agent Dashboard — 修改点汇总

本文档汇总近期对 **openclaw-agent-dashboard** 工程的修改，便于他人评审与追溯。  
修改范围：TPM/RPM 统计、连接状态、Windows 启动、调试能力及文档。

---

## 一、TPM 趋势无值 / 多接口 usage 兼容

### 问题
- 性能监控中 **TPM 趋势** 一直为 0，RPM 趋势有值。
- 原因：TPM 仅依赖 `usage.totalTokens`，而不同大模型/网关返回的 usage 格式不一（如 `input`/`output`、`input_tokens`/`output_tokens` 等），或上游未写入 totalTokens 导致为 0。

### 修改策略
- **不再枚举字段名**：采用两段逻辑——
  1. 若有明确总量字段（`totalTokens` / `total_tokens` / `total`）且 > 0，直接使用；
  2. 否则对 `usage` 内**所有数值**求和作为总 token 数，兼容任意命名。
- 避免对同一用量重复计算：有总量时只返回总量，不再参与求和。

### 涉及文件
| 文件 | 修改内容 |
|------|----------|
| `plugin/dashboard/api/performance.py` | `_tokens_from_usage()` 重写；新增 `GET /api/performance/debug-usage` 调试接口 |
| `src/backend/api/performance.py` | 同上（与 plugin 保持一致的逻辑与调试接口） |
| `plugin/dashboard/performance.py` | `_tokens_from_usage()` 与 plugin api 一致 |
| `src/backend/performance.py` | 同上 |

### 调试接口
- **GET** `/api/performance/debug-usage?limit=5`
- 返回：`openclaw_path`、`agents_path_exists`、`samples[]`（含 `usage_raw`、`tokens_computed`）。
- 用于确认 session 中实际 usage 结构及 TPM 为 0 是否因上游未写入 token 数。

### 说明
- 若 session 中 `usage` 各字段均为 0（如部分 vLLM/本地模型未回传 token），TPM 仍会为 0，需在**写 session 的上游**（OpenClaw/网关/模型适配层）补齐 usage 写入。

---

## 二、右上角「连接错误」与 WebSocket 回退

### 问题
- Dashboard 右上角连接状态显示「连接错误」。
- 原因：WebSocket `ws://localhost:38271/ws` 连接失败或建立后因发送初始状态异常而断开；前端未及时进入 HTTP 轮询。

### 后端修改
- **发送初始状态失败时**：捕获异常后仍发送最小 `full_state` payload（空列表/空对象），保持连接不因异常关闭。
- **心跳协议**：同时支持纯文本 `ping` 与 JSON `{"type":"ping",...}`，并统一以 JSON 回复 `{"type":"pong",...}`，与前端一致。

### 前端修改
- **WebSocket onerror**：除设置状态为 error 外，调用 `handleDisconnect()`，进入重连或 HTTP 轮询，避免一直停在「连接错误」。
- **重连次数**：默认由 5 次改为 3 次，更快 fallback 到 HTTP 轮询。

### 涉及文件
| 文件 | 修改内容 |
|------|----------|
| `plugin/dashboard/api/websocket.py` | 初始状态异常时发最小 payload；心跳支持 JSON ping/pong |
| `src/backend/api/websocket.py` | 同上 |
| `frontend/src/managers/RealtimeDataManager.ts` | onerror 时调用 handleDisconnect()；reconnectMaxAttempts 默认 3 |

---

## 三、Windows 下 `npm run start` 报错

### 问题
- 在 Windows PowerShell 执行 `npm run start` 报错：`'OPENCLAW_HOME' 不是内部或外部命令`。
- 原因：`package.json` 的 start 脚本使用 Linux/Mac 环境变量语法（`OPENCLAW_HOME=${OPENCLAW_HOME:-$HOME/.openclaw} ...`），在 Windows CMD 下无法解析。

### 修改
- 新增 **Node 跨平台启动脚本** `scripts/start.js`：
  - 根据 `OPENCLAW_HOME`、`DASHBOARD_PORT` 环境变量或默认值设置；
  - Windows 使用 `python`，非 Windows 使用 `python3`；
  - 在 `src/backend` 目录下执行 `uvicorn main:app --host 0.0.0.0 --port <port>`。
- **package.json**：`start` 脚本改为 `node scripts/start.js`。

### 涉及文件
| 文件 | 修改内容 |
|------|----------|
| `scripts/start.js` | 新增，跨平台启动 Dashboard 后端 |
| `package.json` | `"start": "node scripts/start.js"` |

### 说明
- 不影响 Ubuntu/Debian 等 Linux 行为；若已设置 `OPENCLAW_HOME`、`DASHBOARD_PORT`，仍会生效。

---

## 四、文档与运维

### 新增/更新文档
| 文件 | 用途 |
|------|------|
| `RESTART_AND_BUILD.md` | 重启服务、是否需重新打包、一条龙命令（含 Windows PowerShell）；插件部署与独立运行两种方式 |
| `docs/CHANGELOG_AGENT_MODIFICATIONS.md` | 本修改汇总文档，供他人评审 |

---

## 五、修改文件清单（便于 diff / code review）

```
openclaw-agent-dashboard-main/
├── package.json                              # start 改为 node scripts/start.js
├── RESTART_AND_BUILD.md                      # 新增：重启与打包说明
├── scripts/
│   └── start.js                              # 新增：跨平台启动脚本
├── docs/
│   └── CHANGELOG_AGENT_MODIFICATIONS.md      # 本文件
├── frontend/src/managers/
│   └── RealtimeDataManager.ts               # WebSocket 失败回退与重连次数
├── plugin/dashboard/api/
│   ├── performance.py                       # _tokens_from_usage + debug-usage
│   └── websocket.py                          # 初始状态容错 + JSON 心跳
├── plugin/dashboard/
│   └── performance.py                        # _tokens_from_usage 与 api 一致
├── src/backend/api/
│   ├── performance.py                       # 同 plugin/dashboard/api/performance
│   └── websocket.py                          # 同 plugin/dashboard/api/websocket
└── src/backend/
    └── performance.py                        # _tokens_from_usage 与 api 一致
```

---

## 六、建议评审关注点

1. **TPM 逻辑**：`_tokens_from_usage` 先取总量、再对 usage 全数值求和的策略是否满足业务（有无误把非 token 数字加进去的风险）。
2. **WebSocket**：初始状态失败时发最小 payload 是否与前端约定一致；JSON ping/pong 与现有客户端兼容性。
3. **前端**：onerror 时立即 handleDisconnect 与 onclose 的重复调用是否会导致双重重连定时器（当前实现中 scheduleReconnect 会先 stopReconnect，一般只保留一个定时器）。
4. **Windows 启动**：`scripts/start.js` 中 `OPENCLAW_HOME` 默认路径、`python`/`python3` 选择在目标环境是否均可用。

---

**文档版本**：v1.0  
**整理日期**：2026-03-13  
**工程**：openclaw-agent-dashboard（含 plugin 与 src/backend 两套路径）
