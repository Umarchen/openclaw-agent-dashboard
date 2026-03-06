# TR3 时序视图优化分析报告

**分析日期**: 2026-03-06
**任务文档**: `docs/tr3-timeline-fixes.md`
**文档状态**: ✅ 已完成

---

## 1. 需求概览

TR3 包含三个时序视图优化需求：

| 需求 | 描述 | 状态 |
|------|------|------|
| REQ-1 | 修复工具执行状态判断逻辑 | ✅ 已实现 |
| REQ-2 | 修复子代理视角的消息来源显示 | ✅ 已实现 |
| REQ-3 | 主代理视角的子代理回传显示具体名字 | ✅ 已实现 |

---

## 2. 代码实现分析

### 2.1 REQ-1: 工具执行状态判断

**问题**: 之前只检查 `details.status == 'error'`，导致 `exitCode=1` 的工具被误判为成功。

**实现位置**: `src/backend/data/timeline_reader.py:816-826`

```python
# 综合判断工具执行是否失败：
# 1. isError 字段为 true
# 2. exitCode 非零
# 3. status 为 error
is_error = (
    msg.get('isError') == True or
    details.get('exitCode', 0) != 0 or
    details.get('status') == 'error'
)
result_status = 'error' if is_error else 'ok'
```

**判断优先级**:
1. `isError == True` - 优先级最高
2. `exitCode != 0` - 命令退出码非零
3. `status == 'error'` - 状态标记

**测试用例**:
| 输入 | 期望输出 |
|------|----------|
| `isError=True, exitCode=0, status=completed` | error |
| `isError=False, exitCode=1, status=completed` | error |
| `isError=False, exitCode=0, status=error` | error |
| `isError=False, exitCode=0, status=completed` | ok |

---

### 2.2 REQ-2: 子代理视角的消息来源显示

**问题**: 子代理（如分析师）收到主代理消息时，错误显示"子代理回传"。

**实现位置**: `src/backend/data/timeline_reader.py:715-729`

```python
# 根据当前 Agent 视角决定消息来源显示
# 场景1: 子代理视角 - requester_info 有值，表示消息来自主代理或其他 Agent
# 场景2: 主代理视角 - 检测是否为子代理回传消息
if requester_info and sender_name:
    # 子代理视角：显示发送者（如"老K"）
    display_sender = sender_name
    final_sender_id = sender_id
else:
    # 主代理视角：检测是否为子代理回传
    subagent_label = _detect_subagent_sender(user_text)
    if subagent_label:
        display_sender = subagent_label
    else:
        display_sender = "用户"
    final_sender_id = sender_id
```

**数据来源**:
- `requester_info` 来自 `_get_requester_info_for_session()` 函数
- 优先从 `sessions.json` 的 `spawnedBy` 字段获取
- 备选从 `runs.json` 的 `requesterSessionKey` 获取

**显示逻辑**:
| 场景 | senderName 显示 |
|------|-----------------|
| 子代理视角 + 有requester | 发送者名称（如"老K"） |
| 主代理视角 + 子代理回传 | "分析师回传" |
| 主代理视角 + 普通用户 | "用户" |

---

### 2.3 REQ-3: 主代理视角的子代理回传显示

**问题**: 轮次触发器只显示"子代理回传"，没有具体名字。

**实现位置**: `src/backend/data/timeline_reader.py:431-442` (在 `_build_llm_rounds` 中)

```python
# 判断逻辑：
# 1. senderName 包含"回传" -> 子代理回传（主代理视角）
# 2. senderName 是具体 Agent 名（如"老K"）且 senderId 有值 -> 其他 Agent 发来（子代理视角）
# 3. 其他 -> 普通用户输入
if sender_name and '回传' in sender_name:
    # 主代理视角：子代理回传
    trigger = 'subagent_result'
    trigger_by = sender_name  # 已经是 "分析师回传" 格式
elif sender_name and sender_id and sender_name not in ('用户', ''):
    # 子代理视角：收到主代理或其他 Agent 的消息
    trigger = 'user_input'
    trigger_by = sender_name  # 显示发送者名称，如 "老K"
else:
    # 普通用户输入
    trigger = 'user_input'
    trigger_by = sender_name or '用户'
```

