"""
机制追踪读取器 - 从 sessions.json 提取 Memory/Skill/Channel/Heartbeat/Cron 使用情况
"""
import json
from pathlib import Path
from typing import Dict, Any, List


from data.config_reader import get_openclaw_root
from data.session_reader import normalize_sessions_index


def get_agent_mechanisms(agent_id: str) -> Dict[str, Any]:
    """
    获取 Agent 使用的机制：Memory、Skill、Channel、Heartbeat、Cron
    数据来源：sessions.json 的 systemPromptReport、origin、deliveryContext
    """
    sessions_index = get_openclaw_root() / "agents" / agent_id / "sessions" / "sessions.json"
    result = {
        "agentId": agent_id,
        "memory": [],
        "skills": [],
        "channel": None,
        "heartbeat": None,
        "cron": None,
    }
    
    if not sessions_index.exists():
        return result
    
    try:
        with open(sessions_index, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return result
        
        # 取最新 session 的机制信息（兼容 sessions.json 顶层或 entries 嵌套）
        index_map = normalize_sessions_index(data)
        for session_key, entry in index_map.items():
            if not isinstance(entry, dict):
                continue
            report = entry.get('systemPromptReport', {})
            if isinstance(report, dict):
                # Memory: injectedWorkspaceFiles 中含 MEMORY.md、memory/
                injected = report.get('injectedWorkspaceFiles', [])
                for f in injected:
                    if not isinstance(f, dict):
                        continue
                    name = f.get('name', '')
                    path = f.get('path', '')
                    if 'MEMORY.md' in name or 'memory' in name:
                        result["memory"].append({
                            "name": name,
                            "path": path,
                            "missing": f.get('missing', False),
                        })
                # 去重
                seen = set()
                unique = []
                for m in result["memory"]:
                    k = m.get("path", "")
                    if k and k not in seen:
                        seen.add(k)
                        unique.append(m)
                result["memory"] = unique
                
                # Skills: systemPromptReport.skills.entries 或 skillsSnapshot.resolvedSkills
                skills_data = report.get('skills', {})
                if isinstance(skills_data, dict):
                    entries = skills_data.get('entries', [])
                    for s in entries:
                        if isinstance(s, dict) and s.get('name'):
                            result["skills"].append({
                                "name": s.get('name'),
                                "blockChars": s.get('blockChars'),
                            })
                if not result["skills"]:
                    snapshot = entry.get('skillsSnapshot', {})
                    resolved = snapshot.get('resolvedSkills', [])
                    for s in resolved:
                        if isinstance(s, dict) and s.get('name'):
                            result["skills"].append({
                                "name": s.get('name'),
                                "filePath": s.get('filePath'),
                                "baseDir": s.get('baseDir'),
                            })
            
            # Channel: origin.channel / deliveryContext.channel / lastChannel
            channel = (
                entry.get('lastChannel') or
                entry.get('deliveryContext', {}).get('channel') if isinstance(entry.get('deliveryContext'), dict) else None or
                entry.get('origin', {}).get('provider') if isinstance(entry.get('origin'), dict) else None
            )
            if channel and not result["channel"]:
                result["channel"] = channel
            
            # 只取第一个有效 session
            if result["channel"] or result["memory"] or result["skills"]:
                break
        
        # Heartbeat/Cron: 从 openclaw.json 读取配置
        config_path = get_openclaw_root() / "openclaw.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            defaults = config.get('agents', {}).get('defaults', {})
            hb = defaults.get('heartbeat', {})
            if hb:
                result["heartbeat"] = {
                    "every": hb.get('every'),
                    "enabled": hb.get('every') is not None,
                }
        
        cron_path = get_openclaw_root() / "cron" / "jobs.json"
        if cron_path.exists():
            with open(cron_path, 'r', encoding='utf-8') as f:
                cron_data = json.load(f)
            jobs = cron_data.get('jobs', [])
            if isinstance(jobs, dict):
                jobs = list(jobs.values())
            result["cron"] = {"count": len(jobs), "jobs": jobs[:10]}
        
    except (json.JSONDecodeError, IOError) as e:
        result["error"] = str(e)
    
    return result


def get_all_agents_mechanisms() -> List[Dict[str, Any]]:
    """获取所有 Agent 的机制使用情况"""
    from .config_reader import get_agents_list
    agents = get_agents_list()
    return [get_agent_mechanisms(a.get('id', '')) for a in agents if a.get('id')]
