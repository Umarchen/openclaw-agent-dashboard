# TR9-2: 模型调用小球匹配修复

> 需求文档：规范化 model ID 格式，修复调用小球匹配问题

## 1. 需求背景

### 1.1 问题描述

协作流程右侧显示模型面板，每个模型卡片中应显示对应 Agent 的调用小球（颜色代表不同 Agent）。用户反馈：各 Agent 使用不同模型，但调用小球没有正确落入对应的模型框中。

### 1.2 根因分析

**格式不一致问题**：

| 来源 | 格式示例 | 说明 |
|------|----------|------|
| Agent 配置 | `anthropic/claude-sonnet-4.6` | provider/model 格式 |
| 模型节点 modelId | `anthropic/claude-sonnet-4.6` | 同配置 |
| Session 消息 model | `claude-sonnet-4.6` 或 `claude-sonnet-4.6-20250514` | 可能不含 provider，可能有版本号 |

**匹配失败场景**：

```
模型节点 modelId: anthropic/claude-sonnet-4.6
                    │
                    ▼
              前端尝试匹配
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
  "anthropic/   "claude-    都不匹配
   claude-       sonnet-
   sonnet-4.6"   4.6"
                    │
                    ▼
           Session 中的实际值
           可能是: "claude-sonnet-4.6-20250514"
```

## 2. 解决方案

### 2.1 后端规范化（推荐）

在获取调用记录时，将 model 字段统一为标准格式。

### 2.2 规范化函数设计

#### 2.2.1 边界情况处理

**问题**：原始实现使用 `split('-20')[0]` 存在边界问题：

| 输入 | 期望结果 | 实际结果（错误） |
|------|----------|------------------|
| `claude-sonnet-4-20250514` | `claude-sonnet-4` | `claude-sonnet-4` ❌ |
| `gpt-4-turbo-2024-04-09` | `gpt-4-turbo-2024-04-09` | `gpt-4-turbo` ❌ |

**解决**：使用正则表达式精确匹配 `-20YYMMDD` 格式的日期后缀

```python
import re

# 正确：只匹配末尾的 -20YYMMDD
base_name = re.sub(r'-20\d{6}$', '', model_from_session)
# claude-sonnet-4.6-20250514 -> claude-sonnet-4.6
# claude-sonnet-4-20250514 -> claude-sonnet-4
# gpt-4-turbo-2024-04-09 -> gpt-4-turbo-2024-04-09 (不变，格式不匹配)
```

#### 2.2.2 时区处理

**问题**：`_get_recent_model_calls` 中 `since` 和 `timestamp` 类型不一致可能导致比较错误。

**解决**：确保所有 datetime 都是 timezone-aware

```python
from datetime import datetime, timezone, timedelta

# 确保 since 是 UTC timezone-aware
now = datetime.now(timezone.utc)
since = now - timedelta(minutes=minutes)

for r in parse_session_file_with_details(session_file, agent_id):
    ts = r['timestamp']
    # 确保 timestamp 是 timezone-aware
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    if ts >= since:
        # ...
```

## 3. 技术设计

### 3.1 模型映射缓存

**文件**: `src/backend/api/collaboration.py`

```python
import re
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# 模块级缓存
_model_mapping_cache: Optional[Dict[str, str]] = None


def _get_model_mapping() -> Dict[str, str]:
    """
    获取 model 映射（带缓存）

    Returns:
        {'claude-sonnet-4.6': 'anthropic/claude-sonnet-4.6', ...}
    """
    global _model_mapping_cache
    if _model_mapping_cache is None:
        from data.config_reader import get_all_models_from_agents
        _model_mapping_cache = {}
        for model_id in get_all_models_from_agents():
            short = model_id.split('/')[-1]
            # 精确匹配
            _model_mapping_cache[short] = model_id
            # 去除日期版本号的映射
            base = re.sub(r'-20\d{6}$', '', short)
            if base != short:
                _model_mapping_cache[base] = model_id
    return _model_mapping_cache


def _normalize_model_id(model_from_session: str) -> str:
    """
    将 session 中的 model 值规范化为标准格式

    Args:
        model_from_session: session 中的 model 值

    Returns:
        标准化的模型 ID，如 "anthropic/claude-sonnet-4.6"

    Examples:
        >>> _normalize_model_id("claude-sonnet-4.6")
        "anthropic/claude-sonnet-4.6"
        >>> _normalize_model_id("claude-sonnet-4.6-20250514")
        "anthropic/claude-sonnet-4.6"
        >>> _normalize_model_id("anthropic/claude-sonnet-4.6")
        "anthropic/claude-sonnet-4.6"
    """
    if not model_from_session:
        return '(unknown)'

    # 已经是标准格式
    if '/' in model_from_session:
        return model_from_session

    mapping = _get_model_mapping()

    # 精确匹配
    if model_from_session in mapping:
        return mapping[model_from_session]

    # 使用正则去除日期版本号后匹配
    base_name = re.sub(r'-20\d{6}$', '', model_from_session)
    if base_name in mapping:
        return mapping[base_name]

    logger.debug(f"Unknown model format: {model_from_session}")
    return model_from_session
```

### 3.2 修改 _get_recent_model_calls

**文件**: `src/backend/api/collaboration.py`

