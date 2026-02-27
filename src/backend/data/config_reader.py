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
