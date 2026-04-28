"""
Agent 配置 API - 直接从 openclaw.json 读取
仅依赖 config_reader，无其他模块依赖，作为协作流程的兜底数据源
"""
from fastapi import APIRouter
from typing import List, Dict, Any

from core.error_handler import record_error
from core.safe_api_error import safe_client_string

router = APIRouter()


@router.get("/agents-config")
async def get_agents_config():
    """
    直接从 ~/.openclaw/openclaw.json 读取 agents.list
    返回格式与协作流程兼容，用于 API 失败时的兜底展示
    """
    try:
        from data.config_reader import (
            get_agents_list,
            get_main_agent_id,
            get_agent_models,
        )
        agents_list = get_agents_list()
        main_id = get_main_agent_id()
        agent_models: Dict[str, Dict[str, Any]] = {}
        for a in agents_list:
            aid = a.get('id', '')
            if aid:
                agent_models[aid] = get_agent_models(aid)

        nodes = []
        edges = []
        for agent in agents_list:
            aid = agent.get('id', '')
            if not aid:
                continue
            name = agent.get('name', aid)
            nodes.append({
                'id': aid,
                'type': 'agent',
                'name': name,
                'status': 'idle',
                'metadata': agent_models.get(aid),
            })
            if aid != main_id:
                edges.append({
                    'id': f'edge-{main_id}-{aid}',
                    'source': main_id,
                    'target': aid,
                    'type': 'delegates',
                    'label': '委托',
                })

        return {
            'nodes': nodes,
            'edges': edges,
            'activePath': [],
            'mainAgentId': main_id,
            'agentModels': agent_models,
            'models': [],
            'recentCalls': [],
            'lastUpdate': int(__import__('time').time() * 1000),
        }
    except Exception as e:
        record_error("unknown", str(e), "api:agents_config:get", exc=e)
        return {
            'nodes': [],
            'edges': [],
            'activePath': [],
            'mainAgentId': 'main',
            'agentModels': {},
            'models': [],
            'recentCalls': [],
            'lastUpdate': 0,
            '_error': safe_client_string(str(e)),
        }
