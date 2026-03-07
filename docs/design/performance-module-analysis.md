# 性能数据模块深度分析

> 文档版本：1.0  
> 创建日期：2026-03-07  
> 分析范围：性能监控、Token 分析、调用详情

---

## 一、模块定位与价值

### 1.1 核心功能

| 功能 | API | 描述 |
|------|-----|------|
| TPM/RPM 监控 | `/api/performance` | 每分钟 Token/请求统计，20分钟历史趋势 |
| 调用详情钻取 | `/api/performance/details` | 点击柱状图查看某分钟的调用明细 |
| Token 分析 | `/api/tokens/analysis` | 按 Agent/Session 汇总 Token 消耗 |

### 1.2 使用场景

| 场景 | 价值 |
|------|------|
| **成本监控** | 了解各 Agent 的 Token 消耗，优化 API 成本 |
| **性能调优** | 识别高 TPM 时段，分析调用瓶颈 |
| **问题排查** | 通过调用详情追溯具体操作 |
| **容量规划** | 基于 RPM/TPM 历史数据预估负载 |

### 1.3 与协作流程的区别

| 维度 | 协作流程 | 性能数据 |
|------|----------|----------|
| 关注点 | Agent 间的任务流转 | API 调用量与成本 |
| 时间粒度 | 实时状态 | 分钟级聚合 |
| 数据来源 | runs.json + sessions | sessions.jsonl (usage 字段) |
| 目标用户 | 开发者/架构师 | 运维/成本管理者 |

---

## 二、后端实现分析

### 2.1 数据流

```
~/.openclaw/agents/*/sessions/*.jsonl
    ↓ parse_session_file()
    ↓ 提取 usage.totalTokens, timestamp
    ↓ 按分钟聚合
    ↓
API Response: { current, history, total }
```

### 2.2 关键函数

| 函数 | 文件 | 作用 |
|------|------|------|
| `parse_session_file()` | `api/performance.py:168` | 解析单个 session，提取有 usage 的消息 |
| `parse_session_file_with_details()` | `api/performance.py:95` | 解析 session，带触发内容详情 |
| `get_real_stats()` | `api/performance.py:228` | 聚合统计 TPM/RPM |
| `get_minute_details()` | `api/performance.py:340` | 获取某分钟的调用详情 |
| `get_tokens_analysis()` | `api/performance.py:420` | 从 sessions.json 汇总 Token |

### 2.3 实现质量评估

#### ✅ 优点

1. **真实数据来源**：直接解析 session 文件，非模拟数据
2. **时区处理**：使用 `Asia/Shanghai` 展示，后端 UTC 存储
3. **详情钻取**：支持点击柱状图查看调用详情，含触发内容
4. **缓存统计**：Token 分析包含 `cacheRead/cacheWrite`，便于评估缓存效果

#### ⚠️ 问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **时间范围限制** | `parse_session_file:188-190` | 只统计最近1小时，但 API 支持 20m/1h |
| **错误率始终为0** | `get_real_stats:239` | `errorRate` 未实现，始终返回 0 |
| **延迟含义错误** | `get_performance_stats:224` | `latency` 是 API 处理时间，非 LLM 响应时间 |
| **缺少 OPENCLAW_HOME** | `get_real_stats:253` | 硬编码 `~/.openclaw`，未使用环境变量 |

### 2.4 代码示例（问题）

```python
# src/backend/api/performance.py:188-196
# 只统计最近1小时的消息，但 API 支持 range=1h
now = datetime.now(timezone.utc)
one_hour_ago = now - timedelta(hours=1)

if timestamp >= one_hour_ago:  # ❌ 限制了数据范围
    messages.append({...})
```

---

## 三、前端实现分析

### 3.1 组件结构

| 组件 | 文件 | 功能 |
|------|------|------|
| `PerformanceSection.vue` | `components/performance/` | 主面板：指标卡片 + 趋势图 + 摘要 |
| `TokenAnalysisPanel.vue` | `components/` | Token 分析面板（独立组件） |

### 3.2 UI 功能

#### PerformanceSection.vue

1. **指标卡片**
   - TPM (Tokens/分钟)
   - RPM (Requests/分钟)
   - 延迟 (毫秒)
   - 错误率

2. **趋势图**
   - TPM 柱状图（蓝色）
   - RPM 柱状图（绿色）
   - 点击柱体 → 弹出调用详情

3. **统计摘要**
   - 平均 TPM、最大 TPM
   - 平均延迟、最大延迟
   - 总 Token、总请求

4. **告警面板**
   - TPM > 100000 告警
   - 延迟 > 5000ms 告警

#### TokenAnalysisPanel.vue

- 总 Input/Output Token
- Cache Read/Write
- 按 Agent 分组统计

### 3.3 实现问题

| 问题 | 位置 | 影响 |
|------|------|------|
| **Agent 名称硬编码** | `TokenAnalysisPanel.vue:58-66` | 与任务状态模块相同问题 |
| **时间范围选择器只有一个选项** | `PerformanceSection.vue:243-245` | 只有 20分钟，1h 被移除 |
| **延迟无意义** | 指标卡片 | 显示的是 API 处理时间 (~100ms)，非 LLM 响应时间 |
| **错误率无意义** | 指标卡片 | 后端未实现，始终为 0% |

---

## 四、功能完整性检查

### 4.1 API 测试结果

