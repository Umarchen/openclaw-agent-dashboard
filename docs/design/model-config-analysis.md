# OpenClaw 模型配置分析与 Dashboard 功能设计

## 一、OpenClaw 配置文件结构分析

### 1.1 配置文件位置

```
~/.openclaw/openclaw.json
```

### 1.2 完整结构示意

```json
{
  "models": {
    "providers": {
      "anthropic": {
        "models": [
          {
            "id": "claude-sonnet-4-6",
            "name": "Claude Sonnet 4.6",
            "contextWindow": 200000,
            "maxTokens": 8192,
            "reasoning": false,
            "input": ["text", "image"]
          },
          {
            "id": "claude-opus-4-6",
            "name": "Claude Opus 4.6",
            "contextWindow": 200000,
            "maxTokens": 16384,
            "reasoning": true
          }
        ]
      },
      "openai": {
        "models": [
          { "id": "gpt-4o", "name": "GPT-4o" },
          { "id": "gpt-4-turbo", "name": "GPT-4 Turbo" }
        ]
      }
    }
  },

  "agents": {
    "defaults": {
      "model": {
        "primary": "anthropic/claude-sonnet-4-6",
        "fallbacks": ["anthropic/claude-opus-4-6", "openai/gpt-4o"]
      },
      "models": {
        "anthropic/claude-sonnet-4-6": { "alias": "Sonnet" },
        "anthropic/claude-opus-4-6": { "alias": "Opus" }
      },
      "subagents": {
        "runTimeoutSeconds": 900
      }
    },

    "list": [
      {
        "id": "main",
        "name": "Project Manager",
        "workspace": "~/.openclaw/workspace-main",
        "model": {
          "primary": "anthropic/claude-sonnet-4-6",
          "fallbacks": ["anthropic/claude-opus-4-6"]
        }
      },
      {
        "id": "developer",
        "name": "Developer Agent",
        "workspace": "~/.openclaw/workspace-developer",
        "model": {
          "primary": "anthropic/claude-sonnet-4-6",
          "fallbacks": ["openai/gpt-4o"]
        }
      },
      {
        "id": "reviewer",
        "name": "Code Reviewer",
        "model": {
          "primary": "anthropic/claude-opus-4-6"
        }
      }
    ]
  },

  "plugins": {
    "entries": {
      "openclaw-agent-dashboard": {
        "config": { "port": 38271 }
      }
    }
  }
}
```

### 1.3 各字段含义与用途

| 路径 | 含义 | 用途 |
|------|------|------|
| `models.providers` | **模型提供商配置** | 定义所有可用的模型及其详细参数（上下文窗口、最大输出等） |
| `agents.defaults.model` | **默认模型配置** | 所有 Agent 的默认主模型和备选模型 |
| `agents.defaults.models` | **模型别名映射** | 为模型 ID 设置友好的显示名称 |
| `agents.list[].model` | **Agent 级别模型配置** | 单个 Agent 的模型配置，覆盖 defaults |

---

## 二、模型配置的层次结构

### 2.1 配置优先级（从高到低）

```
agents.list[id].model.primary
         ↓ 若为空
agents.defaults.model.primary
         ↓ 若为空
（无默认值，需显式配置）
```

### 2.2 模型配置的作用

1. **`models.providers`** - 模型注册表
   - 声明系统中所有可用的模型
   - 包含模型的技术参数（contextWindow, maxTokens 等）
   - 支持多 Provider（Anthropic, OpenAI, 本地模型等）

2. **`agents.defaults.model`** - 全局默认
   - 为未单独配置的 Agent 提供默认模型
   - 统一管理 fallback 策略

3. **`agents.list[id].model`** - Agent 个性化
   - 为特定 Agent 指定不同的模型
   - 例如：复杂任务用 Opus，简单任务用 Sonnet

---

## 三、用户场景分析

### 场景 1：标准配置（有 models.providers）

**用户特征：** 完整配置了 OpenClaw，包括模型提供商列表

