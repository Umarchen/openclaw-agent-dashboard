"""
错误中心 API - 聚合 stopReason=error 与 model-failures.log
"""
from fastapi import APIRouter
from typing import List, Dict, Any
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

router = APIRouter()


@router.get("/errors")
async def get_errors(limit: int = 50):
    """
    获取错误中心数据：聚合各 Agent 的 session 错误与 model-failures.log
    """
    from data.session_reader import get_recent_messages
    from data.config_reader import get_agents_list
    from status.error_detector import parse_failure_log
    
    result = {"sessionErrors": [], "modelFailures": []}
    
    # 1. Session 错误：遍历各 Agent 的 jsonl，找 stopReason=error
    agents = get_agents_list()
    for agent in agents:
        agent_id = agent.get('id', '')
        if not agent_id:
            continue
        messages = get_recent_messages(agent_id, limit=100)
        for msg in messages:
            if msg.get('stopReason') != 'error':
                continue
            err_type = 'unknown'
            err_msg = msg.get('errorMessage', '') or ''
            if '429' in err_msg or 'rate limit' in err_msg.lower():
                err_type = 'rate-limit'
            elif 'token' in err_msg.lower() or 'context' in err_msg.lower():
                err_type = 'token-limit'
            elif 'timeout' in err_msg.lower() or '超时' in err_msg:
                err_type = 'timeout'
            result["sessionErrors"].append({
                "agentId": agent_id,
                "type": err_type,
                "message": err_msg[:200] if err_msg else "(无详情)",
                "timestamp": msg.get('timestamp', 0),
            })
    
    result["sessionErrors"].sort(key=lambda x: x["timestamp"], reverse=True)
    result["sessionErrors"] = result["sessionErrors"][:limit]
    
    # 2. Model failures log
    failures = parse_failure_log()
    for f in failures[:limit]:
        result["modelFailures"].append({
            "model": f.get("model", ""),
            "errorType": f.get("error_type", ""),
            "message": (f.get("message", "") or "")[:200],
            "timestamp": f.get("timestamp", 0),
        })
    
    return result
