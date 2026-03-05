# TR3: 协作流程界面 UI 优化

## 状态: ✅ 已完成

## 背景

基于前端分析报告 (`docs/analysis/collaboration-flow-ui-analysis.md`)，协作流程界面存在以下问题：
1. 主 Agent 卡片大小不协调
2. 详情弹窗窄，功能拥挤
3. 布局空间利用不合理

## 需求详情

### REQ-1: 优化主 Agent 卡片比例

**问题**：
- 主 Agent 卡片宽度 320px，子 Agent 最小 180px，差异 1.78 倍
- 主 Agent 区域预留 280px 高度，空间浪费

**解决方案**：
1. 主 Agent 卡片宽度调整为 260px
2. 子 Agent 卡片最小宽度调整为 200px
3. 移除主 Agent 区域固定的 min-height: 280px
4. 统一卡片内边距和字体大小比例

**修改文件**：
- `frontend/src/components/collaboration/CollaborationFlowSection.vue`
- `frontend/src/components/AgentCard.vue`

**具体修改**：

```css
/* CollaborationFlowSection.vue */
/* 修改前 */
.level-section:first-child .agent-card-wrapper.main-agent {
  width: 320px;
}

.level-section:first-child .level-cards {
  min-height: 280px;
  padding-bottom: 1.5rem;
}

.level-section:not(:first-child) .level-cards {
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

/* 修改后 */
.level-section:first-child .agent-card-wrapper.main-agent {
  width: 260px;
  max-width: 100%;
}

.level-section:first-child .level-cards {
  min-height: auto;
  padding-bottom: 1rem;
}

.level-section:not(:first-child) .level-cards {
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
}
```

```css
/* AgentCard.vue */
/* 修改前 */
.agent-card.is-main .avatar {
  font-size: 2.5rem;
  width: 54px;
  height: 54px;
}

.agent-card.is-main .name {
  font-size: 1.1rem;
}

/* 修改后 */
.agent-card.is-main .avatar {
  font-size: 2.2rem;
  width: 48px;
  height: 48px;
}

.agent-card.is-main .name {
  font-size: 1rem;
}

.agent-card.is-main .card-header {
  padding: 0.85rem 1rem;
}

.agent-card.is-main .card-body {
  padding: 0.85rem 1rem;
}
```

---

### REQ-2: 优化详情弹窗宽度和布局

**问题**：
- 弹窗宽度 600px，时序视图等内容显示拥挤
- 5 个 Tab 按钮在窄容器中显得拥挤

**解决方案**：
1. 弹窗宽度增大到 800px
2. Tab 按钮间距优化
3. 增加响应式适配

**修改文件**：
- `frontend/src/components/AgentDetailPanel.vue`

**具体修改**：

```css
/* AgentDetailPanel.vue */
/* 修改前 */
.panel {
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
}

.view-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-btn {
  padding: 8px 16px;
  font-size: 13px;
}

/* 修改后 */
.panel {
  width: 800px;
  max-width: 92vw;
  max-height: 90vh;
}

.view-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  margin-bottom: 12px;
}

.tab-btn {
  padding: 6px 12px;
  font-size: 12px;
  flex-shrink: 0;
}
```

---

### REQ-3: 合并详情弹窗 Tab 视图

**问题**：
- 5 个 Tab 按钮占用空间
- 配置和错误分析使用频率较低

**解决方案**：
1. 保留核心 Tab：时序视图、链路视图
2. 合并"配置"和"错误分析"为"高级"
3. 移除"简单视图"（功能与时序重复）

**修改文件**：
- `frontend/src/components/AgentDetailPanel.vue`

**具体修改**：

```vue
<!-- 修改前 -->
<div class="view-tabs">
  <button class="tab-btn" :class="{ active: activeView === 'timeline' }">📊 时序视图</button>
  <button class="tab-btn" :class="{ active: activeView === 'chain' }">🔗 链路视图</button>
  <button class="tab-btn" :class="{ active: activeView === 'config' }">⚙️ 配置</button>
  <button class="tab-btn" :class="{ active: activeView === 'errors' }">🔍 错误分析</button>
  <button class="tab-btn" :class="{ active: activeView === 'simple' }">📋 简单视图</button>
</div>

<!-- 修改后 -->
<div class="view-tabs">
  <button class="tab-btn" :class="{ active: activeView === 'timeline' }">📊 时序视图</button>
  <button class="tab-btn" :class="{ active: activeView === 'chain' }">🔗 链路视图</button>
  <button class="tab-btn" :class="{ active: activeView === 'advanced' }">⚙️ 高级</button>
</div>
```

```typescript
// 修改类型定义
const activeView = ref<'timeline' | 'chain' | 'advanced'>('timeline')

// 高级视图模板
<div v-else-if="activeView === 'advanced'" class="advanced-container">
  <div class="advanced-section">
    <h4>⚙️ 配置</h4>
    <AgentConfigPanel :agentId="agent.id" />
  </div>
  <div class="advanced-section">
    <h4>🔍 错误分析</h4>
    <ErrorAnalysisView :agentId="agent.id" />
  </div>
</div>
```