**配置示例：**
```json
{
  "models": { "providers": { ... } },
  "agents": { "defaults": { "model": { ... } } }
}
```

**Dashboard 行为：**
- ✅ 从 `models.providers` 读取完整模型列表
- ✅ 显示模型的详细参数（上下文窗口等）
- ✅ 按 Provider 分组展示

---

### 场景 2：简化配置（无 models.providers）

**用户特征：** 只配置了 Agent 的模型，没有完整的 providers 列表

**配置示例：**
```json
{
  "agents": {
    "defaults": { "model": { "primary": "anthropic/claude-sonnet-4-6" } },
    "list": [ { "id": "main", "model": { ... } } ]
  }
}
```

**Dashboard 行为：**
- ⚠️ `models.providers` 为空，无法展示完整模型列表
- ✅ 从已配置的 Agent 中收集已使用的模型
- ⚠️ 缺少模型详细参数

---

### 场景 3：多 Agent 异构配置

**用户特征：** 多个 Agent 使用不同的模型

**配置示例：**
```json
{
  "agents": {
    "list": [
      { "id": "pm", "model": { "primary": "anthropic/claude-opus-4-6" } },
      { "id": "dev", "model": { "primary": "anthropic/claude-sonnet-4-6" } },
      { "id": "test", "model": { "primary": "openai/gpt-4o" } }
    ]
  }
}
```

**Dashboard 行为：**
- ✅ 收集所有 Agent 使用的模型
- ✅ 展示模型多样性

---

### 场景 4：新用户/空配置

**用户特征：** 刚安装，未配置任何模型

**Dashboard 行为：**
- ❌ 无可用模型显示
- 💡 需要引导用户配置

---

## 四、Dashboard 功能设计

### 4.1 模型选择下拉框的数据来源策略

**优先级顺序：**

```
1. models.providers          → 完整模型列表（有详细参数）
2. agents.defaults.model     → 默认主模型 + fallbacks
3. agents.list[].model       → 各 Agent 已配置的模型
4. 内置常用模型列表          → 兜底方案
```

### 4.2 数据获取流程

```
┌─────────────────────────────────────────────────────────┐
│                    get_all_available_models()           │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │ models.providers 存在？│
              └───────────────────────┘
                    │           │
                   Yes          No
                    │           │
                    ▼           ▼
         ┌─────────────┐  ┌─────────────────────────┐
         │ 返回完整列表 │  │ 从 Agent 配置收集模型    │
         │ (含详细参数) │  │ + defaults + 内置列表   │
         └─────────────┘  └─────────────────────────┘
```

### 4.3 模型数据结构

```typescript
interface Model {
  id: string           // "anthropic/claude-sonnet-4-6"
  name: string         // "Claude Sonnet 4.6" 或 "Sonnet"（别名）
  provider: string     // "anthropic"
  contextWindow: number  // 200000
  maxTokens: number      // 8192
  reasoning: boolean     // 是否支持推理增强
  input: string[]        // ["text", "image"]
  source: 'providers' | 'agents' | 'defaults' | 'builtin'  // 数据来源
}
```

### 4.4 前端展示策略

**主模型选择：**
- 展示所有可用模型
- 按 Provider 分组
- 高亮当前 Agent 已配置的模型

**备选模型选择：**
- 展示所有可用模型（排除已选中的）
- 支持添加/删除 fallback
- 最多 3 个 fallback

---

## 五、实现方案

### 5.1 后端修改（agent_config_manager.py）

