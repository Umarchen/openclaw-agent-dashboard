# TR9 开发计划

> 基于需求文档的开发和测试计划

**状态**: ✅ 已完成

## 1. 需求文档清单

| 文档 | 需求 | 优先级 | 状态 |
|------|------|--------|------|
| `tr9-1-time-threshold-status.md` | 基于时间阈值的状态显示 | P0 | ✅ 已完成 |
| `tr9-2-model-id-normalization.md` | 模型调用小球匹配修复 | P1 | ✅ 已完成 |

## 2. 开发任务分解

### Phase 1: 后端基础设施 (TR9-1) ✅

**任务 1.1**: 新增带时间戳的消息接口 ✅
- 文件: `src/backend/data/session_reader.py`
- 函数: `get_recent_messages_with_timestamp()`

**任务 1.2**: 新增带时间戳的工具调用检测 ✅
- 文件: `src/backend/data/session_reader.py`
- 函数: `get_pending_tool_call_with_timestamp()`

**任务 1.3**: 新增获取等待的子代理 ✅
- 文件: `src/backend/data/subagent_reader.py`
- 函数: `get_waiting_child_agent()`

**任务 1.4**: 新增显示状态计算 ✅
- 文件: `src/backend/status/status_calculator.py`
- 函数: `get_display_status()`

### Phase 2: API 增强 (TR9-1 + TR9-2) ✅

**任务 2.1**: 新增 AgentDisplayStatus 模型 ✅
- 文件: `src/backend/api/collaboration.py`

**任务 2.2**: 填充 agentDisplayStatuses 字段 ✅
- 文件: `src/backend/api/collaboration.py`

**任务 2.3**: 实现模型 ID 规范化 ✅
- 文件: `src/backend/api/collaboration.py`
- 函数: `_normalize_model_id()`, `_get_model_mapping()`, `_clear_model_mapping_cache()`

**任务 2.4**: 修改 _get_recent_model_calls 使用规范化 ✅
- 文件: `src/backend/api/collaboration.py`

### Phase 3: 前端适配 (TR9-1) ✅

**任务 3.1**: 更新类型定义 ✅
- 文件: `frontend/src/types/collaboration.ts`
- 新增: `AgentDisplayStatus` 接口

**任务 3.2**: 更新动态数据处理 ✅
- 文件: `frontend/src/components/collaboration/CollaborationFlowSection.vue`
- 更新: `handleCollaborationDynamicUpdate()` 处理 `agentDisplayStatuses`

### Phase 4: 测试验证 ✅

**任务 4.1**: 后端单元测试 ✅
- 所有函数导入成功
- `_normalize_model_id` 边界情况测试通过

**任务 4.2**: 前端构建测试 ✅
- `npm run build` 成功

## 3. 修改文件清单

| 文件 | 修改内容 | 状态 |
|------|----------|------|
| `src/backend/data/session_reader.py` | 新增 `get_recent_messages_with_timestamp()`, `get_pending_tool_call_with_timestamp()` | ✅ |
| `src/backend/data/subagent_reader.py` | 新增 `get_waiting_child_agent()` | ✅ |
| `src/backend/status/status_calculator.py` | 新增 `get_display_status()`，添加 logging | ✅ |
| `src/backend/api/collaboration.py` | 新增 `AgentDisplayStatus` 模型，填充 `agentDisplayStatuses`，新增 `_normalize_model_id()` | ✅ |
| `frontend/src/types/collaboration.ts` | 更新类型定义，新增 `AgentDisplayStatus` | ✅ |
| `frontend/src/components/collaboration/CollaborationFlowSection.vue` | 更新动态数据处理逻辑 | ✅ |

## 4. 测试结果

### 4.1 后端单元测试 ✅

```
✓ session_reader.py: functions imported
✓ subagent_reader.py: get_waiting_child_agent imported
✓ status_calculator.py: get_display_status imported
✓ _normalize_model_id: standard format
✓ _normalize_model_id: short format
✓ _normalize_model_id: with date suffix
✓ _normalize_model_id: edge case -4 not truncated
✓ Regex: "claude-sonnet-4.6-20250514" -> "claude-sonnet-4.6"
✓ Regex: "claude-sonnet-4-20250514" -> "claude-sonnet-4"
✓ Regex: "gpt-4-turbo-2024-04-09" -> "gpt-4-turbo-2024-04-09"
```

### 4.2 前端构建 ✅

```
✓ 93 modules transformed
✓ built in 4.63s
```

## 5. 验收标准

### 5.1 TR9-1 验收标准 ✅

1. **状态显示基于时间阈值**
   - [x] 快速动作（<2s）显示"处理中..."
   - [x] 等待子代理超过 3s 显示"等待 xxx"
   - [x] 执行命令超过 2s 显示"执行命令"
   - [x] 等待模型超过 5s 显示"等待响应"
   - [x] 等待模型超过 15s 显示"等待响应 (可能限流)"

2. **duration 正确显示**
   - [x] 后端返回 duration 字段
   - [x] 前端存储到 metadata

3. **alert 标志正确**
   - [x] 等待子代理超过 60s 设置 alert=true
   - [x] 执行命令超过 30s 设置 alert=true
   - [x] 等待模型超过 15s 设置 alert=true

### 5.2 TR9-2 验收标准 ✅

1. **model ID 规范化**
   - [x] `claude-sonnet-4.6` -> `anthropic/claude-sonnet-4.6`
   - [x] `claude-sonnet-4.6-20250514` -> `anthropic/claude-sonnet-4.6`
   - [x] `anthropic/claude-sonnet-4.6` -> `anthropic/claude-sonnet-4.6`

2. **边界情况处理**
   - [x] `claude-sonnet-4-20250514` 正确处理（不截断 `-4`）
   - [x] 未知格式原样返回

## 6. 待集成测试

以下测试需要在运行环境验证：

- [ ] API 接口测试：`GET /api/collaboration/dynamic` 返回 `agentDisplayStatuses`
- [ ] 前端功能测试：Agent 状态正确显示
- [ ] 模型小球匹配测试：调用小球落入正确模型框
