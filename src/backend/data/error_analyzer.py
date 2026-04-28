"""
错误分析器 - 分析 Agent 执行错误，追溯根因
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum


class ErrorType(Enum):
    """错误类型分类"""
    API_AUTH = "api_auth"              # API 认证错误
    API_RATE_LIMIT = "api_rate_limit"  # API 限流
    API_MODEL_ERROR = "api_model"      # 模型错误
    TIMEOUT = "timeout"                # 超时
    PERMISSION = "permission"          # 权限错误
    TOOL_ERROR = "tool_error"          # 工具调用错误
    SUBAGENT_ERROR = "subagent"        # 子任务错误
    NETWORK = "network"                # 网络错误
    UNKNOWN = "unknown"                # 未知错误


class ErrorSeverity(Enum):
    """错误严重程度"""
    CRITICAL = "critical"  # 致命错误，任务无法继续
    HIGH = "high"          # 严重错误，需要干预
    MEDIUM = "medium"      # 中等错误，可恢复
    LOW = "low"            # 轻微错误，可忽略


from data.config_reader import get_openclaw_root, normalize_openclaw_agent_id
from utils.data_repair import parse_session_jsonl_line


# 错误模式匹配规则
ERROR_PATTERNS = [
    # API 认证错误
    (ErrorType.API_AUTH, ErrorSeverity.CRITICAL, [
        r"invalid.*api.*key",
        r"authentication.*failed",
        r"unauthorized",
        r"api.*key.*invalid",
        r"401",
        r"invalid.*token",
    ]),
    # API 限流
    (ErrorType.API_RATE_LIMIT, ErrorSeverity.HIGH, [
        r"rate.*limit",
        r"too.*many.*requests",
        r"quota.*exceeded",
        r"429",
        r"throttl",
    ]),
    # 模型错误
    (ErrorType.API_MODEL_ERROR, ErrorSeverity.HIGH, [
        r"model.*not.*found",
        r"model.*unavailable",
        r"invalid.*model",
        r"model.*overloaded",
        r"context.*length.*exceed",
        r"max.*tokens",
    ]),
    # 超时
    (ErrorType.TIMEOUT, ErrorSeverity.MEDIUM, [
        r"timeout",
        r"timed.*out",
        r"deadline.*exceeded",
        r"execution.*timeout",
    ]),
    # 权限错误
    (ErrorType.PERMISSION, ErrorSeverity.HIGH, [
        r"permission.*denied",
        r"access.*denied",
        r"forbidden",
        r"not.*authorized",
        r"403",
        r"EACCES",
        r"EPERM",
    ]),
    # 网络错误
    (ErrorType.NETWORK, ErrorSeverity.MEDIUM, [
        r"connection.*refused",
        r"network.*error",
        r"ENOTFOUND",
        r"ECONNREFUSED",
        r"ETIMEDOUT",
        r"socket.*hang.*up",
        r"fetch.*failed",
    ]),
    # 子任务错误
    (ErrorType.SUBAGENT_ERROR, ErrorSeverity.HIGH, [
        r"subagent.*error",
        r"subagent.*failed",
        r"child.*session.*error",
        r"spawn.*failed",
        r"agent.*failed",
    ]),
    # 工具错误
    (ErrorType.TOOL_ERROR, ErrorSeverity.MEDIUM, [
        r"tool.*error",
        r"tool.*failed",
        r"command.*failed",
        r"execution.*failed",
        r"invalid.*argument",
    ]),
]


def classify_error(error_message: str) -> Tuple[ErrorType, ErrorSeverity]:
    """根据错误消息分类错误类型和严重程度"""
    if not error_message:
        return ErrorType.UNKNOWN, ErrorSeverity.MEDIUM

    error_lower = error_message.lower()

    for error_type, severity, patterns in ERROR_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, error_lower, re.IGNORECASE):
                return error_type, severity

    return ErrorType.UNKNOWN, ErrorSeverity.MEDIUM


def get_error_suggestions(error_type: ErrorType, error_message: str) -> List[str]:
    """根据错误类型提供修复建议"""
    suggestions = {
        ErrorType.API_AUTH: [
            "检查 API Key 是否正确配置",
            "确认 API Key 是否过期",
            "检查环境变量中的 API Key 设置",
        ],
        ErrorType.API_RATE_LIMIT: [
            "等待一段时间后重试",
            "检查 API 配额使用情况",
            "考虑降低请求频率",
            "升级 API 套餐获取更高配额",
        ],
        ErrorType.API_MODEL_ERROR: [
            "检查模型 ID 是否正确",
            "确认该模型在当前套餐中可用",
            "尝试使用其他模型",
            "检查 context window 是否超出限制",
        ],
        ErrorType.TIMEOUT: [
            "检查网络连接稳定性",
            "尝试减小请求内容长度",
            "考虑增加超时时间设置",
        ],
        ErrorType.PERMISSION: [
            "检查文件/目录权限",
            "确认当前用户有执行权限",
            "检查是否需要 sudo 权限",
        ],
        ErrorType.NETWORK: [
            "检查网络连接",
            "确认 API 服务是否可用",
            "检查代理设置",
            "尝试使用其他网络",
        ],
        ErrorType.SUBAGENT_ERROR: [
            "查看子 Agent 的详细错误日志",
            "检查子任务的任务描述是否清晰",
            "确认子 Agent 配置正确",
        ],
        ErrorType.TOOL_ERROR: [
            "检查工具参数是否正确",
            "查看工具的详细错误输出",
            "确认相关依赖已安装",
        ],
        ErrorType.UNKNOWN: [
            "查看详细日志获取更多信息",
            "尝试重新执行任务",
            "如果问题持续，请联系支持",
        ],
    }
    return suggestions.get(error_type, suggestions[ErrorType.UNKNOWN])


def parse_session_for_errors(session_path: Path) -> List[Dict[str, Any]]:
    """解析 session 文件，提取错误信息"""
    errors = []

    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            turn_index = 0
            for line in f:
                try:
                    envelope, msg = parse_session_jsonl_line(line)
                    if (
                        envelope is None
                        or envelope.get('type') != 'message'
                        or msg is None
                    ):
                        continue
                    role = msg.get('role')
                    timestamp = msg.get('timestamp')
                    stop_reason = msg.get('stopReason')

                    # 检查 stopReason 为 error
                    if stop_reason == 'error':
                        # 优先从 errorMessage 字段获取
                        error_text = msg.get('errorMessage', '')

                        # 如果没有 errorMessage，从 content 中提取
                        if not error_text:
                            content = msg.get('content', [])
                            for c in content:
                                if isinstance(c, dict):
                                    if c.get('type') == 'text':
                                        error_text += c.get('text', '') + ' '

                        # 提取更多上下文
                        provider = msg.get('provider', '')
                        model = msg.get('model', '')

                        error_type, severity = classify_error(error_text)
                        suggestions = get_error_suggestions(error_type, error_text)

                        errors.append({
                            'turnIndex': turn_index,
                            'timestamp': timestamp,
                            'role': role,
                            'stopReason': stop_reason,
                            'rawMessage': error_text[:500],
                            'errorType': error_type.value,
                            'severity': severity.value,
                            'suggestions': suggestions,
                            'provider': provider,
                            'model': model,
                        })

                    # 检查 toolResult 中的错误
                    if role == 'user':
                        content = msg.get('content', [])
                        for c in content:
                            if isinstance(c, dict) and c.get('type') == 'toolResult':
                                if c.get('isError') or c.get('error'):
                                    error_text = c.get('error', '') or str(c.get('content', ''))[:500]
                                    tool_name = c.get('toolName', 'unknown')
                                    error_type, severity = classify_error(error_text)
                                    suggestions = get_error_suggestions(error_type, error_text)

                                    errors.append({
                                        'turnIndex': turn_index,
                                        'timestamp': timestamp,
                                        'role': 'toolResult',
                                        'toolName': tool_name,
                                        'stopReason': 'tool_error',
                                        'rawMessage': error_text,
                                        'errorType': error_type.value,
                                        'severity': severity.value,
                                        'suggestions': suggestions,
                                    })

                    turn_index += 1

                except (KeyError, TypeError, AttributeError):
                    continue

    except Exception as e:
        errors.append({
            'error': f'Failed to parse session: {str(e)}',
            'errorType': ErrorType.UNKNOWN.value,
            'severity': ErrorSeverity.LOW.value,
        })

    return errors


def get_tool_call_chain(session_path: Path, before_turn: int, limit: int = 10) -> List[Dict[str, Any]]:
    """获取错误发生前的工具调用链"""
    chain = []

    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            turn_index = 0
            for line in f:
                try:
                    if turn_index >= before_turn:
                        break

                    envelope, msg = parse_session_jsonl_line(line)
                    if (
                        envelope is None
                        or envelope.get('type') != 'message'
                        or msg is None
                    ):
                        continue
                    role = msg.get('role')
                    timestamp = msg.get('timestamp')

                    if role == 'assistant':
                        content = msg.get('content', [])
                        for c in content:
                            if isinstance(c, dict) and c.get('type') == 'toolCall':
                                chain.append({
                                    'turnIndex': turn_index,
                                    'timestamp': timestamp,
                                    'toolName': c.get('name', 'unknown'),
                                    'toolId': c.get('id', ''),
                                    'arguments': str(c.get('arguments', {}))[:200],
                                })

                    turn_index += 1

                except (KeyError, TypeError, AttributeError):
                    continue

    except Exception:
        pass

    # 返回最近的 N 个工具调用
    return chain[-limit:] if len(chain) > limit else chain


def analyze_agent_errors(agent_id: str, session_limit: int = 5) -> Dict[str, Any]:
    """分析 Agent 的错误情况"""
    aid = normalize_openclaw_agent_id(agent_id)
    sessions_dir = get_openclaw_root() / "agents" / aid / "sessions"
    if not sessions_dir.exists():
        return {'agentId': agent_id, 'error': 'Sessions directory not found', 'errors': []}

    # 获取最近的 session 文件（包括 .deleted 归档文件）
    session_files = []

    # 正常的 jsonl 文件
    for f in sessions_dir.glob("*.jsonl"):
        session_files.append(f)

    # 归档的 deleted 文件（子 agent 的 session）
    for f in sessions_dir.glob("*.deleted.*"):
        session_files.append(f)

    # 按修改时间排序，取最近的 N 个
    session_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    session_files = session_files[:session_limit]

    all_errors = []
    error_summary = {
        'total': 0,
        'byType': {},
        'bySeverity': {},
    }

    for session_file in session_files:
        errors = parse_session_for_errors(session_file)
        for error in errors:
            if 'error' not in error:  # 排除解析错误
                error['sessionFile'] = session_file.name
                error['agentId'] = agent_id

                # 标记是否为归档文件
                error['isArchived'] = '.deleted.' in session_file.name

                # 获取工具调用链
                if error.get('turnIndex'):
                    error['toolChain'] = get_tool_call_chain(
                        session_file,
                        error['turnIndex'],
                        limit=5
                    )

                all_errors.append(error)

                # 统计
                error_summary['total'] += 1
                et = error.get('errorType', 'unknown')
                error_summary['byType'][et] = error_summary['byType'].get(et, 0) + 1
                es = error.get('severity', 'medium')
                error_summary['bySeverity'][es] = error_summary['bySeverity'].get(es, 0) + 1

    return {
        'agentId': agent_id,
        'errors': all_errors,
        'summary': error_summary,
        'analyzedAt': int(datetime.now().timestamp() * 1000),
    }


def analyze_all_agents_errors() -> Dict[str, Any]:
    """分析所有 Agent 的错误"""
    agents_dir = get_openclaw_root() / "agents"
    if not agents_dir.exists():
        return {'agents': [], 'globalSummary': {}}

    agent_ids = [d.name for d in agents_dir.iterdir() if d.is_dir()]

    all_results = []
    global_summary = {
        'totalErrors': 0,
        'byAgent': {},
        'byType': {},
        'bySeverity': {},
    }

    for agent_id in agent_ids:
        result = analyze_agent_errors(agent_id, session_limit=3)
        if result.get('errors'):
            all_results.append(result)

            # 汇总统计
            summary = result.get('summary', {})
            global_summary['totalErrors'] += summary.get('total', 0)
            global_summary['byAgent'][agent_id] = summary.get('total', 0)

            for et, count in summary.get('byType', {}).items():
                global_summary['byType'][et] = global_summary['byType'].get(et, 0) + count

            for es, count in summary.get('bySeverity', {}).items():
                global_summary['bySeverity'][es] = global_summary['bySeverity'].get(es, 0) + count

    return {
        'agents': all_results,
        'globalSummary': global_summary,
        'analyzedAt': int(datetime.now().timestamp() * 1000),
    }


def get_error_detail(agent_id: str, session_file: str, turn_index: int) -> Optional[Dict[str, Any]]:
    """获取单个错误的详细信息"""
    aid = normalize_openclaw_agent_id(agent_id)
    session_path = get_openclaw_root() / "agents" / aid / "sessions" / session_file
    if not session_path.exists():
        return None

    errors = parse_session_for_errors(session_path)
    for error in errors:
        if error.get('turnIndex') == turn_index:
            error['agentId'] = agent_id
            error['sessionFile'] = session_file
            error['toolChain'] = get_tool_call_chain(session_path, turn_index, limit=10)
            return error

    return None