```python
# 内置常用模型列表（兜底）
BUILTIN_MODELS = [
    {
        'id': 'anthropic/claude-sonnet-4-6',
        'name': 'Claude Sonnet 4.6',
        'provider': 'anthropic',
        'contextWindow': 200000,
        'maxTokens': 8192,
        'reasoning': False,
        'input': ['text', 'image'],
    },
    {
        'id': 'anthropic/claude-opus-4-6',
        'name': 'Claude Opus 4.6',
        'provider': 'anthropic',
        'contextWindow': 200000,
        'maxTokens': 16384,
        'reasoning': True,
        'input': ['text', 'image'],
    },
    {
        'id': 'openai/gpt-4o',
        'name': 'GPT-4o',
        'provider': 'openai',
        'contextWindow': 128000,
        'maxTokens': 4096,
        'reasoning': False,
        'input': ['text', 'image'],
    },
]

def get_all_available_models() -> List[Dict[str, Any]]:
    """
    获取所有可用模型列表

    优先级：
    1. models.providers（完整配置）
    2. agents.defaults.model（默认配置）
    3. agents.list[].model（各 Agent 配置）
    4. 内置常用模型（兜底）
    """
    config = load_full_config()
    models = []
    seen_ids = set()

    # 1. 从 models.providers 读取
    providers = config.get('models', {}).get('providers', {})
    for provider_name, provider_cfg in providers.items():
        for model in provider_cfg.get('models', []):
            model_id = f"{provider_name}/{model.get('id', '')}"
            if model_id in seen_ids:
                continue
            seen_ids.add(model_id)
            models.append({
                'id': model_id,
                'name': model.get('name', model.get('id', '')),
                'provider': provider_name,
                'contextWindow': model.get('contextWindow', 0),
                'maxTokens': model.get('maxTokens', 0),
                'reasoning': model.get('reasoning', False),
                'input': model.get('input', ['text']),
                'source': 'providers',
            })

    if models:
        return models

    # 2. 从 agents.defaults.model 读取
    defaults = config.get('agents', {}).get('defaults', {})
    default_model = defaults.get('model', {})

    def add_model(model_id: str, source: str):
        if not model_id or model_id in seen_ids:
            return
        seen_ids.add(model_id)
        provider = model_id.split('/')[0] if '/' in model_id else 'default'
        # 尝试获取别名
        alias = defaults.get('models', {}).get(model_id, {}).get('alias')
        models.append({
            'id': model_id,
            'name': alias or model_id.split('/')[-1],
            'provider': provider,
            'contextWindow': 0,
            'maxTokens': 0,
            'reasoning': False,
            'input': ['text'],
            'source': source,
        })

    if default_model.get('primary'):
        add_model(default_model['primary'], 'defaults')
    for fb in default_model.get('fallbacks', []):
        add_model(fb, 'defaults')

    # 3. 从各 Agent 配置读取
    agent_list = config.get('agents', {}).get('list', [])
    for agent in agent_list:
        model_cfg = agent.get('model', {})
        if model_cfg.get('primary'):
            add_model(model_cfg['primary'], 'agents')
        for fb in model_cfg.get('fallbacks', []):
            add_model(fb, 'agents')

    # 4. 如果仍为空，使用内置列表
    if not models:
        for m in BUILTIN_MODELS:
            if m['id'] not in seen_ids:
                seen_ids.add(m['id'])
                models.append({**m, 'source': 'builtin'})

    return models
```

### 5.2 前端修改（AgentConfigPanel.vue）

无需修改，当前已正确调用 `/api/available-models` 接口。

---

## 六、测试场景

| 场景 | 配置状态 | 预期结果 |
|------|----------|----------|
| 完整配置 | 有 models.providers | 显示完整模型列表，按 Provider 分组 |
| 简化配置 | 仅有 defaults.model | 显示已配置的模型 |
| Agent 配置 | 各 Agent 有不同模型 | 合并显示所有模型 |
| 空配置 | 无任何模型配置 | 显示内置常用模型列表 |

---

## 七、总结

### 7.1 核心原则

1. **兼容性优先**：支持各种配置程度（从完整到空）
2. **数据来源透明**：让用户知道模型列表来自哪里
3. **兜底保障**：内置常用模型确保下拉框不为空

### 7.2 当前代码状态

当前 `get_all_available_models()` 已实现了从 `models.providers` 和 Agent 配置读取的逻辑，但缺少：
1. 内置模型兜底
2. 从 `defaults.model` 读取的逻辑

### 7.3 建议修改

按照 5.1 节的实现方案修改 `agent_config_manager.py`，确保在各种配置场景下都能提供模型选项。
