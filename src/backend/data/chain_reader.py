"""
任务链路读取器 - 解析 Agent 间的任务派发关系
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime


class ChainNodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


class ChainStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


from data.config_reader import get_openclaw_root


def _get_agents_config() -> Dict[str, Any]:
    """获取 agents 配置"""
    config_file = get_openclaw_root() / "openclaw.json"
    if not config_file.exists():
        return {}

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}


def _get_agent_info(agent_id: str) -> Dict[str, Any]:
    """获取单个 agent 的信息"""
    config = _get_agents_config()
    agents = config.get('agents', {}).get('list', [])
    for a in agents:
        if a.get('id') == agent_id:
            return a
    return {}


def _parse_session_key(session_key: str) -> Dict[str, str]:
    """解析 session key，提取 agent_id 等信息"""
    # 格式: agent:agent-id:subagent:uuid 或 agent:agent-id:main
    parts = session_key.split(':')
    result = {'type': parts[0] if len(parts) > 0 else 'unknown'}

    if len(parts) >= 2:
        result['agent_id'] = parts[1]
    if len(parts) >= 3:
        result['session_type'] = parts[2]  # main 或 subagent
    if len(parts) >= 4:
        result['uuid'] = parts[3]

    return result


def _load_runs() -> Dict[str, Any]:
    """加载 runs.json"""
    runs_file = get_openclaw_root() / "subagents" / "runs.json"
    if not runs_file.exists():
        return {"version": 2, "runs": {}}

    try:
        with open(runs_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"version": 2, "runs": {}}


def _get_workflow_state(project_id: str) -> Dict[str, Any]:
    """获取项目的 workflow 状态"""
    # 尝试多个可能的项目路径
    possible_paths = [
        get_openclaw_root() / f"workspace-{project_id}" / ".staging" / "workflow_state.json",
        Path.home() / "vrt-projects" / "projects" / project_id / ".staging" / "workflow_state.json",
    ]

    for path in possible_paths:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass

    return {}


def build_task_chains(limit: int = 20) -> List[Dict[str, Any]]:
    """
    构建任务链路列表

    通过解析 runs.json 中的派发关系，构建完整的任务执行链路
    """
    runs_data = _load_runs()
    runs = runs_data.get('runs', {})

    if not runs:
        return []

    # 按 requesterSessionKey 分组，构建链路
    chains_map: Dict[str, Dict[str, Any]] = {}

    for run_id, run_info in runs.items():
        if not isinstance(run_info, dict):
            continue

        requester_key = run_info.get('requesterSessionKey', '')
        child_key = run_info.get('childSessionKey', '')

        if not requester_key or not child_key:
            continue

        # 解析 requester 和 child
        requester = _parse_session_key(requester_key)
        child = _parse_session_key(child_key)

        requester_id = requester.get('agent_id', 'main')
        child_id = child.get('agent_id', 'unknown')

        # 使用 requester 的 session 作为链路 ID（简化处理）
        chain_id = requester_key.split(':subagent:')[0] if ':subagent:' in requester_key else requester_key

        if chain_id not in chains_map:
            chains_map[chain_id] = {
                'chainId': chain_id,
                'rootTask': '',
                'startedAt': None,
                'status': ChainStatus.RUNNING.value,
                'nodes': {},
                'edges': [],
                'projectId': None
            }

        chain = chains_map[chain_id]

        # 添加 requester 节点（如果不存在）
        if requester_id not in chain['nodes']:
            agent_info = _get_agent_info(requester_id)
            chain['nodes'][requester_id] = {
                'agentId': requester_id,
                'agentName': agent_info.get('name', requester_id),
                'role': requester_id.split('-')[0] if '-' in requester_id else requester_id,
                'status': ChainNodeStatus.COMPLETED.value,
                'startedAt': None,
                'endedAt': None,
                'duration': None,
                'task': None,
                'runId': None,
                'input': None,
                'output': None,
                'artifacts': [],
                'toolCallCount': 0,
                'tokenUsage': {'input': 0, 'output': 0}
            }

        # 添加子节点
        agent_info = _get_agent_info(child_id)
        started_at = run_info.get('startedAt')
        ended_at = run_info.get('endedAt')

        node_status = ChainNodeStatus.PENDING.value
        if started_at and ended_at:
            node_status = ChainNodeStatus.COMPLETED.value if run_info.get('outcome') == 'ok' else ChainNodeStatus.ERROR.value
        elif started_at:
            node_status = ChainNodeStatus.RUNNING.value

        chain['nodes'][child_id] = {
            'agentId': child_id,
            'agentName': agent_info.get('name', child_id),
            'role': child_id.split('-')[0] if '-' in child_id else child_id,
            'status': node_status,
            'startedAt': started_at,
            'endedAt': ended_at,
            'duration': (ended_at - started_at) if started_at and ended_at else None,
            'task': run_info.get('task', ''),
            'runId': run_id,
            'input': None,
            'output': None,
            'artifacts': [],
            'toolCallCount': 0,
            'tokenUsage': {'input': 0, 'output': 0}
        }

        # 添加边
        edge = {'from': requester_id, 'to': child_id}
        if edge not in chain['edges']:
            chain['edges'].append(edge)

        # 更新链路开始时间
        if started_at:
            if chain['startedAt'] is None or started_at < chain['startedAt']:
                chain['startedAt'] = started_at

        # 设置根任务（使用第一个子节点的任务）
        if not chain['rootTask'] and run_info.get('task'):
            chain['rootTask'] = run_info.get('task')

        # 保存 archiveAtMs（用于超时倒计时）
        if run_info.get('archiveAtMs') and not chain.get('archiveAtMs'):
            chain['archiveAtMs'] = run_info.get('archiveAtMs')

    # 转换节点为列表并计算统计信息
    chains = []
    for chain_id, chain in chains_map.items():
        nodes_list = list(chain['nodes'].values())

        # 计算进度
        completed = sum(1 for n in nodes_list if n['status'] == ChainNodeStatus.COMPLETED.value)
        running = sum(1 for n in nodes_list if n['status'] == ChainNodeStatus.RUNNING.value)
        total = len(nodes_list)

        progress = completed / total if total > 0 else 0

        # 计算总耗时
        total_duration = sum(n['duration'] or 0 for n in nodes_list)

        # 确定链路状态
        if any(n['status'] == ChainNodeStatus.ERROR.value for n in nodes_list):
            chain_status = ChainStatus.ERROR.value
        elif running > 0:
            chain_status = ChainStatus.RUNNING.value
        else:
            chain_status = ChainStatus.COMPLETED.value

        chains.append({
            'chainId': chain_id,
            'projectId': chain.get('projectId'),
            'rootTask': chain.get('rootTask', '未知任务'),
            'startedAt': chain.get('startedAt'),
            'archiveAtMs': chain.get('archiveAtMs'),
            'status': chain_status,
            'nodes': nodes_list,
            'edges': chain['edges'],
            'progress': progress,
            'completedNodes': completed,
            'totalNodes': total,
            'totalDuration': total_duration
        })

    # 按开始时间排序
    chains.sort(key=lambda x: x.get('startedAt') or 0, reverse=True)

    return chains[:limit]


def get_task_chain(chain_id: str) -> Optional[Dict[str, Any]]:
    """获取单个任务链的详情"""
    chains = build_task_chains(limit=100)
    for chain in chains:
        if chain['chainId'] == chain_id:
            return chain
    return None


def get_active_chain() -> Optional[Dict[str, Any]]:
    """获取当前活跃的任务链（正在执行的）"""
    chains = build_task_chains(limit=50)
    for chain in chains:
        if chain['status'] == ChainStatus.RUNNING.value:
            return chain
    return None


def get_chains_summary() -> Dict[str, Any]:
    """获取任务链摘要统计"""
    chains = build_task_chains(limit=100)

    running = sum(1 for c in chains if c['status'] == ChainStatus.RUNNING.value)
    completed = sum(1 for c in chains if c['status'] == ChainStatus.COMPLETED.value)
    error = sum(1 for c in chains if c['status'] == ChainStatus.ERROR.value)

    return {
        'total': len(chains),
        'running': running,
        'completed': completed,
        'error': error,
        'chains': [
            {
                'chainId': c['chainId'],
                'rootTask': c['rootTask'][:50] + '...' if len(c['rootTask']) > 50 else c['rootTask'],
                'status': c['status'],
                'progress': c['progress'],
                'startedAt': c['startedAt']
            }
            for c in chains[:10]
        ]
    }
