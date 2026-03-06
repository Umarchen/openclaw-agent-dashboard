# TR4: Dashboard 优化 - 状态刷新与模型球显示

## 状态: ✅ 已完成

## 背景
基于 `docs/dashboard-analysis.md` 的分析报告，Dashboard 存在以下问题需要修复：

1. **任务结束后状态不准确**: Agent 完成任务后仍显示"工作中"
2. **模型球显示位置不对**: 分析师主模型是 glm-5，但绿球显示在 glm-4.7
3. **子 Agent 模型调用不刷新**: 子 Agent 的 LLM 调用不会显示在模型面板
4. **时序视图更新延迟**: 子 Agent 视图更新比主 Agent 慢
5. **任务截断问题**: Agent 卡片中当前任务被截断，无法查看完整内容
6. **阻塞检测不精确**: 无法准确判断 Agent 正在等待什么

## 需求详情

### REQ-1: 修复任务结束后状态不准确

**问题分析**:
- `has_recent_session_activity(agent_id, minutes=5)` 检测窗口过长
- 即使任务已完成，5分钟内有活动就仍显示"工作中"
- WebSocket 广播间隔 8 秒，前端轮询 5 秒，延迟较大

**解决方案**:
1. 将 session 活动检测窗口从 5 分钟改为 2 分钟
2. 将 WebSocket 广播间隔从 8 秒改为 3 秒
3. 将前端动态轮询从 5 秒改为 3 秒

**涉及文件**:
- `src/backend/status/status_calculator.py:39` - 修改 `minutes=5` 为 `minutes=2`
- `src/backend/api/websocket.py:19` - 修改 `BROADCAST_INTERVAL_SEC = 8` 为 `3`
- `frontend/src/components/collaboration/CollaborationFlowSection.vue:178` - 修改 `5000` 为 `3000`

### REQ-2: 修复模型球显示位置问题

**问题分析**:
- 分析师配置的主模型是 `zhipu/glm-5`
- 但实际调用时可能使用了 fallback 模型 `zhipu/glm-4.7`
- `recentCalls` 中记录的是实际使用的模型（如 `glm-4.7`）
- 前端按实际使用模型匹配，所以球显示在 glm-4.7 下

**当前数据**:
```
Agent Models:
  analyst-agent: {'primary': 'zhipu/glm-5', 'fallbacks': ['zhipu/glm-4.7', ...]}

Recent Calls:
  analyst-agent: model=glm-4.7  ← 实际使用的模型
```

**解决方案**:
1. 模型球应该显示在**实际使用的模型**下面（这是正确的行为）
2. 但需要在光球上显示 Agent 颜色，表示是哪个 Agent 的调用
3. 增加 tooltip 显示更多信息（Agent 名称 + 实际模型）

**涉及文件**:
- `frontend/src/components/collaboration/CollaborationFlowSection.vue:398-406` - 优化模型匹配逻辑
- `frontend/src/components/collaboration/CollaborationFlowSection.vue:121-131` - 增强光球显示

### REQ-3: 子 Agent 模型调用获取优化

**问题分析**:
- `_get_recent_model_calls()` 已经遍历所有 Agent 目录
- 但 `parse_session_file_with_details()` 从 session 中提取 model 字段
- session 文件中 model 字段格式可能不一致

**解决方案**:
1. 检查 session 文件中 model 字段的实际格式
2. 确保正确解析 `zhipu/glm-5` 格式的模型名
3. 添加日志便于调试

**涉及文件**:
- `src/backend/api/performance.py:126` - 检查 model 字段解析
- `src/backend/api/collaboration.py:226-265` - 增加日志

### REQ-4: 时序视图更新延迟优化

**问题分析**:
- FileWatcher 在启动时只监听已存在的目录
- 新创建的 Agent 目录不会被监听
- 导致子 Agent session 更新不及时

**解决方案**:
1. 增加动态监听新 Agent 目录的功能
2. 或定期刷新监听目录列表

**涉及文件**:
- `src/backend/watchers/file_watcher.py` - 增加动态监听

### REQ-5: 任务截断问题优化

**问题分析**:
- 后端截断 50 字符，协作 API 截断 80 字符，不一致
- 无法查看完整任务描述

**解决方案**:
1. 统一截断长度为 60 字符
2. 增加鼠标悬停显示完整任务（title 属性）

**涉及文件**:
- `src/backend/status/status_calculator.py:85-88` - 统一截断长度
- `frontend/src/components/AgentCard.vue:40` - 增加 title 属性

### REQ-6: 阻塞检测优化

**问题分析**:
- 检测阈值单一（60 秒）
- 等待对象不明确

**解决方案**:
1. 分级检测阈值：warning(45s), attention(90s), critical(180s)
2. 更精确的等待对象检测

**涉及文件**:
- `src/backend/api/collaboration.py:155` - 修改阈值
- `src/backend/api/collaboration.py:169-223` - 优化原因分析

## 实现步骤

### Step 1: REQ-1 状态刷新优化

```python
# status_calculator.py:39
# 改前
if has_recent_session_activity(agent_id, minutes=5):
# 改后
if has_recent_session_activity(agent_id, minutes=2):
```

```python
# websocket.py:19
# 改前
BROADCAST_INTERVAL_SEC = 8
# 改后
BROADCAST_INTERVAL_SEC = 3
```

```typescript
// CollaborationFlowSection.vue:178
// 改前
const DYNAMIC_POLL_INTERVAL_MS = 5000
// 改后
const DYNAMIC_POLL_INTERVAL_MS = 3000
```

### Step 2: REQ-2 模型球显示优化

确保模型球正确显示在**实际使用的模型**下，并增强 tooltip：

```vue
<span
  v-for="call in getCallsForModelNode(modelNode).slice(0, 8)"
  :key="call.id"
  class="model-dot"
  :style="{ background: getAgentColor(call.agentId) }"
  :title="`${call.agentId} @ ${call.model}`"
/>
```

### Step 3: REQ-5 任务截断优化

```python
# status_calculator.py
def get_current_task(agent_id: str) -> str:
    runs = get_agent_runs(agent_id, limit=1)
    if not runs:
        return ''
    task = runs[0].get('task', '')
    # 统一截断为 60 字符
    if len(task) > 60:
        task = task[:57] + '...'
    return task
```

```vue
<!-- AgentCard.vue -->
<div class="task-name" :title="fullTask">{{ truncatedTask }}</div>
```

## 验收标准

1. Agent 完成任务后 2 分钟内状态变为"空闲"
2. 模型球显示在正确的模型节点下，tooltip 显示 Agent 和模型信息
3. 前端状态更新延迟不超过 3 秒
4. 鼠标悬停在任务上可查看完整描述
5. 阻塞警告分级显示

## 测试用例

### TC-1: 状态刷新
- 操作: 完成一个任务后等待
- 期望: 2 分钟内状态从"工作中"变为"空闲"

### TC-2: 模型球显示
- 操作: 查看协作流程右侧模型面板
- 期望: 绿球显示在实际使用的模型下，hover 显示 Agent 名

### TC-3: 任务截断
- 操作: 鼠标悬停在 Agent 卡片的任务上
- 期望: 显示完整任务描述

## 时间估算
- 实现时间: 45 分钟
- 测试验证: 15 分钟

## 依赖
- TR3 已完成 ✅