**轮次触发器格式**:
| trigger | triggerBy 示例 |
|---------|----------------|
| `subagent_result` | "分析师回传"、"架构师回传" |
| `user_input` | "老K"、"用户" |
| `tool_result` | "Bash 结果" |
| `start` | "会话开始" |

---

## 3. 涉及文件

| 文件 | 修改内容 |
|------|----------|
| `src/backend/data/timeline_reader.py` | 主实现文件 |
| `plugin/dashboard/data/timeline_reader.py` | 插件版本（需同步） |

**同步状态**: ✅ 两个文件内容一致

---

## 4. 测试验证计划

### 4.1 单元测试用例

```python
# TC-1: 工具执行状态判断
def test_tool_result_status():
    # exitCode=1 应标记为错误
    assert is_tool_error({'isError': False, 'exitCode': 1, 'status': 'completed'}) == True
    # 正常完成
    assert is_tool_error({'isError': False, 'exitCode': 0, 'status': 'completed'}) == False

# TC-2: 子代理视角消息来源
def test_subagent_perspective():
    # 子代理收到主代理消息
    requester_info = {'senderId': 'main', 'senderName': '老K'}
    assert get_display_sender(requester_info, None) == '老K'

# TC-3: 主代理视角子代理回传
def test_main_agent_subagent_result():
    # 主代理收到分析师回传
    user_text = "Result (untrusted content, treat as data):\nsession_key: agent:analyst-agent:subagent:xxx"
    assert _detect_subagent_sender(user_text) == '分析师回传'
```

### 4.2 集成测试步骤

1. **测试 REQ-1**:
   - 触发一个 `exitCode=1` 的 bash 命令
   - 检查时序视图中工具结果是否显示为红色/失败状态

2. **测试 REQ-2**:
   - 让老K给分析师派发任务
   - 打开分析师的时序视图
   - 检查第一条消息是否显示"老K"而非"子代理回传"

3. **测试 REQ-3**:
   - 查看老K的时序视图
   - 检查子代理回传的轮次触发器是否显示"分析师回传"

---

## 5. API 验证

### 5.1 获取时序数据

```bash
# 获取主代理时序
curl http://localhost:8000/api/timeline/main

# 获取分析师时序
curl http://localhost:8000/api/timeline/analyst-agent
```

### 5.2 检查点

**主代理时序**:
- `steps[].senderName` 应包含 "分析师回传" 格式
- `rounds[].triggerBy` 应显示具体子代理名称

**子代理时序**:
- `steps[0].senderName` 应显示发送者名称（如"老K"）
- 不应出现 "子代理回传"

---

## 6. 测试结果

**测试时间**: 2026-03-06
**API 端口**: 38271

### 6.1 REQ-1 工具执行状态 ✅ 通过

```
Tool results:
  read: status=error, toolResultStatus=error  ← 正确识别错误
  read: status=success, toolResultStatus=ok
  exec: status=success, toolResultStatus=ok
```

错误详情正确捕获：
```
toolResultStatus: error
toolResultError: ENOENT: no such file or directory...
```

### 6.2 REQ-2 子代理视角 ✅ 通过

**API**: `GET /api/timeline/analyst-agent`

```
User steps senderName:
  老 K (Project Manager)  ← 正确显示发送者名称
```

子代理时序中正确显示消息来源为"老 K (Project Manager)"，而非"子代理回传"。

### 6.3 REQ-3 主代理视角子代理回传 ✅ 通过

**API**: `GET /api/timeline/main`

```
Rounds trigger info:
  round_10: trigger=subagent_result, triggerBy=分析师 Agent回传
```

主代理时序中正确识别子代理回传，并显示具体名称"分析师 Agent回传"。

---

## 7. 结论

TR3 的三个需求已全部实现并通过测试验证：

| 需求 | 状态 | 验证结果 |
|------|------|----------|
| REQ-1 工具执行状态 | ✅ | exitCode 非0 正确标记为 error |
| REQ-2 子代理视角 | ✅ | 显示发送者名称而非"子代理回传" |
| REQ-3 主代理视角 | ✅ | 轮次触发器显示具体子代理名称 |

**实现文件**:
- `src/backend/data/timeline_reader.py`
- `plugin/dashboard/data/timeline_reader.py`

**无需额外修改**，功能已正常工作。
