# 调用详情钻取模块详细设计

> 文档版本：1.0
> 创建日期：2026-03-07
> 模块类型：性能监控辅助模块

---

## 一、需求概述

### 1.1 功能目标

当用户点击趋势图某个时间点时，展示该时间窗口内的所有 API 调用详情，帮助：
- 追溯具体操作
- 分析高消耗原因
- 排查问题

### 1.2 用户场景

| 场景 | 用户行为 | 期望结果 |
|------|----------|----------|
| 发现 TPM 异常峰值 | 点击该分钟柱体 | 看到是哪个 Agent/任务导致的 |
| 追溯成本 | 查看高消耗时段的详情 | 了解 Token 消耗分布 |
| 问题排查 | 查看特定时间的调用 | 找到相关 Session 和触发内容 |

---

## 二、功能设计

### 2.1 入口

- **唯一入口**：点击 TPM 趋势图的柱体
- 不同时间范围下，点击行为：

| 时间范围 | 点击单位 | 详情时间窗口 |
|----------|----------|--------------|
| 20m | 某一分钟 | 该分钟的调用 |
| 1h | 某一分钟 | 该分钟的调用 |
| 24h | 某一小时 | 该小时的调用 |

### 2.2 详情面板设计

#### 2.2.1 布局

采用 **右侧抽屉 (Drawer)** 或 **模态框 (Modal)** 展示：

```
┌─────────────────────────────────────────────────────┐
│  调用详情 - 2026-03-07 13:05                    ✕  │
├─────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────┐    │
│  │ 总调用: 12  │  总Token: 15,234  │  平均: 1,269 │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ 🔍 搜索调用内容...                           │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Agent: analyst-agent                         │    │
│  │ Token: 5,234  │  时间: 13:05:23              │    │
│  │ ─────────────────────────────────────────── │    │
│  │ 触发内容:                                    │    │
│  │ "分析本周的销售数据，生成报告..."             │    │
│  │                                             │    │
│  │ Session: session_abc123                     │    │
│  │ [查看完整对话 →]                             │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ Agent: main                                  │    │
│  │ Token: 3,456  │  时间: 13:05:45              │    │
│  │ ─────────────────────────────────────────── │    │
│  │ 触发内容:                                    │    │
│  │ "继续执行任务..."                            │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  [加载更多...]                                      │
└─────────────────────────────────────────────────────┘
```

#### 2.2.2 调用条目信息

每个调用条目包含：

| 字段 | 说明 | 来源 |
|------|------|------|
| **Agent 名称** | 执行调用的 Agent | session 文件路径 |
| **Token 数量** | 该调用的 totalTokens | message.usage |
| **时间** | 调用发生时间 | message.timestamp |
| **触发内容** | 用户消息摘要（前100字符） | message.content |
| **Session ID** | 关联的会话标识 | 文件名 |

#### 2.2.3 交互功能

| 功能 | 描述 |
|------|------|
| **搜索过滤** | 在搜索框输入关键词，过滤触发内容 |
| **Agent 筛选** | 下拉选择特定 Agent 的调用 |
| **排序** | 按 Token 降序 / 时间升序 |
| **查看详情** | 点击跳转到该 Session 的完整对话 |

### 2.3 空状态

当该时间窗口无调用时：

