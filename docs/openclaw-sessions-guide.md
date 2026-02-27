# OpenClaw 会话管理与 openclaw-agent-dashboard 使用说明

本文档说明 OpenClaw 的会话（sessions）管理机制，以及 openclaw-agent-dashboard 如何读取和使用这些会话数据。

---

## 一、OpenClaw 会话管理

### 1.1 目录结构

```
~/.openclaw/agents/<agentId>/sessions/
├── sessions.json          # 会话索引（sessionKey → SessionEntry）
├── <sessionId>.jsonl     # 当前活跃的会话记录
├── <sessionId>.jsonl.reset.<timestamp>   # 重置前的归档
├── <sessionId>.jsonl.deleted.<timestamp>  # 删除前的归档
└── archive/               # 压缩/归档目录
```

**示例路径**（agentId = main）：
```
/home/ubuntu/.openclaw/agents/main/sessions/
├── sessions.json
├── 9472e015-c7e0-417a-b9ad-1f98e240c0a7.jsonl   # 当前默认会话
├── fb3f0b3c-2bb1-4106-baf7-0a01190c9b36.jsonl   # 旧会话（历史保留）
└── ...
```

### 1.2 核心概念

| 概念 | 说明 |
|------|------|
| **sessionKey** | 会话的逻辑键，格式 `agent:<agentId>:<key>`。例如主会话为 `agent:main:main` |
| **sessionId** | 会话的物理 ID（UUID），对应 `.jsonl` 文件名 |
| **sessions.json** | 索引文件，映射 `sessionKey → { sessionId, sessionFile, updatedAt, ... }` |
| **\<sessionId>.jsonl** | 对话记录文件，每行一条 JSON（消息、工具调用、系统事件等） |

### 1.3 sessions.json 结构

```json
{
  "agent:main:main": {
    "sessionId": "9472e015-c7e0-417a-b9ad-1f98e240c0a7",
    "updatedAt": 1772195847527,
    "sessionFile": "/path/to/9472e015-....jsonl",
    "skillsSnapshot": { ... },
    "modelProvider": "zhipu",
    "model": "glm-4.5",
    "inputTokens": 262140,
    "outputTokens": 431,
    ...
  }
}
```

- **sessionId**：当前会话对应的记录文件 ID
- **sessionFile**：可选的显式路径，若存在则优先于 `sessionId` 推导的路径
- 其他字段：技能快照、模型、token 统计、来源等元数据

### 1.4 新会话 vs 老会话

| 场景 | 行为 | 文件变化 |
|------|------|----------|
| **新建会话**（`/new`、`/reset`） | 为当前 sessionKey 创建新的 sessionId | 新建 `<新UUID>.jsonl`，sessions.json 中该 sessionKey 的 sessionId 和 sessionFile 更新为新文件 |
| **旧会话文件** | 不会被删除 | 旧 `.jsonl` 保留在磁盘，可手动切换或归档 |
| **每日重置**（默认 4:00） | 下一条消息时创建新 sessionId | 同上 |
| **空闲过期**（idleMinutes） | 超时后下一条消息创建新 sessionId | 同上 |
| **压缩/归档** | 旧记录可能被归档到 `archive/` | 原文件可能重命名或移动 |

**重要**：新建会话**不会**删除旧的 `.jsonl` 文件，它们会一直保留，只是不再被 sessions.json 引用为当前会话。

### 1.5 会话文件类型

| 文件模式 | 说明 |
|----------|------|
| `*.jsonl` | 活跃会话记录，被 OpenClaw 和 Dashboard 读取 |
| `*.jsonl.reset.<ts>` | 重置前的归档，通常不参与统计 |
| `*.jsonl.deleted.<ts>` | 删除前的归档，通常不参与统计 |
| `*.lock` | 锁文件，读取时应跳过 |

---

## 二、openclaw-agent-dashboard 如何使用 sessions

