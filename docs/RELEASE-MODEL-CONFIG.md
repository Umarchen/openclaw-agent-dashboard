# openclaw-agent-dashboard 模型配置修改总结

## 一、修改概览

本工程对模型配置模块进行了调整，使显示与配置生效逻辑与 OpenClaw 保持一致。

---

## 二、涉及文件

| 文件 | 修改内容 |
|------|----------|
| `src/backend/data/agent_config_manager.py` | 白名单过滤、展示用 id、`_get_allowlist_model_ids` |
| `src/backend/data/config_reader.py` | `get_model_display_name` 改为仅用 id |
| `scripts/test_available_models.py` | 新增白名单、保存格式测试 |

---

## 三、与 OpenClaw 配置格式的对应关系

### 3.1 配置读取（Agent 生效时使用）

| OpenClaw 配置路径 | 含义 | Dashboard 读取 |
|-------------------|------|----------------|
| `agents.defaults.model.primary` | 默认主模型 | `get_agent_model_config` 合并 |
| `agents.defaults.model.fallbacks` | 默认备选 | 同上 |
| `agents.list[].model.primary` | Agent 主模型 | 覆盖 defaults |
| `agents.list[].model.fallbacks` | Agent 备选 | 覆盖 defaults |

**生效格式**：`provider/model`（如 `zhipu/glm-4`、`openai/gpt-4`）

### 3.2 配置写入（用户保存后）

| 写入路径 | 格式 | 示例 |
|----------|------|------|
| `agents.list[id].model.primary` | model_id 字符串 | `"openai/gpt-4"` |
| `agents.list[id].model.fallbacks` | model_id 数组 | `["zhipu/glm-4-flash"]` |

**与 OpenClaw 一致**：`update_agent_model` 直接写入上述字段。

### 3.3 可选模型列表（白名单）

| 条件 | 显示来源 | 与 OpenClaw 一致 |
|------|----------|------------------|
| 有 `agents.defaults.models` | 仅白名单中的 model_id | ✓ buildAllowedModelSet |
| 无白名单 + 有 `models.providers` | providers 全量 + agents 已用 | ✓ |
| 无白名单 + 无 providers | 从 agents 收集 | ✓ |

### 3.4 展示策略

| 策略 | 实现 | 说明 |
|------|------|------|
| 使用 id 不用别名 | `_model_id_to_display_name` | `zhipu/glm-4` → `glm-4` |
| 下拉 option value | `model.id`（model_id） | 保存时写入 primary/fallbacks |

---

## 四、数据流

```
用户选择模型（下拉 option value = model_id）
    ↓
PUT /api/agent-config/{id}/model { primary, fallbacks }
    ↓
update_agent_model() 写入 agents.list[].model
    ↓
openclaw.json 格式符合 OpenClaw 约定
    ↓
OpenClaw 重启后读取 model.primary / model.fallbacks 生效
```

---

## 五、测试场景

| 场景 | 验证点 |
|------|--------|
| 1 | 无 providers，从 agents 收集 |
| 2 | 仅 defaults.model |
| 3 | agents.list 为空 |
| 3b | 白名单 + 展示用 id |
| 3c | providers + 白名单，仅显示白名单 |
| 3d | 配置保存格式（primary/fallbacks） |

---

## 六、符合性结论

| 维度 | 符合预期 |
|------|----------|
| 配置读取格式 | ✓ agents.list[].model.primary/fallbacks |
| 配置写入格式 | ✓ 同上 |
| 白名单逻辑 | ✓ agents.defaults.models 与 buildAllowedModelSet 一致 |
| 展示策略 | ✓ 使用 id 不用别名 |
| 无白名单时 | ✓ providers 或 agents 收集 |