```
┌─────────────────────────────────────────────────────┐
│  调用详情 - 2026-03-07 13:05                    ✕  │
├─────────────────────────────────────────────────────┤
│                                                     │
│              📭                                     │
│         该时间段无调用记录                          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 三、后端设计

### 3.1 API 接口

**GET /api/performance/details**

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `timestamp` | number | 是 | 时间戳（毫秒） |
| `granularity` | string | 否 | 粒度：`minute`（默认）或 `hour` |
| `agent` | string | 否 | 筛选指定 Agent |
| `search` | string | 否 | 搜索触发内容 |
| `sort` | string | 否 | 排序：`tokens_desc`（默认）或 `time_asc` |

**响应结构：**

```json
{
  "timeWindow": {
    "start": "2026-03-07T13:05:00Z",
    "end": "2026-03-07T13:05:59Z",
    "label": "2026-03-07 13:05"
  },
  "summary": {
    "totalCalls": 12,
    "totalTokens": 15234,
    "avgTokens": 1269
  },
  "calls": [
    {
      "id": "call_001",
      "agent": "analyst-agent",
      "timestamp": "2026-03-07T13:05:23Z",
      "tokens": 5234,
      "triggerContent": "分析本周的销售数据，生成报告...",
      "sessionId": "session_abc123",
      "messageId": "msg_xyz789"
    }
  ],
  "pagination": {
    "total": 12,
    "offset": 0,
    "limit": 20
  }
}
```

### 3.2 数据获取逻辑

```python
def get_minute_details(timestamp_ms: int, granularity: str = 'minute') -> dict:
    """
    获取指定时间窗口的调用详情

    Args:
        timestamp_ms: 时间戳（毫秒）
        granularity: 'minute' 或 'hour'

    Returns:
        包含调用列表和摘要的字典
    """
    # 1. 确定时间窗口
    if granularity == 'hour':
        start, end = get_hour_range(timestamp_ms)
    else:
        start, end = get_minute_range(timestamp_ms)

    # 2. 遍历所有 agent 的 session 文件
    calls = []
    for agent_dir in get_agent_dirs():
        for session_file in agent_dir.glob('sessions/*.jsonl'):
            for message in parse_session_file(session_file):
                if start <= message.timestamp < end and message.usage:
                    calls.append({
                        'agent': agent_dir.name,
                        'timestamp': message.timestamp,
                        'tokens': message.usage.totalTokens,
                        'triggerContent': extract_trigger(message),
                        'sessionId': session_file.stem,
                        'messageId': message.id
                    })

    # 3. 排序和分页
    calls.sort(key=lambda x: x['tokens'], reverse=True)

    return {
        'timeWindow': {...},
        'summary': calculate_summary(calls),
        'calls': calls[:20]
    }
```

### 3.3 触发内容提取

```python
def extract_trigger(message: dict) -> str:
    """
    提取用户消息作为触发内容

    规则：
    1. 查找 message 前最近的 user 角色消息
    2. 取内容前 100 字符
    3. 如果是工具调用，显示工具名称
    """
    content = message.get('content', '')
    if isinstance(content, list):
        # 处理多部分内容
        text_parts = [p.get('text', '') for p in content if p.get('type') == 'text']
        content = ' '.join(text_parts)

    # 截取前 100 字符
    return content[:100] + ('...' if len(content) > 100 else '')
```

---

## 四、前端设计

### 4.1 组件结构

```
CallDetailsDrawer.vue (新建)
├── DetailsHeader.vue          # 标题和时间窗口信息
├── DetailsSummary.vue         # 摘要统计
├── DetailsFilter.vue          # 搜索和筛选
├── CallList.vue               # 调用列表
│   └── CallItem.vue           # 单个调用条目
└── EmptyState.vue             # 空状态
```

### 4.2 状态管理

```typescript
interface DetailsDrawerState {
  visible: boolean;
  timestamp: number | null;
  granularity: 'minute' | 'hour';
  data: CallDetailsData | null;
  loading: boolean;
  filters: {
    agent: string | null;
    search: string;
    sort: 'tokens_desc' | 'time_asc';
  };
}
```

### 4.3 与趋势图的联动

```typescript
// PerformanceSection.vue
function handleBarClick(timestamp: number) {
  detailsStore.open({
    timestamp,
    granularity: timeRange.value === '24h' ? 'hour' : 'minute'
  });
}
```

---

## 五、验收标准

### 5.1 功能验收

- [ ] 点击趋势图柱体弹出详情面板
- [ ] 显示时间窗口内的所有调用
- [ ] 显示每个调用的 Agent、Token、时间、触发内容
- [ ] 支持搜索过滤
- [ ] 支持 Agent 筛选
- [ ] 支持排序
- [ ] 空状态正确显示

### 5.2 性能验收

- [ ] 详情加载 < 1s
- [ ] 列表滚动流畅

### 5.3 交互验收

- [ ] 点击外部区域关闭面板
- [ ] ESC 键关闭面板
- [ ] 面板支持滚动

---

## 六、相关文件

| 文件 | 修改类型 |
|------|----------|
| `src/backend/api/performance.py` | 扩展 `get_minute_details()` |
| `frontend/src/components/performance/CallDetailsDrawer.vue` | 新建 |
| `frontend/src/components/performance/PerformanceSection.vue` | 集成抽屉组件 |
| `frontend/src/types/performance.ts` | 添加类型定义 |
