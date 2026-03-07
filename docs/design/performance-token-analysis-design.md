# Token 分析模块详细设计

> 文档版本：1.0
> 创建日期：2026-03-07
> 模块类型：成本分析核心模块

---

## 一、需求概述

### 1.1 功能目标

提供多维度的 Token 消耗分析，帮助用户：
- 了解各 Agent 的 Token 消耗分布
- 评估 Prompt 缓存效果（cacheRead/cacheWrite）
- 估算 API 成本
- 优化资源使用

### 1.2 用户场景

| 角色 | 场景 | 目标 |
|------|------|------|
| 成本管理者 | 月度成本核算 | 了解各 Agent 的 Token 消耗占比 |
| 开发者 | 优化 Prompt | 评估缓存命中率，优化缓存策略 |
| 架构师 | 容量规划 | 分析历史消耗趋势，预测未来需求 |

---

## 二、功能设计

### 2.1 时间范围选择

与 TPM/RPM 模块保持一致：

| 选项 | 数据粒度 | 适用场景 |
|------|----------|----------|
| **20分钟** | 实时数据 | 实时监控 |
| **1小时** | 分钟级 | 短期分析 |
| **24小时** | 小时级 | 日常分析 |

**额外选项（Token 分析专用）：**

| 选项 | 说明 |
|------|------|
| **全部** | 所有历史数据（用于成本核算） |

### 2.2 总览卡片

显示 Token 消耗的总体情况：

```
┌──────────────────────────────────────────────────────────────┐
│                      Token 消耗总览                           │
├────────────┬────────────┬────────────┬────────────┬─────────┤
│  Input     │  Output    │  Cache Read│  Cache Write│  成本    │
│  58,609    │  20,084    │  190,932   │  12,345    │  $2.35  │
│  ↓ 5%      │  ↑ 12%     │  ↑ 45%     │  ↓ 8%      │  ↑ 3%   │
│  输入Token  │  输出Token  │  缓存读取   │  缓存写入   │  估算成本 │
└────────────┴────────────┴────────────┴────────────┴─────────┘
```

**指标说明：**

| 指标 | 含义 | 单位换算 |
|------|------|----------|
| Input | 输入 Token 数 | 千 / 百万 |
| Output | 输出 Token 数 | 千 / 百万 |
| Cache Read | 从缓存读取的 Token（节省的输入） | 千 / 百万 |
| Cache Write | 写入缓存的 Token | 千 / 百万 |
| 成本 | 估算 API 成本 | 美元 |

**缓存命中率计算：**

```
缓存命中率 = Cache Read / (Input + Cache Read) × 100%
```

### 2.3 Agent 分布

#### 2.3.1 表格视图

```
┌─────────────────────────────────────────────────────────────────────────┐
│  按 Agent 分布                                          [表格] [图表]    │
├────────────────┬─────────┬─────────┬───────────┬───────────┬───────────┤
│  Agent         │  Input  │  Output │  Cache    │  总计     │  占比     │
├────────────────┼─────────┼─────────┼───────────┼───────────┼───────────┤
│  analyst-agent │  29,034 │  17,454 │  167,052  │  213,540  │  68.5%    │
│  main          │  21,388 │   1,079 │   29,220  │   51,687  │  16.6%    │
│  devops-agent  │   8,187 │   1,551 │   14,660  │   24,398  │   7.8%    │
│  ...           │   ...   │   ...   │   ...     │   ...     │   ...     │
├────────────────┴─────────┴─────────┴───────────┴───────────┴───────────┤
│  合计           │  58,609 │  20,084 │  190,932  │  311,820  │  100%     │
└─────────────────────────────────────────────────────────────────────────┘
```

**列说明：**

| 列 | 计算方式 | 排序 |
|------|----------|------|
| Agent | Agent 名称 | - |
| Input | 该 Agent 的 input tokens | 可排序 |
| Output | 该 Agent 的 output tokens | 可排序 |
| Cache | Cache Read + Cache Write | 可排序 |
| 总计 | Input + Output | 可排序（默认降序） |
| 占比 | 该 Agent 总计 / 全部总计 | - |

#### 2.3.2 图表视图

**饼图 / 环形图：**

```
              Token 消耗分布
                  ┌───┐
              ╱───│   │───╲
            ╱     │68%│    ╲
           │      └───┘      │
           │   analyst-agent │
           │                 │
           │  ┌───┐          │
            ╲ │17%│ main    ╱
              └───┘
                 ╲
                  ╲───┐
                      │
                      │
                  ────┘
```

**条形图（水平）：**

```
Token 消耗 (按 Agent)

analyst-agent ████████████████████████████████ 68.5%
main          █████████ 16.6%
devops-agent  ████ 7.8%
test-agent    ██ 5.1%
other         █ 2.0%
```

### 2.4 趋势分析（24h 模式）

在 24h 时间范围下，显示 Token 消耗趋势：

```
Token 消耗趋势 (24h)
│
│     Input
│     ▓▓▓▓▓
│  ▓▓▓▓▓▓▓▓▓▓▓     Output
│  ▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░
│──▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░──▓▓▓▓▓▓▓──
│
└──────────────────────────────────→ 时间
  00:00   06:00   12:00   18:00   24:00
```

### 2.5 成本估算

#### 2.5.1 模型定价配置

支持配置不同模型的定价：

```typescript
interface ModelPricing {
  model: string;
  inputPrice: number;    // 每 1M Token 价格（美元）
  outputPrice: number;   // 每 1M Token 价格（美元）
  cacheReadPrice: number;  // 每 1M Token 价格（美元）
  cacheWritePrice: number; // 每 1M Token 价格（美元）
}

// 默认配置（Claude 3.5 Sonnet）
const DEFAULT_PRICING: ModelPricing = {
  model: 'claude-3-5-sonnet',
  inputPrice: 3.00,
  outputPrice: 15.00,
  cacheReadPrice: 0.30,
  cacheWritePrice: 3.75
};
```

