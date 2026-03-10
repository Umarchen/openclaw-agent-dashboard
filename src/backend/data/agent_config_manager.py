"""
Agent 配置管理器 - 读取和修改 openclaw.json 中的 Agent 配置
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import shutil
from datetime import datetime


def _openclaw_home() -> Path:
    """OpenClaw 根目录"""
    env = os.environ.get("OPENCLAW_HOME")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
    return Path.home() / ".openclaw"


OPENCLAW_DIR = _openclaw_home()
OPENCLAW_CONFIG_PATH = OPENCLAW_DIR / "openclaw.json"


def _backup_config() -> Optional[Path]:
    """备份配置文件"""
    if not OPENCLAW_CONFIG_PATH.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = OPENCLAW_DIR / f"openclaw.json.backup-{timestamp}"
    shutil.copy2(OPENCLAW_CONFIG_PATH, backup_path)
    return backup_path


def load_full_config() -> Dict[str, Any]:
    """加载完整的 openclaw.json"""
    if not OPENCLAW_CONFIG_PATH.exists():
        return {}
    with open(OPENCLAW_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_full_config(config: Dict[str, Any]) -> bool:
    """保存完整配置"""
    try:
        _backup_config()
        with open(OPENCLAW_CONFIG_PATH, 'w', encoding='utf-8') as f:
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
        if agent.get('id') == agent_id:
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


def get_all_available_models() -> List[Dict[str, Any]]:
    """获取所有可用模型列表：优先从 openclaw.json 的 models.providers 读取；若无则从各 Agent 已配置的主模型与 fallback 收集"""
    config = load_full_config()
    providers = config.get('models', {}).get('providers', {})

    models = []
    for provider_name, provider_cfg in providers.items():
        for model in provider_cfg.get('models', []):
            model_id = f"{provider_name}/{model.get('id', '')}"
            models.append({
                'id': model_id,
                'name': model.get('name', model.get('id', '')),
                'provider': provider_name,
                'contextWindow': model.get('contextWindow', 0),
                'maxTokens': model.get('maxTokens', 0),
                'reasoning': model.get('reasoning', False),
                'input': model.get('input', ['text']),
            })

    if models:
        return models

    # 无 models.providers 或为空时：从各 Agent 配置中收集已使用的主模型与 fallback，保证下拉框有选项
    try:
        from data.config_reader import get_all_models_from_agents, get_model_display_name
        for model_id in get_all_models_from_agents():
            if not model_id:
                continue
            provider = model_id.split('/')[0] if '/' in model_id else 'default'
            models.append({
                'id': model_id,
                'name': get_model_display_name(model_id),
                'provider': provider,
                'contextWindow': 0,
                'maxTokens': 0,
                'reasoning': False,
                'input': ['text'],
            })
    except Exception as e:
        print(f"[AgentConfig] 从 Agent 配置收集模型列表失败: {e}")

    return models


def update_agent_model(agent_id: str, primary: Optional[str] = None, fallbacks: Optional[List[str]] = None) -> Dict[str, Any]:
    """更新 Agent 的模型配置"""
    config = load_full_config()
    agents = config.get('agents', {})
    agent_list = agents.get('list', [])

    found = False
    for agent in agent_list:
        if agent.get('id') == agent_id:
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
    session_file = OPENCLAW_DIR / f"agents/{agent_id}/sessions/sessions.json"
    status = 'idle'
    last_active = None

    if session_file.exists():
        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                sessions_data = json.load(f)
            entries = sessions_data.get('entries', {})
            if entries:
                latest = max(entries.values(), key=lambda e: e.get('lastMessageAt', 0))
                last_active = latest.get('lastMessageAt')
                if latest.get('active'):
                    status = 'working'
        except Exception:
            pass

    return {
        'found': True,
        'id': agent_id,
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
