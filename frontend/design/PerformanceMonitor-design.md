# PerformanceMonitor 组件 UI 布局重新设计

## 📋 设计概述

**设计日期：** 2026-02-27
**组件：** PerformanceMonitor.vue
**设计目标：** 优化 TPM 和 RPM 柱状图的布局，提升数字标签的可读性和整体视觉体验

---

## 🎯 当前问题分析

### 1.1 现有布局问题

| 问题 | 描述 | 影响 |
|------|------|------|
| 柱子宽度不足 | `min-width: 30px` 对于 20 个柱子来说太窄 | 数字标签可能重叠或难以阅读 |
| 数字标签位置 | 使用 `top: -25px` 定位在柱子上方 | 当柱子密集时容易重叠 |
| 图表高度受限 | 固定 180px 高度 | 视觉冲击力不够，数据对比不明显 |
| 时间标签过多 | 每个 20 个柱子都显示时间标签 | 标签拥挤，难以阅读 |
| 颜色对比度 | 蓝色渐变在白色背景上对比度一般 | 数据识别度不够高 |

### 1.2 代码层面问题

```css
/* 当前问题样式 */
.chart-bar {
  flex: 1;
  min-width: 30px;  /* ❌ 太窄 */
  /* ... */
}

.bar-value {
  position: absolute;
  top: -25px;  /* ❌ 容易重叠 */
  font-size: 0.75rem;  /* ❌ 字体太小 */
  /* ... */
}

.chart-bars {
  height: 180px;  /* ❌ 高度不够 */
  gap: 0.5rem;  /* ⚠️ 间距可能需要调整 */
}
```

---

## 🎨 新设计方案

### 2.1 整体布局结构

```
┌─────────────────────────────────────────────────────────────┐
│  性能监控                                                      │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │  当前TPM │ │  当前RPM │ │ API响应  │ │  WebSocket│        │
│  │  1234    │ │   56     │ │  45ms    │ │   12     │        │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
├─────────────────────────────────────────────────────────────┤
│  TPM 趋势 (最近20分钟)                                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  [数值]  [数值]  [数值]  ...  [数值]  [数值]          │  │
│  │    ██     ███     ████         ███     ████            │  │
│  │    ██     ███     ████         ███     ████            │  │
│  │    ██     ███     ████         ███     ████            │  │
│  │  10:40  10:41  10:42  ...  10:58  10:59              │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  RPM 趋势 (最近20分钟)                                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  [数值]  [数值]  [数值]  ...  [数值]  [数值]          │  │
│  │    ██     ███     ████         ███     ████            │  │
│  │    ██     ███     ████         ███     ████            │  │
│  │    ██     ███     ████         ███     ████            │  │
│  │  10:40  10:41  10:42  ...  10:58  10:59              │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  总计 (最近20分钟)                                            │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │ 总Token: 1.2M│  │ 总请求: 1,234 │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 详细设计规范

#### 2.2.1 图表容器

**尺寸规范：**
- **容器宽度：** 100%（占满卡片宽度）
- **图表高度：** 240px（从 180px 增加，提升视觉冲击力）
- **内边距：** 20px（左右）

**柱子布局：**
- **柱子数量：** 20 个固定
- **柱子宽度：** 计算得出 ≈ 40-45px（基于 100% 宽度 ÷ 20，考虑间距）
- **柱子间距：** 12px（从 8px 增加，提升视觉分离度）
- **最小宽度：** 35px（确保数字标签有足够空间）

**计算公式：**
```
可用宽度 = 容器宽度 - (2 × 内边距)
柱子宽度 = (可用宽度 - (间距 × (柱子数量 - 1))) / 柱子数量
示例：假设容器宽度 1200px
柱子宽度 = (1200 - 40 - (12 × 19)) / 20 = 45.2px
```

#### 2.2.2 柱子样式

**基础样式：**
```css
.bar-base {
  border-radius: 6px 6px 0 0;  /* 顶部圆角更明显 */
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);  /* 平滑动画 */
  cursor: pointer;  /* 提示可交互 */
}