#### 2.5.2 成本计算

```typescript
function calculateCost(usage: TokenUsage, pricing: ModelPricing): number {
  const inputCost = (usage.input / 1_000_000) * pricing.inputPrice;
  const outputCost = (usage.output / 1_000_000) * pricing.outputPrice;
  const cacheReadCost = (usage.cacheRead / 1_000_000) * pricing.cacheReadPrice;
  const cacheWriteCost = (usage.cacheWrite / 1_000_000) * pricing.cacheWritePrice;

  return inputCost + outputCost + cacheReadCost + cacheWriteCost;
}
```

#### 2.5.3 节省金额

显示通过缓存节省的金额：

```
缓存节省: $5.23 (节省 68% 输入成本)
```

---

## 三、后端设计

### 3.1 API 接口

**GET /api/tokens/analysis**

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `range` | string | 否 | 时间范围：`20m`、`1h`、`24h`、`all`，默认 `all` |
| `model` | string | 否 | 指定模型计算成本 |

**响应结构：**

```json
{
  "summary": {
    "input": 58609,
    "output": 20084,
    "cacheRead": 190932,
    "cacheWrite": 12345,
    "total": 311820,
    "cacheHitRate": 0.765
  },
  "cost": {
    "input": 0.18,
    "output": 0.30,
    "cacheRead": 0.06,
    "cacheWrite": 0.05,
    "total": 0.59,
    "saved": 0.54,
    "savedPercent": 0.48
  },
  "byAgent": [
    {
      "agent": "analyst-agent",
      "input": 29034,
      "output": 17454,
      "cacheRead": 167052,
      "cacheWrite": 8000,
      "total": 221540,
      "percent": 0.685,
      "cost": 0.40
    }
  ],
  "trend": {
    "timestamps": ["00:00", "01:00", ...],
    "input": [1000, 2000, ...],
    "output": [500, 800, ...]
  }
}
```

### 3.2 数据来源

#### 3.2.1 当前实现（sessions.json）

```python
# 从 sessions.json 读取
# 位置: ~/.openclaw/agents/*/sessions.json
```

#### 3.2.2 扩展支持（sessions/*.jsonl）

为支持时间范围筛选，需要从 jsonl 文件实时计算：

```python
def get_tokens_analysis(range: str = 'all') -> dict:
    """
    获取 Token 分析数据

    Args:
        range: 时间范围
    """
    if range == 'all':
        # 从 sessions.json 读取（快速）
        return read_from_sessions_json()
    else:
        # 从 sessions/*.jsonl 计算（支持时间筛选）
        return calculate_from_jsonl(range)
```

### 3.3 Agent 名称获取

**消除硬编码：**

```python
def get_agent_names() -> list[str]:
    """
    动态获取所有 Agent 名称

    从 ~/.openclaw/ 目录扫描
    """
    openclaw_home = os.environ.get('OPENCLAW_HOME', '~/.openclaw')
    agents_dir = Path(openclaw_home).expanduser()

    return [d.name for d in agents_dir.iterdir()
            if d.is_dir() and (d / 'sessions').exists()]
```

---

## 四、前端设计

### 4.1 组件结构

```
TokenAnalysisPanel.vue (重构)
├── TimeRangeSelector.vue       # 时间范围选择（复用）
├── TokenSummaryCards.vue       # 总览卡片（新建）
├── AgentDistribution.vue       # Agent 分布（重构）
│   ├── TableView.vue           # 表格视图
│   └── ChartView.vue           # 图表视图
├── CostEstimation.vue          # 成本估算（新建）
└── TrendChart.vue              # 趋势图（24h 模式）
```

### 4.2 视图切换

```
┌─────────────────────────────────────────┐
│  [📊 表格]  [📈 图表]                    │
├─────────────────────────────────────────┤
│                                         │
│            当前视图内容                   │
│                                         │
└─────────────────────────────────────────┘
```

### 4.3 与 PerformanceSection 整合

**方案：Tab 切换**

```
┌─────────────────────────────────────────┐
│  [TPM/RPM]  [Token 分析]                │
├─────────────────────────────────────────┤
│                                         │
│   共享时间范围选择器                      │
│   各自独立的内容区域                      │
│                                         │
└─────────────────────────────────────────┘
```

---

## 五、验收标准

### 5.1 功能验收

- [ ] 显示 Input/Output/Cache Token 总览
- [ ] 显示缓存命中率
- [ ] 按 Agent 分组统计
- [ ] 支持表格和图表视图切换
- [ ] 支持成本估算
- [ ] 显示缓存节省金额
- [ ] 支持时间范围筛选
- [ ] 24h 模式显示趋势

### 5.2 数据验收

- [ ] Agent 名称动态获取，无硬编码
- [ ] 数据与后端 API 一致
- [ ] 成本计算准确

### 5.3 性能验收

- [ ] `all` 模式加载 < 1s（使用 sessions.json）
- [ ] 时间范围模式加载 < 2s

---

## 六、相关文件

| 文件 | 修改类型 |
|------|----------|
| `src/backend/api/performance.py` | 扩展 `get_tokens_analysis()` |
| `frontend/src/components/TokenAnalysisPanel.vue` | 重构 |
| `frontend/src/components/performance/PerformanceSection.vue` | 整合 Tab |
| `frontend/src/types/performance.ts` | 更新类型 |