```css
/* 新增样式 */
.advanced-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.advanced-section {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.advanced-section h4 {
  margin: 0;
  padding: 10px 14px;
  background: #f9fafb;
  border-bottom: 1px solid #e5e7eb;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}
```

---

### REQ-4: 优化模型面板宽度

**问题**：
- 模型面板宽度 120px，模型名称常被截断

**解决方案**：
1. 增加宽度到 150px
2. 优化模型名称显示

**修改文件**：
- `frontend/src/components/collaboration/CollaborationFlowSection.vue`

**具体修改**：

```css
/* 修改前 */
.model-panel {
  width: 120px;
}

/* 修改后 */
.model-panel {
  width: 150px;
  min-width: 120px;
}
```

---

## 实现步骤

### Step 1: 修改主 Agent 卡片样式 (REQ-1)

1. 修改 `CollaborationFlowSection.vue` 中的 `.agent-card-wrapper.main-agent` 宽度
2. 修改 `AgentCard.vue` 中的 `.is-main` 相关样式
3. 调整层级布局间距

### Step 2: 优化详情弹窗 (REQ-2, REQ-3)

1. 修改 `AgentDetailPanel.vue` 弹窗宽度
2. 重构 Tab 视图结构
3. 合并低频视图

### Step 3: 优化模型面板 (REQ-4)

1. 修改模型面板宽度
2. 测试长模型名称显示

### Step 4: 响应式适配

1. 添加媒体查询
2. 测试不同屏幕尺寸

---

## 验收标准

| 编号 | 验收点 | 期望结果 |
|------|--------|----------|
| AC-1 | 主 Agent 卡片宽度 | 260px ± 10px |
| AC-2 | 子 Agent 卡片最小宽度 | 200px |
| AC-3 | 详情弹窗宽度 | 800px (桌面) |
| AC-4 | Tab 按钮数量 | 3 个 |
| AC-5 | 模型面板宽度 | 150px |
| AC-6 | 响应式适配 | 1280px/1440px/1920px 屏幕正常显示 |

---

## 测试用例

### TC-1: 主 Agent 卡片比例
- 前置: 打开 Dashboard
- 操作: 观察主 Agent (PM) 卡片
- 期望: 卡片宽度约 260px，与子 Agent 比例协调

### TC-2: 详情弹窗宽度
- 前置: 点击任意 Agent 卡片
- 操作: 观察弹窗宽度
- 期望: 弹窗宽度 800px，时序视图显示宽敞

### TC-3: Tab 视图切换
- 前置: 打开详情弹窗
- 操作: 切换不同 Tab
- 期望: 3 个 Tab，切换流畅

### TC-4: 响应式布局
- 前置: 打开 Dashboard
- 操作: 调整浏览器窗口宽度
- 期望: 1280px-1920px 范围内布局正常

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 弹窗在小屏幕溢出 | 中 | max-width: 92vw 保底 |
| 合并视图导致功能缺失 | 低 | 高级视图保留所有功能 |
| 样式兼容性问题 | 低 | 渐进式修改，每步测试 |

---

## 时间估算

| 步骤 | 时间 |
|------|------|
| Step 1: 卡片样式修改 | 30 分钟 |
| Step 2: 弹窗优化 | 45 分钟 |
| Step 3: 模型面板 | 15 分钟 |
| Step 4: 响应式适配 | 20 分钟 |
| 测试验证 | 20 分钟 |
| **总计** | **2 小时 10 分钟** |

---

## 相关文档

- [前端分析报告](./analysis/collaboration-flow-ui-analysis.md)

---

## 完成总结

### 实施日期
2026-03-05

### 修改文件清单
| 文件 | 修改内容 |
|------|----------|
| `frontend/src/components/collaboration/CollaborationFlowSection.vue` | 主卡片宽度 320px→260px，子卡片最小宽度 180px→200px，模型面板 120px→150px，移除固定高度，添加响应式 |
| `frontend/src/components/AgentCard.vue` | 主卡片 avatar 54px→48px，字体 1.1rem→1rem，内边距缩小 |
| `frontend/src/components/AgentDetailPanel.vue` | 弹窗宽度 600px→800px，Tab 从 5 个合并为 3 个，添加高级视图，添加响应式 |

### 验收结果
- [x] AC-1: 主 Agent 卡片宽度调整为 260px
- [x] AC-2: 子 Agent 卡片最小宽度调整为 200px
- [x] AC-3: 详情弹窗宽度调整为 800px
- [x] AC-4: Tab 按钮数量从 5 个减少为 3 个
- [x] AC-5: 模型面板宽度调整为 150px
- [x] AC-6: 添加响应式适配（1280px/1024px/768px 断点）

### 构建验证
前端构建成功，无编译错误。
