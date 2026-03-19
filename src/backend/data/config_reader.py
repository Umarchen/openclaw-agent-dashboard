"""
配置读取器 - 读取 openclaw.json
支持 OPENCLAW_STATE_DIR、OPENCLAW_HOME 环境变量（跨平台，含 Windows）
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any


def get_openclaw_root() -> Path:
    """OpenClaw 根目录，统一解析优先级（兼容 Windows）：
    1. OPENCLAW_STATE_DIR（最高优先级）
    2. OPENCLAW_HOME（兼容两种写法：直接指向 .openclaw，或指向用户 Home 需拼接 .openclaw）
    3. ~/.openclaw（兜底）
    """
    # 1. OPENCLAW_STATE_DIR
    env_state = os.environ.get("OPENCLAW_STATE_DIR")
    if env_state:
        return Path(env_state).expanduser().resolve()

    # 2. OPENCLAW_HOME
    env_home = os.environ.get("OPENCLAW_HOME")
    if env_home:
        p = Path(env_home).expanduser().resolve()
        # 兼容两种写法：直接指向 .openclaw 目录，或指向用户 Home
        if p.name in (".openclaw", "openclaw"):
            return p
        return p / ".openclaw"

    # 3. 兜底
    return Path.home() / ".openclaw"


def load_config() -> Dict[str, Any]:
    """加载 openclaw.json"""
    config_path = get_openclaw_root() / "openclaw.json"
    if not config_path.exists():
        return {}
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_agents_list() -> List[Dict[str, Any]]:
    """获取 Agent 列表"""
    config = load_config()
    agents = config.get('agents')
    if agents is None or not isinstance(agents, dict):
        return []
    return agents.get('list', [])


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
        paths.append(get_openclaw_root() / "workspace-main")
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
    agents = config.get('agents')
    if agents is None or not isinstance(agents, dict):
        return {}
    return agents.get('defaults', {})


def get_agent_models(agent_id: str) -> Dict[str, Any]:
    """获取 Agent 的模型配置（primary + fallbacks）"""
    agent = get_agent_config(agent_id)
    model_cfg = agent.get('model') or {}
    defaults = get_default_config()
    default_model = defaults.get('model', {})
    primary = model_cfg.get('primary') or default_model.get('primary') or ''
    fallbacks = model_cfg.get('fallbacks') or default_model.get('fallbacks') or []
    return {'primary': primary, 'fallbacks': fallbacks}


def get_models_configured_by_agents() -> List[str]:
    """
    从配置中收集「各 Agent 实际配置使用」的模型 ID（仅 primary + fallbacks）。
    用于协作流程右侧模型面板：只显示有 Agent 配置的模型，不含白名单中未使用的。
    """
    agents = get_agents_list()
    model_ids = set()
    defaults = get_default_config()
    default_model = defaults.get('model', {})
    if default_model.get('primary'):
        model_ids.add(default_model['primary'])
    for fb in default_model.get('fallbacks') or []:
        model_ids.add(fb)
    for agent in agents:
        cfg = get_agent_models(agent.get('id', ''))
        if cfg.get('primary'):
            model_ids.add(cfg['primary'])
        for fb in cfg.get('fallbacks', []):
            model_ids.add(fb)
    return sorted(model_ids)


def get_all_models_from_agents() -> List[str]:
    """
    从配置中收集模型 ID（provider/model 格式），用于无 models.providers 时的下拉选项。
    来源（合并去重）：
    1. 各 Agent 实际配置（primary + fallbacks）
    2. agents.defaults.models（白名单 key，确保配置过的能选）
    """
    model_ids = set(get_models_configured_by_agents())
    defaults = get_default_config()
    models_cfg = defaults.get('models', {}) or {}
    if isinstance(models_cfg, dict):
        for mid in models_cfg.keys():
            if mid and isinstance(mid, str):
                model_ids.add(mid)
    return sorted(model_ids)


def get_model_display_name(model_id: str) -> str:
    """获取模型显示名。展示策略：使用 id 不用别名（与 OpenClaw 白名单逻辑一致）"""
    if not model_id:
        return ''
    parts = model_id.split('/')
    return parts[-1] if len(parts) > 1 else model_id
