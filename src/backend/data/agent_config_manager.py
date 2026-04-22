"""
Agent 配置管理器 - 读取和修改 openclaw.json 中的 Agent 配置
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import shutil
from datetime import datetime

from data.config_reader import get_openclaw_root, normalize_openclaw_agent_id, agent_ids_equal
from data.session_reader import normalize_sessions_index


def _backup_config() -> Optional[Path]:
    """备份配置文件"""
    root = get_openclaw_root()
    config_path = root / "openclaw.json"
    if not config_path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = root / f"openclaw.json.backup-{timestamp}"
    shutil.copy2(config_path, backup_path)
    return backup_path


def load_full_config() -> Dict[str, Any]:
    """加载完整的 openclaw.json"""
    config_path = get_openclaw_root() / "openclaw.json"
    if not config_path.exists():
        return {}
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_full_config(config: Dict[str, Any]) -> bool:
    """保存完整配置"""
    try:
        _backup_config()
        config_path = get_openclaw_root() / "openclaw.json"
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


def get_agent_config(agent_id: str) -> Optional[Dict[str, Any]]:
    """获取单个 Agent 的完整配置"""
    config = load_full_config()
    agents = config.get('agents', {})
    agent_list = agents.get('list', [])

    for agent in agent_list:
        if agent_ids_equal(agent.get('id'), agent_id):
            return agent
    return None


def get_agent_model_config(agent_id: str) -> Dict[str, Any]:
    """获取 Agent 的模型配置"""
    agent = get_agent_config(agent_id)
    if not agent:
        return {'primary': '', 'fallbacks': []}

    model_cfg = agent.get('model', {})

    # 获取默认配置
    config = load_full_config()
    defaults = config.get('agents', {}).get('defaults', {})
    default_model = defaults.get('model', {})

    return {
        'primary': model_cfg.get('primary') or default_model.get('primary', ''),
        'fallbacks': model_cfg.get('fallbacks') or default_model.get('fallbacks', []),
    }


def _model_id_to_display_name(model_id: str) -> str:
    """展示策略：使用 id 不用别名。取 provider/model 的 model 部分，或原样返回"""
    if not model_id:
        return ''
    parts = model_id.split('/')
    return parts[-1] if len(parts) > 1 else model_id


def _model_entry_from_id(model_id: str, provider: str) -> Dict[str, Any]:
    """由 model_id 与 provider 构造与 providers 结构一致的单项（展示用 id 不用别名）"""
    return {
        'id': model_id,
        'name': _model_id_to_display_name(model_id),
        'provider': provider,
        'contextWindow': 0,
        'maxTokens': 0,
        'reasoning': False,
        'input': ['text'],
    }


def _get_allowlist_model_ids(config: Dict[str, Any]) -> List[str]:
    """
    获取模型白名单（与 OpenClaw buildAllowedModelSet 一致）。
    来源：agents.defaults.models 的 key。
    注：OpenClaw 源码仅使用 agents.defaults.models，未使用 agents.list[].models 作为白名单。
    """
    defaults = config.get('agents', {}).get('defaults', {})
    models_cfg = defaults.get('models', {}) or {}
    if not isinstance(models_cfg, dict):
        return []
    return [k for k in models_cfg.keys() if k and isinstance(k, str)]


def get_all_available_models() -> List[Dict[str, Any]]:
    """
    获取所有可用模型列表，与 OpenClaw 逻辑保持一致：
    - 若存在 agents.defaults.models（白名单）：仅显示白名单中的模型，展示用 id 不用别名。
    - 若无白名单：显示 models.providers 完整目录；若无 providers 则从 agents 收集。
    详见 docs/design/openclaw-config-models-and-agents.md
    """
    from data.config_reader import get_all_models_from_agents

    config = load_full_config()
    providers = config.get('models', {}).get('providers', {})

    # 构建 providers 目录
    catalog_models: List[Dict[str, Any]] = []
    catalog_ids: set = set()
    for provider_name, provider_cfg in providers.items():
        for model in provider_cfg.get('models', []):
            model_id = f"{provider_name}/{model.get('id', '')}"
            catalog_ids.add(model_id)
            catalog_models.append({
                'id': model_id,
                'name': _model_id_to_display_name(model_id),  # 展示用 id 不用别名
                'provider': provider_name,
                'contextWindow': model.get('contextWindow', 0),
                'maxTokens': model.get('maxTokens', 0),
                'reasoning': model.get('reasoning', False),
                'input': model.get('input', ['text']),
            })

    allowlist = _get_allowlist_model_ids(config)

    if allowlist:
        # 有白名单：仅显示白名单中的模型，与 OpenClaw 一致
        allowed_set = set(allowlist)
        result = []
        for m in catalog_models:
            if m['id'] in allowed_set:
                result.append(m)
        for model_id in allowed_set:
            if model_id not in catalog_ids:
                provider = model_id.split('/')[0] if '/' in model_id else 'default'
                result.append(_model_entry_from_id(model_id, provider))
        return result

    # 无白名单：显示 providers 或从 agents 收集
    if catalog_models:
        try:
            used_ids = set(get_all_models_from_agents())
        except Exception as e:
            print(f"[AgentConfig] 从 Agent 配置收集模型 ID 失败: {e}")
            used_ids = set()
        result = list(catalog_models)
        for model_id in used_ids:
            if not model_id or model_id in catalog_ids:
                continue
            provider = model_id.split('/')[0] if '/' in model_id else 'default'
            result.append(_model_entry_from_id(model_id, provider))
        return result

    # 无 providers：从 agents 收集
    try:
        used_ids = set(get_all_models_from_agents())
    except Exception as e:
        print(f"[AgentConfig] 从 Agent 配置收集模型 ID 失败: {e}")
        used_ids = set()
    result = []
    for model_id in used_ids:
        if not model_id:
            continue
        provider = model_id.split('/')[0] if '/' in model_id else 'default'
        result.append(_model_entry_from_id(model_id, provider))
    return result


def update_agent_model(agent_id: str, primary: Optional[str] = None, fallbacks: Optional[List[str]] = None) -> Dict[str, Any]:
    """更新 Agent 的模型配置"""
    config = load_full_config()
    agents = config.get('agents', {})
    agent_list = agents.get('list', [])

    found = False
    for agent in agent_list:
        if agent_ids_equal(agent.get('id'), agent_id):
            if 'model' not in agent:
                agent['model'] = {}

            if primary is not None:
                agent['model']['primary'] = primary

            if fallbacks is not None:
                agent['model']['fallbacks'] = fallbacks

            found = True
            break

    if not found:
        return {'success': False, 'error': f'Agent {agent_id} not found'}

    if save_full_config(config):
        return {'success': True, 'agent_id': agent_id}
    else:
        return {'success': False, 'error': 'Failed to save config'}


def get_agent_full_info(agent_id: str) -> Dict[str, Any]:
    """获取 Agent 的完整信息（配置 + 运行状态）"""
    agent_config = get_agent_config(agent_id)
    if not agent_config:
        return {'error': f'Agent {agent_id} not found', 'found': False}

    model_config = get_agent_model_config(agent_id)

    # 检查运行状态
    aid = normalize_openclaw_agent_id(agent_id)
    session_file = get_openclaw_root() / "agents" / aid / "sessions" / "sessions.json"
    status = 'idle'
    last_active = None

    if session_file.exists():
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                sessions_data = json.load(f)
            entries = normalize_sessions_index(sessions_data)
            if entries:
                latest = max(entries.values(), key=lambda e: e.get('lastMessageAt', 0))
                last_active = latest.get('lastMessageAt')
                if latest.get('active'):
                    status = 'working'
        except Exception:
            pass

    return {
        'found': True,
        'id': agent_config.get('id', agent_id),
        'name': agent_config.get('name', agent_id),
        'workspace': agent_config.get('workspace', ''),
        'model': model_config,
        'status': status,
        'lastActiveAt': last_active,
        'systemPrompt': agent_config.get('systemPrompt', ''),
        'description': agent_config.get('description', ''),
    }


def get_all_agents_info() -> List[Dict[str, Any]]:
    """获取所有 Agent 的基本信息"""
    config = load_full_config()
    agents = config.get('agents', {})
    agent_list = agents.get('list', [])

    result = []
    for agent in agent_list:
        agent_id = agent.get('id', '')
        if not agent_id:
            continue

        info = get_agent_full_info(agent_id)
        result.append(info)

    return result