```python
def _get_recent_model_calls(minutes: int = 30) -> List[Dict]:
    """
    获取最近 N 分钟的模型调用记录（用于光球展示）

    Args:
        minutes: 时间范围（分钟）

    Returns:
        调用记录列表，model 字段已规范化

    注意:
        - since 为 timezone-aware datetime (UTC)
        - timestamp 统一处理为 UTC timezone-aware
        - model 字段规范化为 provider/model 格式
    """
    from api.performance import parse_session_file_with_details
    from datetime import datetime, timezone, timedelta

    records = []
    openclaw_path = Path.home() / '.openclaw'
    agents_path = openclaw_path / 'agents'
    if not agents_path.exists():
        return []

    # 确保 since 是 UTC timezone-aware
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=minutes)

    for agent_dir in agents_path.iterdir():
        if not agent_dir.is_dir():
            continue
        agent_id = agent_dir.name
        sessions_path = agent_dir / 'sessions'
        if not sessions_path.exists():
            continue
        for session_file in sessions_path.glob('*.jsonl'):
            if 'lock' in session_file.name or 'deleted' in session_file.name:
                continue
            for r in parse_session_file_with_details(session_file, agent_id):
                ts = r['timestamp']
                # 确保 timestamp 是 timezone-aware
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)

                if ts >= since:
                    ts_local = ts.astimezone(TZ_DISPLAY)
                    # 规范化 model 字段
                    normalized_model = _normalize_model_id(r.get('model', ''))

                    records.append({
                        'agentId': agent_id,
                        'model': normalized_model,  # 使用规范化后的值
                        'sessionId': r['sessionId'],
                        'trigger': r.get('trigger', ''),
                        'tokens': r.get('tokens', 0),
                        'timestamp': int(ts.timestamp() * 1000),
                        'time': ts_local.strftime('%H:%M:%S')
                    })

    records.sort(key=lambda x: x['timestamp'])
    return records[-100:]
```

### 3.3 缓存失效机制

当配置文件变更时，需要清除缓存：

```python
def _clear_model_mapping_cache():
    """清除模型映射缓存（配置变更时调用）"""
    global _model_mapping_cache
    _model_mapping_cache = None
```

## 4. 测试用例

### 4.1 单元测试

```python
import pytest

def test_normalize_model_id_standard():
    """已经是标准格式"""
    result = _normalize_model_id("anthropic/claude-sonnet-4.6")
    assert result == "anthropic/claude-sonnet-4.6"

def test_normalize_model_id_short():
    """短格式匹配"""
    with mock.patch('_get_model_mapping', return_value={
        'claude-sonnet-4.6': 'anthropic/claude-sonnet-4.6'
    }):
        result = _normalize_model_id("claude-sonnet-4.6")
        assert result == "anthropic/claude-sonnet-4.6"

def test_normalize_model_id_with_date():
    """带日期版本号"""
    with mock.patch('_get_model_mapping', return_value={
        'claude-sonnet-4.6': 'anthropic/claude-sonnet-4.6',
        'claude-sonnet-4': 'anthropic/claude-sonnet-4'
    }):
        result = _normalize_model_id("claude-sonnet-4.6-20250514")
        assert result == "anthropic/claude-sonnet-4.6"

def test_normalize_model_id_edge_case_4():
    """边界情况：-4 不应被截断"""
    with mock.patch('_get_model_mapping', return_value={
        'claude-sonnet-4': 'anthropic/claude-sonnet-4'
    }):
        result = _normalize_model_id("claude-sonnet-4-20250514")
        assert result == "anthropic/claude-sonnet-4"

def test_normalize_model_id_unknown():
    """未知格式"""
    result = _normalize_model_id("unknown-model")
    assert result == "unknown-model"

def test_normalize_model_id_empty():
    """空值"""
    result = _normalize_model_id("")
    assert result == "(unknown)"
```

### 4.2 集成测试

```bash
# 获取协作数据，检查 recentCalls 中的 model 字段
curl http://localhost:8000/api/collaboration | jq '.recentCalls[].model'

# 期望输出：所有 model 都是 "provider/model" 格式
# "anthropic/claude-sonnet-4.6"
# "openai/gpt-4"
```

## 5. 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `collaboration.py` | 新增 `_get_model_mapping()`, `_normalize_model_id()`, `_clear_model_mapping_cache()` |
| `collaboration.py` | 修改 `_get_recent_model_calls()` 使用规范化函数 |

## 6. 调试建议

添加日志以确认实际问题：

```python
import logging
logger = logging.getLogger(__name__)

# 在 _normalize_model_id 中添加
logger.debug(f"Normalizing model: {model_from_session} -> {normalized_model}")

# 在 _get_recent_model_calls 中添加
logger.debug(f"Session model: {r.get('model')}, Normalized: {normalized_model}")
```

前端调试（仅开发环境）：

```typescript
if (import.meta.env.DEV) {
  console.log('[DEBUG] Model node:', modelId, 'Calls keys:', Object.keys(callsPerModel.value))
}
```

## 7. 注意事项

1. **正则表达式**：`-20\d{6}$` 只匹配末尾的日期后缀，避免误匹配
2. **缓存管理**：配置变更时需清除缓存
3. **向后兼容**：未知格式原样返回，不影响现有功能
4. **性能**：缓存避免重复读取配置文件
