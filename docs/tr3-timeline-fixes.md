# TR3: 时序视图优化 - 工具执行状态与视角显示

## 状态: ✅ 已完成

## 背景
OpenClaw Agent Dashboard 的时序视图存在三个问题需要修复：

1. **工具执行失败误判**: exec 工具经常显示执行失败，但实际可能只是退出码非0
2. **子代理视角错误**: 子代理（如分析师）收到主代理消息时，显示"子代理回传"，应显示发送者名称
3. **回传来源不明确**: 主代理时序中子代理回传没有显示具体子代理名字

## 需求详情

### REQ-1: 修复工具执行状态判断逻辑

**问题分析**:
- 当前代码只检查 `details.status == 'error'`
- 但有些工具执行可能 `details.status = 'completed'` 但 `exitCode != 0` 或 `isError = true`
- 例如 bash 命令 `exitCode=1` 会被误判为成功

**解决方案**:
1. 检查 `isError` 字段（优先级最高）
2. 检查 `exitCode` 是否为非0
3. 检查 `details.status == 'error'`
4. 任何一个条件满足都标记为失败

**涉及文件**:
- `src/backend/data/timeline_reader.py`
- `plugin/dashboard/data/timeline_reader.py`

### REQ-2: 修复子代理视角的消息来源显示

**问题分析**:
- 当前 `_detect_subagent_sender` 函数是从主代理视角设计的
- 子代理收到主代理的消息时，显示"子代理回传"是错误的
- 应该根据当前 Agent 的角色来决定显示内容

**解决方案**:
1. 子代理视角：收到消息应显示发送者名称（如"老K发来任务"）
2. 主代理视角：子代理回传显示具体子代理名字（如"分析师回传"）
3. 通过 `requester_info` 获取真实的发送者信息

**涉及文件**:
- `src/backend/data/timeline_reader.py`
- `plugin/dashboard/data/timeline_reader.py`

### REQ-3: 主代理视角的子代理回传显示具体名字

**问题分析**:
- 当前轮次触发器只显示"子代理回传"，没有具体名字
- 难以区分是哪个子代理的回传

**解决方案**:
1. 在轮次构建时，正确解析并显示子代理名称
2. 轮次触发器显示格式："↩️ 分析师回传" 或 "↩️ 架构师回传"

**涉及文件**:
- `src/backend/data/timeline_reader.py`
- `plugin/dashboard/data/timeline_reader.py`
- `frontend/src/components/timeline/TimelineRound.vue`（可能需要调整显示逻辑）

## 实现步骤

### Step 1: 修复工具执行状态判断（REQ-1）

修改 `_parse_session_file` 函数中的 toolResult 处理逻辑：

```python
# 原代码
result_status = details.get('status', 'ok')

# 修改为：综合考虑 isError、exitCode 和 status
is_error = (
    msg.get('isError') == True or
    details.get('exitCode', 0) != 0 or
    details.get('status') == 'error'
)
result_status = 'error' if is_error else 'ok'
```

### Step 2: 修复子代理视角的消息来源（REQ-2）

修改 user 消息处理逻辑，区分主代理和子代理视角：

```python
# 子代理视角：requester_info 中有发送者信息
if requester_info and sender_name:
    # 子代理收到主代理的消息
    display_sender = f"{sender_name}发来"
else:
    # 主代理视角：检测是否为子代理回传
    subagent_label = _detect_subagent_sender(user_text)
    display_sender = subagent_label or "用户"
```

### Step 3: 优化轮次触发器显示（REQ-3）

修改 `_build_llm_rounds` 函数，正确解析子代理名称：

```python
# 从 user 步骤的 senderName 提取子代理名称
sender_name = step.get('senderName', '')
if sender_name and '回传' in sender_name:
    trigger = 'subagent_result'
    trigger_by = sender_name  # 已经是 "分析师回传" 格式
```

## 验收标准

1. 工具执行状态准确，不再有误判的失败
2. 子代理视角下，第一条消息显示发送者名称（如"老K"）
3. 主代理视角下，轮次触发器显示具体子代理名称

## 测试用例

### TC-1: 工具执行状态
- 输入: `exitCode=1, status=completed` 的 toolResult
- 期望: 显示为失败状态

### TC-2: 子代理视角
- 输入: 分析师 Agent 的时序数据，第一条 user 消息来自老K
- 期望: 显示"老K"而非"子代理回传"

### TC-3: 主代理视角
- 输入: 主代理时序数据，包含分析师回传
- 期望: 轮次显示"↩️ 分析师回传"

## 时间估算
- 实现时间: 30分钟
- 测试验证: 15分钟