Dashboard 通过**直接读取文件系统**访问 `~/.openclaw/agents/*/sessions/`，不经过 OpenClaw Gateway。

### 2.1 数据读取概览

| 模块 | 文件 | 读取范围 | 用途 |
|------|------|----------|------|
| **session_reader** | `data/session_reader.py` | 单个「最新」.jsonl | 最近消息、错误检测 |
| **performance** | `api/performance.py` | 所有 agent 的**所有** .jsonl | TPM/RPM 统计、按分钟详情 |
| **collaboration** | `api/collaboration.py` | 所有 agent 的**所有** .jsonl | 协作流程图、最近模型调用 |

### 2.2 session_reader.py

```python
# 获取「按修改时间最新」的一个 .jsonl
get_latest_session_file(agent_id)
# → 遍历 agents/<id>/sessions/*.jsonl，按 st_mtime 排序取第一个

# 读取该文件全部行，解析后取最后 N 条
get_recent_messages(agent_id, limit=10)
# → 整文件逐行解析，messages[-limit:]
```

- **特点**：只读「最新」的一个文件，但会**完整解析**该文件
- **风险**：若最新文件很大（如 800KB+），解析会变慢

### 2.3 performance.py

```python
# 遍历所有 agent、所有 .jsonl
for agent_dir in agents_path.iterdir():
    for session_file in sessions_path.glob('*.jsonl'):
        if 'lock' in session_file.name or 'deleted' in session_file.name:
            continue
        messages = parse_session_file(session_file)  # 逐行解析
        # 或
        records = parse_session_file_with_details(session_file, agent_id)
```

- **特点**：遍历**所有** `.jsonl`（跳过含 `lock`、`deleted` 的文件名）
- **用途**：TPM/RPM 统计、按分钟钻取、调用详情
- **风险**：大文件多时，API 响应变慢

### 2.4 collaboration.py

```python
# _get_recent_model_calls() 同样遍历所有 .jsonl
for session_file in sessions_path.glob('*.jsonl'):
    if 'lock' in session_file.name or 'deleted' in session_file.name:
        continue
    for r in parse_session_file_with_details(session_file, agent_id):
        # 过滤最近 N 分钟
```

- **用途**：协作流程图中的「最近模型调用」光球展示
- **风险**：同上，大文件会拖慢接口

### 2.5 与 OpenClaw Control UI 的对比

| 项目 | 数据来源 | 读取方式 |
|------|----------|----------|
| **OpenClaw Control UI** | Gateway WebSocket `chat.history` RPC | 后端 `readFileSync` 读 sessions.json 中 sessionKey 对应的 sessionFile/sessionId 指向的 .jsonl |
| **openclaw-agent-dashboard** | 直接读 `~/.openclaw/agents/*/sessions/` | Python 逐行读取，遍历所有 .jsonl |

两者都会受大 session 文件影响：Control UI 易卡死，Dashboard 易变慢。

---

## 三、大文件问题与建议

### 3.1 问题根因

- **OpenClaw**：`chat.history` 用 `fs.readFileSync` 一次性读入整个 .jsonl，大文件会阻塞主线程
- **Dashboard**：逐行读取，但会解析每一行，大文件多时仍会明显变慢

### 3.2 建议

1. **定期新建会话**：在 Control UI 或 TUI 中 `/new` 或新建会话，避免单会话无限增长
2. **监控文件大小**：`ls -lh ~/.openclaw/agents/main/sessions/*.jsonl`，对 >500KB 的考虑归档
3. **归档旧会话**：将不常用的大文件移到 `archive/` 或备份后删除，减少 Dashboard 扫描量

---

## 四、路径速查

| 项目 | 路径 |
|------|------|
| 会话索引 | `~/.openclaw/agents/<agentId>/sessions/sessions.json` |
| 会话记录 | `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl` |
| 主 agent 示例 | `~/.openclaw/agents/main/sessions/` |
| Dashboard 根路径 | `Path.home() / ".openclaw"` |