```bash
# TPM/RPM API
$ curl /api/performance?range=20m
{
  "current": { "tpm": 0, "rpm": 0, "latency": 89, "errorRate": 0.0 },
  "history": { "tpm": [0,0,...], "rpm": [0,0,...], "timestamps": [...] },
  "total": { "tokens": 0, "requests": 0 }
}

# Token 分析 API
$ curl /api/tokens/analysis
{
  "byAgent": {
    "devops-agent": { "input": 8187, "output": 1551, "cacheRead": 14660 },
    "main": { "input": 21388, "output": 1079, "cacheRead": 9220 },
    "analyst-agent": { "input": 29034, "output": 17454, "cacheRead": 167052 }
  },
  "total": { "input": 58609, "output": 20084, "cacheRead": 190932 }
}

# 调用详情 API
$ curl /api/performance/details?timestamp=1741358400000
{ "minute": "2026-03-07 13:08", "calls": [], "totalCalls": 0, "totalTokens": 0 }
```

### 4.2 功能状态

| 功能 | 状态 | 说明 |
|------|------|------|
| TPM/RPM 统计 | ⚠️ 部分可用 | 只统计最近1小时内的数据 |
| 趋势图 | ✅ 正常 | 20分钟柱状图展示 |
| 调用详情钻取 | ✅ 正常 | 点击柱体可查看详情 |
| Token 分析 | ✅ 正常 | 按 Agent/Session 汇总 |
| 延迟监控 | ❌ 无效 | 显示 API 处理时间，非 LLM 延迟 |
| 错误率监控 | ❌ 未实现 | 始终为 0 |
| 告警功能 | ⚠️ 逻辑存在 | 但基于无效的延迟/错误率数据 |

---

## 五、与协作流程的协同

### 5.1 数据共享

| 数据源 | 协作流程使用 | 性能数据使用 |
|--------|--------------|--------------|
| `runs.json` | ✅ 任务状态、Agent 关系 | ❌ 不使用 |
| `sessions/*.jsonl` | ✅ 提取 output、files | ✅ 提取 usage |
| `sessions.json` | ❌ 不使用 | ✅ Token 汇总 |

### 5.2 功能互补

| 需求 | 协作流程 | 性能数据 |
|------|----------|----------|
| 查看任务执行状态 | ✅ 主入口 | ❌ |
| 分析 Token 消耗 | ❌ | ✅ 主入口 |
| 追溯某时刻的操作 | ⚠️ 需点击任务 | ✅ 直接钻取 |
| 评估缓存效果 | ❌ | ✅ cacheRead/cacheWrite |

---

## 六、优化建议

### 6.1 P0 - 修复无效指标

| 任务 | 描述 |
|------|------|
| **移除/重定义延迟** | 当前"延迟"是 API 处理时间(~100ms)，无实际意义。建议：移除或改为从 session 提取 LLM 响应时间 |
| **移除错误率** | 后端未实现，始终为 0。建议：移除或从 runs.json 提取失败率 |

### 6.2 P1 - 数据范围修复

| 任务 | 描述 |
|------|------|
| **修复时间范围** | `parse_session_file()` 限制为1小时，应支持 `range` 参数 |
| **支持 OPENCLAW_HOME** | 使用环境变量替代硬编码路径 |
| **扩展时间范围** | 前端恢复 1h 选项 |

### 6.3 P2 - UI 优化

| 任务 | 描述 |
|------|------|
| **消除 Agent 名称硬编码** | 从配置获取名称 |
| **整合 Token 分析** | 将 TokenAnalysisPanel 合并到 PerformanceSection |
| **添加成本估算** | 基于模型单价计算 API 成本 |

---

## 七、是否需要保留

### 7.1 保留价值评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **独特价值** | ⭐⭐⭐⭐ | Token 消耗分析是其他模块不具备的 |
| **实现质量** | ⭐⭐⭐ | 核心功能可用，但延迟/错误率无效 |
| **用户需求** | ⭐⭐⭐⭐ | 成本监控是生产环境刚需 |
| **维护成本** | ⭐⭐⭐⭐ | 代码清晰，依赖简单 |

### 7.2 结论

**建议保留并优化**，原因：

1. **成本监控刚需**：Token 消耗是 AI 应用的核心成本指标
2. **调用详情价值**：钻取功能有助于问题排查
3. **缓存统计**：帮助评估 Prompt 缓存效果
4. **与协作流程互补**：各自关注不同维度

### 7.3 建议优化优先级

```
P0 (立即修复):
  ├── 移除/隐藏无效的"延迟"指标
  └── 移除/隐藏无效的"错误率"指标

P1 (短期优化):
  ├── 修复时间范围限制
  └── 消除 Agent 名称硬编码

P2 (长期增强):
  ├── 添加 API 成本估算
  ├── 整合 Token 分析到主面板
  └── 支持更多时间范围 (6h, 24h)
```

---

## 八、附录

### 8.1 相关文件清单

```
后端:
├── src/backend/api/performance.py    # 性能 API (478 行)
└── src/backend/performance.py        # (空文件，可删除)

前端:
├── frontend/src/components/performance/PerformanceSection.vue  # 主面板 (1063 行)
├── frontend/src/components/TokenAnalysisPanel.vue              # Token 分析 (165 行)
└── frontend/src/types/performance.ts                           # 类型定义 (38 行)

文档:
└── docs/design/dashboard_interaction_visualization_design.md   # 交互设计
```

### 8.2 API 端点

| 方法 | 路径 | 参数 |
|------|------|------|
| GET | `/api/performance` | `range=20m|1h` |
| GET | `/api/performance/details` | `timestamp=毫秒` |
| GET | `/api/tokens/analysis` | - |
