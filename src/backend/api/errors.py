"""
错误中心 API - 聚合 Session 错误、Model Failures、API 状态
支持统计、筛选、趋势分析
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import sys
from pathlib import Path
import time
from collections import defaultdict

sys.path.append(str(Path(__file__).parent.parent))

from core.error_handler import get_framework_error_stats_for_client, record_error
from core.safe_api_error import safe_api_error_detail

router = APIRouter()


# 错误类型映射
ERROR_TYPE_MAP = {
    'rate-limit': {'label': 'Rate Limit', 'color': '#f59e0b', 'severity': 'warning'},
    'token-limit': {'label': 'Token 超限', 'color': '#8b5cf6', 'severity': 'warning'},
    'timeout': {'label': '超时', 'color': '#ef4444', 'severity': 'error'},
    'auth': {'label': '认证失败', 'color': '#dc2626', 'severity': 'critical'},
    'unknown': {'label': '未知错误', 'color': '#6b7280', 'severity': 'error'},
}


def classify_error(err_msg: str) -> str:
    """更精细的错误分类"""
    err_lower = err_msg.lower()

    if '429' in err_msg or 'rate limit' in err_lower or 'too many requests' in err_lower:
        return 'rate-limit'
    elif 'token' in err_lower or 'context' in err_lower or 'length' in err_lower:
        return 'token-limit'
    elif 'timeout' in err_lower or '超时' in err_msg or 'timed out' in err_lower:
        return 'timeout'
    elif '401' in err_msg or '403' in err_msg or 'auth' in err_lower or 'unauthorized' in err_lower:
        return 'auth'
    else:
        return 'unknown'


def get_session_errors(limit: int = 100, agent_filter: str = None, type_filter: str = None) -> List[Dict]:
    """获取 Session 错误"""
    from data.session_reader import get_recent_messages
    from data.config_reader import get_agents_list

    errors = []
    agents = get_agents_list()

    for agent in agents:
        agent_id = agent.get('id', '')
        if not agent_id:
            continue
        if agent_filter and agent_id != agent_filter:
            continue

        messages = get_recent_messages(agent_id, limit=200)
        for msg in messages:
            if msg.get('stopReason') != 'error':
                continue

            err_msg = msg.get('errorMessage', '') or ''
            err_type = classify_error(err_msg)

            if type_filter and err_type != type_filter:
                continue

            errors.append({
                "id": f"session-{agent_id}-{msg.get('timestamp', 0)}",
                "source": "session",
                "agentId": agent_id,
                "type": err_type,
                "typeLabel": ERROR_TYPE_MAP.get(err_type, {}).get('label', err_type),
                "severity": ERROR_TYPE_MAP.get(err_type, {}).get('severity', 'error'),
                "message": err_msg[:300] if err_msg else "(无详情)",
                "fullMessage": err_msg,
                "timestamp": msg.get('timestamp', 0),
                "datetime": datetime.fromtimestamp(msg.get('timestamp', 0) / 1000).strftime('%Y-%m-%d %H:%M:%S') if msg.get('timestamp') else '-',
            })

    errors.sort(key=lambda x: x["timestamp"], reverse=True)
    return errors[:limit]


def get_model_failures(limit: int = 100, model_filter: str = None, type_filter: str = None) -> List[Dict]:
    """获取 Model Failures"""
    from status.error_detector import parse_failure_log

    errors = []
    failures = parse_failure_log()

    for f in failures:
        model = f.get("model", "")
        if model_filter and model != model_filter:
            continue

        err_type = f.get("error_type", "unknown")
        if type_filter and err_type != type_filter:
            continue

        timestamp = f.get("timestamp", 0)
        errors.append({
            "id": f"model-{timestamp}-{model}",
            "source": "model",
            "model": model,
            "type": err_type,
            "typeLabel": ERROR_TYPE_MAP.get(err_type, {}).get('label', err_type),
            "severity": ERROR_TYPE_MAP.get(err_type, {}).get('severity', 'error'),
            "message": (f.get("message", "") or "")[:300],
            "fullMessage": f.get("message", "") or "",
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S') if timestamp else '-',
        })

    return errors[:limit]


def get_api_status() -> List[Dict]:
    """获取 API 状态（整合自原 api_status 模块）"""
    from status.error_detector import parse_failure_log

    failures = parse_failure_log()
    status_map = {}
    now = int(time.time() * 1000)

    for failure in failures:
        model = failure.get('model', '')
        if not model:
            continue

        if model not in status_map:
            status_map[model] = {
                'model': model,
                'provider': parse_provider(model),
                'status': 'healthy',
                'errorCount': 0,
                'lastError': None,
            }

        status_map[model]['errorCount'] += 1

        # 最近 10 分钟内有错误
        if failure['timestamp'] > now - 600000:
            if failure['timestamp'] > now - 120000:  # 2分钟内
                status_map[model]['status'] = 'down'
            else:
                status_map[model]['status'] = 'degraded'

            if not status_map[model]['lastError']:
                status_map[model]['lastError'] = {
                    'type': failure.get('error_type', 'unknown'),
                    'message': (failure.get('message', '') or '')[:100],
                    'timestamp': failure['timestamp'],
                }

    return list(status_map.values())


def parse_provider(model: str) -> str:
    """从模型名解析服务商"""
    if model.startswith('glm'):
        return 'zhipu'
    elif model.startswith('qwen'):
        return 'qwen'
    elif model.startswith('kimi'):
        return 'moonshot'
    elif model.startswith('claude'):
        return 'anthropic'
    elif model.startswith('gpt'):
        return 'openai'
    else:
        return 'unknown'


def get_error_stats(session_errors: List, model_failures: List) -> Dict:
    """计算错误统计"""
    # 按类型统计
    type_stats = defaultdict(lambda: {'count': 0, 'label': '', 'color': ''})
    for e in session_errors + model_failures:
        err_type = e.get('type', 'unknown')
        type_stats[err_type]['count'] += 1
        type_stats[err_type]['label'] = ERROR_TYPE_MAP.get(err_type, {}).get('label', err_type)
        type_stats[err_type]['color'] = ERROR_TYPE_MAP.get(err_type, {}).get('color', '#6b7280')

    # 按 Agent 统计
    agent_stats = defaultdict(lambda: {'count': 0, 'agentId': ''})
    for e in session_errors:
        agent_id = e.get('agentId', 'unknown')
        agent_stats[agent_id]['count'] += 1
        agent_stats[agent_id]['agentId'] = agent_id

    # 按小时统计（最近 24 小时）
    hourly_stats = defaultdict(int)
    now = datetime.now()
    for e in session_errors + model_failures:
        ts = e.get('timestamp', 0)
        if ts:
            dt = datetime.fromtimestamp(ts / 1000)
            if dt > now - timedelta(hours=24):
                hour_key = dt.strftime('%Y-%m-%d %H:00')
                hourly_stats[hour_key] += 1

    # 生成完整的小时序列
    hourly_list = []
    for i in range(24):
        hour = (now - timedelta(hours=23-i)).strftime('%Y-%m-%d %H:00')
        hourly_list.append({
            'hour': hour,
            'count': hourly_stats.get(hour, 0)
        })

    return {
        'totalCount': len(session_errors) + len(model_failures),
        'sessionErrorCount': len(session_errors),
        'modelFailureCount': len(model_failures),
        'byType': dict(type_stats),
        'byAgent': dict(agent_stats),
        'hourlyTrend': hourly_list,
    }


@router.get("/errors")
async def get_errors(
    limit: int = Query(50, ge=1, le=500),
    agent: Optional[str] = Query(None, description="按 Agent ID 筛选"),
    type: Optional[str] = Query(None, description="按错误类型筛选"),
    model: Optional[str] = Query(None, description="按模型筛选"),
):
    """
    获取错误中心数据
    支持按 Agent、类型、模型筛选
    """
    try:
        session_errors = get_session_errors(limit, agent, type)
        model_failures = get_model_failures(limit, model, type)
    except Exception as e:
        record_error("unknown", str(e), "api:errors:list", exc=e)
        raise HTTPException(status_code=500, detail=safe_api_error_detail(e)) from e

    return {
        "sessionErrors": session_errors,
        "modelFailures": model_failures,
    }


@router.get("/errors/stats")
async def get_errors_stats():
    """
    获取错误统计数据
    包括：总数、按类型分布、按 Agent 分布、时间趋势
    """
    try:
        session_errors = get_session_errors(200)
        model_failures = get_model_failures(200)
        out = get_error_stats(session_errors, model_failures)
        out["framework"] = get_framework_error_stats_for_client()
        return out
    except Exception as e:
        record_error("unknown", str(e), "api:errors:stats", exc=e)
        raise HTTPException(status_code=500, detail=safe_api_error_detail(e)) from e


@router.get("/errors/api-status")
async def get_errors_api_status():
    """
    获取 API 状态
    整合自原 api_status 模块
    """
    return get_api_status()


@router.get("/errors/summary")
async def get_errors_summary():
    """
    获取错误中心完整数据（一次请求获取所有）
    包括：错误列表、统计、API 状态
    """
    try:
        session_errors = get_session_errors(100)
        model_failures = get_model_failures(100)
        api_status = get_api_status()
        stats = get_error_stats(session_errors, model_failures)
    except Exception as e:
        record_error("unknown", str(e), "api:errors:summary", exc=e)
        raise HTTPException(status_code=500, detail=safe_api_error_detail(e)) from e

    return {
        "sessionErrors": session_errors,
        "modelFailures": model_failures,
        "apiStatus": api_status,
        "stats": stats,
    }
