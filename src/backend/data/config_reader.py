"""
配置读取器 - 读取 openclaw.json
"""
import json
from pathlib import Path
from typing import List, Dict, Any

OPENCLAW_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"


def load_config() -> Dict[str, Any]:
    """加载 openclaw.json"""
    if not OPENCLAW_CONFIG_PATH.exists():
        return {}
    
    with open(OPENCLAW_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_agents_list() -> List[Dict[str, Any]]:
    """获取 Agent 列表"""
    config = load_config()
    return config.get('agents', {}).get('list', [])


def get_main_agent_id() -> str:
    """获取主 Agent ID（配置中 id 为 main 的，或列表第一个）"""
    agents = get_agents_list()
    for a in agents:
        if a.get('id') == 'main':
            return 'main'
    return agents[0].get('id', 'main') if agents else 'main'


def get_workspace_paths() -> List[Path]:
    """获取所有 Agent 的 workspace 路径（用于 model-failures.log 等）"""
    agents = get_agents_list()
    paths = []
    seen = set()
    for a in agents:
        ws = a.get('workspace')
        if ws and ws not in seen:
            p = Path(ws).expanduser() if isinstance(ws, str) else Path(ws)
            if p.exists():
                paths.append(p)
                seen.add(ws)
    if not paths:
        paths.append(OPENCLAW_CONFIG_PATH.parent / "workspace-main")
    return paths


def get_agent_config(agent_id: str) -> Dict[str, Any]:
    """获取单个 Agent 配置"""
    agents = get_agents_list()
    for agent in agents:
        if agent.get('id') == agent_id:
            return agent
    return {}


def get_default_config() -> Dict[str, Any]:
    """获取默认配置"""
    config = load_config()
    return config.get('agents', {}).get('defaults', {})


def get_agent_models(agent_id: str) -> Dict[str, Any]:
    """获取 Agent 的模型配置（primary + fallbacks）"""
    agent = get_agent_config(agent_id)
    model_cfg = agent.get('model') or {}
    defaults = get_default_config()
    default_model = defaults.get('model', {})
    primary = model_cfg.get('primary') or default_model.get('primary') or ''
    fallbacks = model_cfg.get('fallbacks') or default_model.get('fallbacks') or []
    return {'primary': primary, 'fallbacks': fallbacks}


def get_all_models_from_agents() -> List[str]:
    """从所有 Agent 配置中收集用到的模型 ID（provider/model 格式）"""
    agents = get_agents_list()
    model_ids = set()
    for agent in agents:
        cfg = get_agent_models(agent.get('id', ''))
        if cfg.get('primary'):
            model_ids.add(cfg['primary'])
        for fb in cfg.get('fallbacks', []):
            model_ids.add(fb)
    return sorted(model_ids)


def get_model_display_name(model_id: str) -> str:
    """获取模型显示名（provider/model -> 简短名）"""
    config = load_config()
    models_cfg = config.get('agents', {}).get('defaults', {}).get('models', {})
    alias = models_cfg.get(model_id, {}).get('alias') if isinstance(models_cfg.get(model_id), dict) else None
    if alias:
        return alias
    parts = model_id.split('/')
    return parts[-1] if len(parts) > 1 else model_id
