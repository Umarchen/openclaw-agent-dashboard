"""
错误分析 API - 提供错误根因分析接口
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from data.error_analyzer import (
    analyze_agent_errors,
    analyze_all_agents_errors,
    get_error_detail,
    classify_error,
    get_error_suggestions,
)

router = APIRouter()


def format_error_for_display(error: dict) -> dict:
    """格式化错误信息用于前端展示"""
    severity_colors = {
        'critical': '#dc2626',
        'high': '#f97316',
        'medium': '#fbbf24',
        'low': '#6b7280',
    }

    severity_labels = {
        'critical': '严重',
        'high': '高',
        'medium': '中',
        'low': '低',
    }

    type_labels = {
        'api_auth': 'API 认证错误',
        'api_rate_limit': 'API 限流',
        'api_model': '模型错误',
        'timeout': '超时',
        'permission': '权限错误',
        'tool_error': '工具错误',
        'subagent': '子任务错误',
        'network': '网络错误',
        'unknown': '未知错误',
    }

    error_type = error.get('errorType', 'unknown')
    severity = error.get('severity', 'medium')

    return {
        **error,
        'errorTypeLabel': type_labels.get(error_type, error_type),
        'severityLabel': severity_labels.get(severity, severity),
        'severityColor': severity_colors.get(severity, '#6b7280'),
    }


@router.get("/error-analysis")
async def get_global_error_analysis():
    """
    获取所有 Agent 的错误分析概览

    返回全局错误统计和每个 Agent 的错误摘要
    """
    try:
        result = analyze_all_agents_errors()

        # 格式化错误信息
        for agent_result in result.get('agents', []):
            agent_result['errors'] = [
                format_error_for_display(e)
                for e in agent_result.get('errors', [])
            ]

        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'agents': [],
            'globalSummary': {},
            'error': str(e),
        }


@router.get("/error-analysis/{agent_id}")
async def get_agent_error_analysis(agent_id: str, session_limit: int = 5):
    """
    获取单个 Agent 的错误分析

    - agent_id: Agent ID
    - session_limit: 分析最近的 N 个 session
    """
    try:
        result = analyze_agent_errors(agent_id, session_limit)
        result['errors'] = [
            format_error_for_display(e)
            for e in result.get('errors', [])
        ]
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/error-analysis/{agent_id}/{session_file}/{turn_index}")
async def get_error_detail_api(agent_id: str, session_file: str, turn_index: int):
    """
    获取单个错误的详细信息

    包括错误发生前的工具调用链
    """
    try:
        error = get_error_detail(agent_id, session_file, turn_index)
        if not error:
            raise HTTPException(status_code=404, detail="Error not found")
        return format_error_for_display(error)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/error-analysis/classify")
async def classify_error_message(message: str):
    """
    对给定的错误消息进行分类

    返回错误类型、严重程度和修复建议
    """
    try:
        error_type, severity = classify_error(message)
        suggestions = get_error_suggestions(error_type, message)

        return {
            'message': message,
            'errorType': error_type.value,
            'severity': severity.value,
            'suggestions': suggestions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