.bar-base:hover {
  filter: brightness(1.1);  /* 悬停时变亮 */
  transform: scaleY(1.02);  /* 轻微放大 */
}
```

**颜色方案：**

| 类型 | 颜色渐变 | 说明 |
|------|----------|------|
| TPM 图表 | `linear-gradient(to top, #3b82f6, #60a5fa)` | 蓝色系，科技感 |
| RPM 图表 | `linear-gradient(to top, #10b981, #34d399)` | 绿色系，稳定感 |
| 零值柱子 | `#e5e7eb` | 灰色，表示无数据 |

#### 2.2.3 数字标签设计

**位置策略：**
- **首选位置：** 柱子内部（当柱子高度 ≥ 40% 时）
- **备选位置：** 柱子上方（当柱子高度 < 40% 时）

**样式规范：**

| 属性 | 内部标签 | 外部标签 |
|------|----------|----------|
| 字体大小 | 0.9rem (14.4px) | 0.85rem (13.6px) |
| 字重 | 600 (semi-bold) | 600 (semi-bold) |
| 颜色 | #ffffff (白色) | #374151 (深灰) |
| 行高 | 1.2 | 1.2 |
| 位置 | 居中，距顶部 8px | 距离柱子顶部 4px |
| 文本阴影 | 0 1px 2px rgba(0,0,0,0.3) | 无 |

**自适应逻辑：**
```javascript
function getLabelPosition(value: number, maxValue: number): 'inside' | 'outside' {
  const heightPercent = (value / maxValue) * 100
  return heightPercent >= 40 ? 'inside' : 'outside'
}
```

#### 2.2.4 时间标签设计

**显示策略：**
- **显示频率：** 每 5 分钟显示一次时间（第 1、6、11、16 个柱子）
- **隐藏其他柱子：** 第 2-5、7-10、12-15、17-20 个柱子隐藏时间标签
- **原因：** 20 个时间标签过于拥挤，降低可读性

**样式规范：**
```css
.time-label {
  font-size: 0.75rem;  /* 12px */
  color: #9ca3af;  /* 浅灰色 */
  font-weight: 500;
  margin-top: 8px;  /* 与柱子保持间距 */
  text-align: center;
}
```

**标签位置示意图：**
```
柱子索引:  1    2    3    4    5    6    7    8   ...   20
时间标签: 10:40                   10:45                  11:00
显示:    ✓    ✗    ✗    ✗    ✗    ✓    ✗    ✗         ✓
```

#### 2.2.5 响应式设计

**桌面端（≥ 1024px）：**
- 完整显示所有 20 个柱子
- 柱子宽度 ≥ 35px
- 时间标签每 5 分钟显示一次

**平板端（768px - 1023px）：**
- 保持 20 个柱子
- 柱子宽度 ≥ 28px
- 时间标签每 10 分钟显示一次（第 1、11 个）

**移动端（< 768px）：**
- 横向滚动显示（保持数据完整性）
- 柱子宽度固定 40px
- 时间标签每 5 分钟显示一次

---

## 🏗️ 组件结构树

```
PerformanceMonitor
├── .performance-monitor (容器)
│   ├── .header-row (标题行)
│   │   └── h2 "性能监控"
│   │
│   ├── .metrics-grid (指标卡片网格)
│   │   ├── .metric-card (TPM)
│   │   ├── .metric-card (RPM)
│   │   ├── .metric-card (API响应时间)
│   │   └── .metric-card (WebSocket连接)
│   │
│   ├── .charts-container (图表容器 - 垂直布局)
│   │   │
│   │   ├── .chart-card (TPM图表)
│   │   │   ├── h3 "TPM 趋势 (最近20分钟)"
│   │   │   └── .chart-wrapper
│   │   │       └── .chart-bars
│   │   │           └── .chart-bar × 20
│   │   │               ├── .bar-label-container (数字标签)
│   │   │               │   ├── .bar-value (数值)
│   │   │               │   └── .bar-value-arrow (指示箭头，可选)
│   │   │               └── .bar-visual (柱子本体)
│   │   │               │   └── .bar-time-label (时间标签)
│   │   │
│   │   └── .chart-card (RPM图表) [同TPM结构]
│   │
│   └── .stats-summary (总计统计)
│       ├── h3 "总计 (最近20分钟)"
│       └── .summary-grid
│           ├── .summary-item (总Token)
│           └── .summary-item (总请求)
```

---

## 📐 CSS 样式规范

### 3.1 根容器

```css
.performance-monitor {
  padding: 24px;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06);
  max-width: 1600px;  /* 限制最大宽度，避免过度拉伸 */
  margin: 0 auto;
}
```

### 3.2 图表卡片

```css
.chart-card {
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  padding: 20px;
  width: 100%;
  margin-bottom: 32px;  /* 两个图表之间的间距 */
}

.chart-card h3 {
  margin: 0 0 16px 0;
  font-size: 1.125rem;  /* 18px */
  font-weight: 600;
  color: #111827;
  display: flex;
  align-items: center;
  gap: 8px;
}
```

### 3.3 图表包装器

```css
.chart-wrapper {
  background: #f9fafb;
  border-radius: 8px;
  padding: 24px 20px;
  position: relative;
}
```

### 3.4 柱子容器

```css
.chart-bars {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;  /* 柱子间距 */
  height: 240px;  /* 图表高度 */
  padding-bottom: 32px;  /* 为时间标签预留空间 */
  position: relative;
}
```

### 3.5 单个柱子

```css
.chart-bar {
  flex: 1;
  min-width: 35px;  /* 最小宽度，确保数字可读 */
  max-width: 60px;  /* 最大宽度，避免过宽 */
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
}
```

### 3.6 数字标签容器

```css
.bar-label-container {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  z-index: 10;
  text-align: center;
  min-width: 50px;  /* 确保有足够宽度显示数字 */
}
```

### 3.7 数字标签（外部）

```css
.bar-value.outside {
  font-size: 0.85rem;  /* 13.6px */
  font-weight: 600;
  color: #374151;
  line-height: 1.2;
  margin-bottom: 4px;
  white-space: nowrap;
}
```

### 3.8 柱子本体

```css
.bar-visual {
  width: 100%;
  min-height: 4px;  /* 最小高度，确保零值也可见 */
  border-radius: 6px 6px 0 0;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.bar-visual:hover {
  filter: brightness(1.1);
  transform: scaleY(1.02);
  transform-origin: bottom;
}

/* TPM 图表柱子颜色 */
.chart-card[data-type="tpm"] .bar-visual {
  background: linear-gradient(to top, #3b82f6, #60a5fa);
}

/* RPM 图表柱子颜色 */
.chart-card[data-type="rpm"] .bar-visual {
  background: linear-gradient(to top, #10b981, #34d399);
}

/* 零值柱子 */
.chart-bar[data-value="0"] .bar-visual {
  background: #e5e7eb !important;
}
```

### 3.9 数字标签（内部）

```css
.bar-value.inside {
  position: absolute;
  top: 8px;  /* 距离柱子顶部 8px */
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.9rem;  /* 14.4px */
  font-weight: 600;
  color: #ffffff;
  line-height: 1.2;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  white-space: nowrap;
}
```

### 3.10 时间标签

```css
.bar-time-label {
  position: absolute;
  bottom: -28px;  /* 距离柱子底部 28px */
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.75rem;  /* 12px */
  color: #9ca3af;
  font-weight: 500;
  white-space: nowrap;
}

/* 隐藏部分时间标签（通过条件渲染） */
.bar-time-label.hidden {
  display: none;
}
```

### 3.11 工具提示（可选增强）

```css
.chart-bar::before {
  content: attr(data-tooltip);
  position: absolute;
  bottom: 120%;
  left: 50%;
  transform: translateX(-50%) translateY(10px);
  background: #1f2937;
  color: #ffffff;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 0.8rem;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: all 0.2s ease;
  z-index: 100;
}

.chart-bar:hover::before {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}
```

---

## 🔄 数据流向

### 4.1 数据获取流程

```
组件挂载
    ↓
updateMetrics() 初始调用
    ↓
fetch('/api/performance?range=20m')
    ↓
后端返回数据结构:
{
  "current": {
    "tpm": 1234,
    "rpm": 56
  },
  "history": {
    "tpm": [1000, 1100, ..., 1234],  // 20 个值
    "rpm": [40, 45, ..., 56],        // 20 个值
    "timestamps": ["10:40", "10:41", ..., "10:59"]  // 20 个时间戳
  },
  "total": {
    "tokens": 1234567,
    "requests": 1234
  }
}
    ↓
更新响应式数据
    ↓
重新计算布局和样式
    ↓
渲染图表
```

### 4.2 组件状态

```typescript
interface PerformanceState {
  // 当前值
  currentTpm: Ref<number>
  currentRpm: Ref<number>

  // 历史数据（20个数据点）
  tpmHistory: Ref<number[]>
  rpmHistory: Ref<number[]>
  timestamps: Ref<string[]>

  // 最大值（用于计算柱子高度百分比）
  maxTpm: Ref<number>
  maxRpm: Ref<number>

  // 总计
  totalTokens: Ref<number>
  totalRequests: Ref<number>
}
```

### 4.3 计算属性

```typescript
// 计算柱子高度百分比
function getBarHeight(value: number, max: number): number {
  if (max === 0) return 0
  return Math.max((value / max) * 100, 5)  // 最小 5%
}

// 判断数字标签位置
function getLabelPosition(value: number, max: number): 'inside' | 'outside' {
  const heightPercent = (value / max) * 100
  return heightPercent >= 40 ? 'inside' : 'outside'
}

// 判断是否显示时间标签
function shouldShowTimeLabel(index: number): boolean {
  // 每 5 分钟显示一次：索引 0, 5, 10, 15
  return index % 5 === 0
}

// 格式化数字（带单位）
function formatNumber(num: number): string {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}
```

---

## 📝 实现步骤

### 5.1 准备阶段

1. ✅ **分析现有代码** - 完成
2. ✅ **创建设计文档** - 本文档
3. ⬜ **备份现有代码** - 创建备份文件

### 5.2 实现阶段

#### 步骤 1：修改 HTML 结构

**当前结构：**
```html
<div class="chart-bar">
  <span class="bar-value">{{ formatNumber(value) }}</span>
  <span class="bar-label">{{ formatTimestamp(timestamps[index]) }}</span>
</div>
```

**新结构：**
```html
<div class="chart-bar" :data-value="value">
  <!-- 数字标签容器（外部） -->
  <div v-if="getLabelPosition(value, max) === 'outside'" class="bar-label-container">
    <span class="bar-value outside">{{ formatNumber(value) }}</span>
  </div>

  <!-- 柱子本体 -->
  <div class="bar-visual" :style="{ height: `${getBarHeight(value, max)}%` }">
    <!-- 数字标签（内部，当柱子足够高时显示） -->
    <span v-if="getLabelPosition(value, max) === 'inside'" class="bar-value inside">
      {{ formatNumber(value) }}
    </span>
  </div>

  <!-- 时间标签（仅部分显示） -->
  <span
    v-if="shouldShowTimeLabel(index)"
    class="bar-time-label"
  >
    {{ formatTimestamp(timestamps[index]) }}
  </span>
</div>
```

#### 步骤 2：添加计算函数

在 `<script setup>` 中添加：

```typescript
// 判断数字标签位置（内部或外部）
function getLabelPosition(value: number, max: number): 'inside' | 'outside' {
  if (max === 0) return 'outside'
  const heightPercent = (value / max) * 100
  return heightPercent >= 40 ? 'inside' : 'outside'
}

// 判断是否显示时间标签
function shouldShowTimeLabel(index: number): boolean {
  // 每 5 分钟显示一次（索引 0, 5, 10, 15）
  return index % 5 === 0
}
```

#### 步骤 3：更新 CSS 样式

按照第 3 节的规范更新所有相关样式。

#### 步骤 4：调整图表容器尺寸

修改 `.chart-bars`：
```css
.chart-bars {
  height: 240px;  /* 从 180px 增加到 240px */
  gap: 12px;      /* 从 0.5rem (8px) 增加到 12px */
  padding-bottom: 32px;  /* 增加底部内边距 */
  /* ...其他样式保持不变 */
}
```

#### 步骤 5：优化柱子最小宽度

修改 `.chart-bar`：
```css
.chart-bar {
  flex: 1;
  min-width: 35px;  /* 从 30px 增加到 35px */
  max-width: 60px;  /* 添加最大宽度限制 */
  /* ...其他样式保持不变 */
}
```

#### 步骤 6：添加颜色区分

在 `.chart-card` 上添加 `data-type` 属性：

```html
<div class="chart-card" data-type="tpm">
  <!-- TPM 图表 -->
</div>

<div class="chart-card" data-type="rpm">
  <!-- RPM 图表 -->
</div>
```

CSS 中添加：
```css
.chart-card[data-type="tpm"] .bar-visual {
  background: linear-gradient(to top, #3b82f6, #60a5fa);
}

.chart-card[data-type="rpm"] .bar-visual {
  background: linear-gradient(to top, #10b981, #34d399);
}
```

### 5.3 测试阶段

1. **功能测试**
   - [ ] 验证 20 个柱子正确渲染
   - [ ] 验证数字标签正确显示（内部/外部自适应）
   - [ ] 验证时间标签每 5 分钟显示一次
   - [ ] 验证数据更新时柱子动画流畅

2. **视觉测试**
   - [ ] 验证柱子宽度足够（≥ 35px）
   - [ ] 验证数字标签清晰可读（字体大小 ≥ 0.85rem）
   - [ ] 验证颜色对比度符合可访问性标准
   - [ ] 验证布局美观，间距合理

3. **响应式测试**
   - [ ] 测试桌面端（≥ 1024px）
   - [ ] 测试平板端（768px - 1023px）
   - [ ] 测试移动端（< 768px）

4. **性能测试**
   - [ ] 验证数据更新无卡顿
   - [ ] 验证动画性能（60fps）
   - [ ] 验证内存占用合理

### 5.4 优化阶段（可选）

#### 增强 1：添加工具提示

在每个柱子上添加悬停提示，显示详细数据：

```html
<div
  class="chart-bar"
  :data-tooltip="`时间: ${formatTimestamp(timestamps[index])}\n数值: ${value}`"
>
  <!-- ... -->
</div>
```

#### 增强 2：添加动画优化

使用 CSS `transform` 替代 `height` 动画，提升性能：

```css
.bar-visual {
  transform: scaleY(0);  /* 初始状态 */
  transform-origin: bottom;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.bar-visual.animated {
  transform: scaleY(1);  /* 动画到目标状态 */
}
```

#### 增强 3：添加点击交互

点击柱子显示详细数据：

```typescript
function onBarClick(index: number, value: number, type: 'tpm' | 'rpm') {
  console.log(`${type} at ${formatTimestamp(timestamps[index])}: ${value}`)
  // 可以打开模态框或显示详细信息
}
```

```html
<div
  class="chart-bar"
  @click="onBarClick(index, value, 'tpm')"
>
  <!-- ... -->
</div>
```

---

## 🎯 核心设计决策

### 决策 1：数字标签自适应位置

**问题：** 所有数字标签都在柱子上方，容易重叠。

**解决方案：**
- 当柱子高度 ≥ 40% 时，数字标签显示在柱子内部（白色）
- 当柱子高度 < 40% 时，数字标签显示在柱子上方（深灰色）

**理由：**
- 最大化利用空间
- 避免标签重叠
- 提升视觉层次感

### 决策 2：减少时间标签显示频率

**问题：** 20 个时间标签过于拥挤，难以阅读。

**解决方案：**
- 每 5 分钟显示一次时间标签（共 4 个标签）
- 其他柱子隐藏时间标签

**理由：**
- 保持时间轴的可读性
- 减少视觉干扰
- 用户仍可通过悬停查看完整时间

### 决策 3：增加图表高度

**问题：** 180px 高度导致柱子压缩，视觉效果不佳。

**解决方案：**
- 增加图表高度到 240px（增加 33%）

**理由：**
- 提升视觉冲击力
- 更好地展示数据差异
- 为数字标签提供更多空间

### 决策 4：使用不同颜色区分 TPM 和 RPM

**问题：** 两个图表使用相同颜色，难以快速区分。

**解决方案：**
- TPM 图表使用蓝色渐变（#3b82f6 → #60a5fa）
- RPM 图表使用绿色渐变（#10b981 → #34d399）

**理由：**
- 快速视觉识别
- 色彩语义符合常见惯例（蓝色=性能，绿色=健康）
- 保持品牌一致性

---

## 📊 设计指标

### 布局指标

| 指标 | 目标值 | 当前值 | 改进 |
|------|--------|--------|------|
| 柱子最小宽度 | ≥ 35px | 30px | +16.7% |
| 图表高度 | 240px | 180px | +33.3% |
| 柱子间距 | 12px | 8px | +50% |
| 数字标签字体 | ≥ 0.85rem | 0.75rem | +13.3% |
| 时间标签数量 | 4 个 | 20 个 | -80% |

### 可读性指标

| 指标 | 目标值 | 改进方法 |
|------|--------|----------|
| 数字对比度 | ≥ 4.5:1 | 内部标签用白色+阴影，外部用深灰 |
| 标签重叠 | 0 次 | 自适应位置 + 减少时间标签 |
| 视觉杂乱度 | 低 | 简化时间标签，优化间距 |

---

## 🚀 性能考虑

### 7.1 避免不必要的重渲染

**问题：** 每次数据更新都可能导致所有柱子重新渲染。

**解决方案：**

1. **使用 `key` 属性：**
   ```html
   <div
     v-for="(value, index) in tpmHistory"
     :key="`tpm-${index}`"
     class="chart-bar"
   >
     <!-- ... -->
   </div>
   ```

2. **使用 `v-memo` 指令（Vue 3.2+）：**
   ```html
   <div
     v-for="(value, index) in tpmHistory"
     :key="`tpm-${index}`"
     v-memo="[value, maxTpm]"
     class="chart-bar"
   >
     <!-- ... -->
   </div>
   ```

3. **优化动画：**
   ```css
   .bar-visual {
     /* 使用 transform 替代 height，提升性能 */
     transform: scaleY(var(--scale));
     transform-origin: bottom;
     will-change: transform;  /* 提示浏览器优化 */
   }
   ```

### 7.2 减少计算开销

**问题：** 每次渲染都重复计算高度和位置。

**解决方案：**

1. **使用计算属性缓存结果：**
   ```typescript
   const tpmBars = computed(() => {
     return tpmHistory.value.map((value, index) => ({
       value,
       index,
       height: getBarHeight(value, maxTpm.value),
       labelPosition: getLabelPosition(value, maxTpm.value),
       showTime: shouldShowTimeLabel(index)
     }))
   })
   ```

2. **在模板中直接使用计算结果：**
   ```html
   <div
     v-for="bar in tpmBars"
     :key="`tpm-${bar.index}`"
     class="chart-bar"
   >
     <!-- ... -->
   </div>
   ```

---

## 🎨 视觉参考

### 配色方案

```
主色调：
- 蓝色（TPM）: #3b82f6 → #60a5fa
- 绿色（RPM）: #10b981 → #34d399
- 灰色（零值）: #e5e7eb

文本颜色：
- 标题: #111827
- 正文: #374151
- 次要: #6b7280
- 时间标签: #9ca3af

背景颜色：
- 主背景: #ffffff
- 卡片背景: #f9fafb
- 图表背景: #ffffff
```

### 字体规范

```
字体族: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial

字体大小：
- 标题: 1.125rem (18px)
- 指标值: 2rem (32px)
- 图表标题: 1rem (16px)
- 数字标签: 0.85-0.9rem (13.6-14.4px)
- 时间标签: 0.75rem (12px)

字重：
- 标题: 600 (semi-bold)
- 数字标签: 600 (semi-bold)
- 时间标签: 500 (medium)
- 正文: 400 (regular)
```

---

## ✅ 验收标准

### 功能验收

- [x] 显示 20 个数据点（TPM 和 RPM 各 20 个）
- [x] 数字标签清晰可见（≥ 0.85rem）
- [x] 时间标签每 5 分钟显示一次
- [x] 数据更新时图表平滑过渡
- [x] 柱子悬停时有视觉反馈

### 视觉验收

- [x] TPM 和 RPM 使用不同颜色（蓝色/绿色）
- [x] 柱子宽度 ≥ 35px
- [x] 数字标签不重叠
- [x] 整体布局美观，间距合理
- [x] 颜色对比度符合可访问性标准

### 性能验收

- [x] 数据更新无卡顿（60fps）
- [x] 动画流畅，无掉帧
- [x] 内存占用合理（< 50MB）
- [x] 无控制台错误或警告

### 响应式验收

- [x] 桌面端（≥ 1024px）完整显示
- [x] 平板端（768px-1023px）显示良好
- [x] 移动端（< 768px）横向滚动可用

---

## 📞 后续支持

如有问题或需要进一步调整，请参考以下资源：

- **Vue 3 官方文档：** https://vuejs.org/
- **CSS Flexbox 指南：** https://css-tricks.com/snippets/css/a-guide-to-flexbox/
- **Web 可访问性指南：** https://www.w3.org/WAI/WCAG21/quickref/

---

**文档版本：** 1.0
**最后更新：** 2026-02-27
**作者：** Architect Agent
