"""
时序数据读取器 - 将 session jsonl 解析为可视化时序步骤
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class StepType(str, Enum):
    """步骤类型"""
    USER = "user"                 # 用户消息
    THINKING = "thinking"         # Agent 思考
    TEXT = "text"                 # Agent 文本响应
    TOOL_CALL = "toolCall"        # 工具调用
    TOOL_RESULT = "toolResult"    # 工具结果
    ERROR = "error"               # 错误


class StepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class TokenUsage:
    input: int = 0
    output: int = 0
    cumulative: int = 0


@dataclass
class TimelineStep:
    """时序步骤"""
    id: str
    type: str                     # StepType
    status: str                   # StepStatus
    timestamp: int
    duration: int = 0             # ms

    # 内容
    content: Optional[str] = None
    thinking: Optional[str] = None

    # 工具调用
    toolName: Optional[str] = None
    toolCallId: Optional[str] = None
    toolArguments: Optional[Dict[str, Any]] = None
    toolResult: Optional[str] = None
    toolResultStatus: Optional[str] = None  # ok / error

    # 错误
    errorMessage: Optional[str] = None
    errorType: Optional[str] = None

    # 统计
    tokens: Optional[Dict[str, int]] = None

    # 展示控制
    collapsed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _openclaw_home() -> Path:
    """OpenClaw 根目录"""
    env = os.environ.get("OPENCLAW_HOME")
    if env:
        p = Path(env).expanduser()
        if p.exists():
            return p
    return Path.home() / ".openclaw"


OPENCLAW_DIR = _openclaw_home()


def _detect_error_type(error_msg: str) -> str:
    """检测错误类型"""
    error_msg_lower = (error_msg or '').lower()

    if '429' in error_msg or 'rate limit' in error_msg_lower:
        return 'rate-limit'
    elif 'token' in error_msg_lower or 'context' in error_msg_lower:
        return 'token-limit'
    elif 'timeout' in error_msg_lower or '超时' in error_msg_lower:
        return 'timeout'
    elif '余额不足' in (error_msg or ''):
        return 'quota'
    else:
        return 'unknown'


def _truncate_text(text: str, max_len: int = 500) -> str:
    """截断文本"""
    if not text or len(text) <= max_len:
        return text
    return text[:max_len] + '...'


def _parse_timestamp(ts) -> int:
    """解析时间戳为毫秒"""
    if not ts:
        return 0
    if isinstance(ts, (int, float)):
        return int(ts)
    if isinstance(ts, str):
        import datetime
        try:
            dt = datetime.datetime.fromisoformat(ts.replace('Z', '+00:00'))
            return int(dt.timestamp() * 1000)
        except:
            return 0
    return 0


def get_subagent_runs() -> Dict[str, List[Dict]]:
    """获取子代理运行记录，按 agent_id 分组"""
    runs_file = OPENCLAW_DIR / "subagents" / "runs.json"
    if not runs_file.exists():
        return {}

    try:
        with open(runs_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except:
        return {}

    runs_by_agent: Dict[str, List[Dict]] = {}
    runs = data.get('runs', {})
    for run_id, run_info in runs.items():
        if not isinstance(run_info, dict):
            continue
        child_key = run_info.get('childSessionKey', '')
        # 格式: agent:analyst-agent:subagent:xxx
        if ':' in child_key:
            parts = child_key.split(':')
            if len(parts) >= 2:
                agent_id = parts[1]
                if agent_id not in runs_by_agent:
                    runs_by_agent[agent_id] = []
                runs_by_agent[agent_id].append({
                    'runId': run_id,
                    'task': run_info.get('task', ''),
                    'startedAt': run_info.get('startedAt'),
                    'endedAt': run_info.get('endedAt'),
                    'outcome': run_info.get('outcome', ''),
                    'childSessionKey': child_key
                })

    return runs_by_agent


def get_timeline_steps(
    agent_id: str,
    session_key: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    获取 Agent 会话的时序步骤
    """
    sessions_path = OPENCLAW_DIR / f"agents/{agent_id}/sessions"

    # 如果该 agent 没有 sessions 目录或为空，尝试从 subagent runs 获取
    if not sessions_path.exists() or not list(sessions_path.glob("*.jsonl")):
        return _get_subagent_timeline(agent_id, limit)

    # 查找 session 文件
    session_file: Optional[Path] = None
    session_id: Optional[str] = None

    if session_key:
        sessions_index = sessions_path / "sessions.json"
        if sessions_index.exists():
            try:
                with open(sessions_index, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                entry = index_data.get(session_key) if isinstance(index_data, dict) else None
                if entry and isinstance(entry, dict):
                    sf = entry.get('sessionFile')
                    sid = entry.get('sessionId')
                    if sf:
                        session_file = Path(sf)
                    elif sid:
                        session_file = sessions_path / f"{sid}.jsonl"
                    session_id = sid or session_key
            except (json.JSONDecodeError, IOError):
                pass
    else:
        jsonl_files = list(sessions_path.glob("*.jsonl"))
        if jsonl_files:
            jsonl_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            session_file = jsonl_files[0]
            session_id = session_file.stem

    if not session_file or not session_file.exists():
        return _get_subagent_timeline(agent_id, limit)

    return _parse_session_file(session_file, agent_id, session_id, limit)


def _get_subagent_timeline(agent_id: str, limit: int) -> Dict[str, Any]:
    """从 subagent runs 获取子代理的时序数据"""
    runs_by_agent = get_subagent_runs()
    runs = runs_by_agent.get(agent_id, [])

    if not runs:
        return {
            "sessionId": None,
            "agentId": agent_id,
            "startedAt": None,
            "status": "no_sessions",
            "steps": [],
            "stats": {
                "totalDuration": 0,
                "totalInputTokens": 0,
                "totalOutputTokens": 0,
                "toolCallCount": 0,
                "stepCount": 0
            },
            "message": f"该 Agent 尚无独立会话记录。子 Agent 的活动记录在 Main Agent 的会话中。"
        }

    # 将运行记录转换为步骤
    steps = []
    for i, run in enumerate(runs[:limit]):
        started = run.get('startedAt')
        ended = run.get('endedAt')
        duration = (ended - started) if started and ended else 0

        steps.append({
            "id": f"run_{i}",
            "type": "text",
            "status": "success" if run.get('outcome') == 'ok' else "running" if not ended else "error",
            "timestamp": started or 0,
            "duration": duration,
            "content": run.get('task', '任务执行中...'),
            "tokens": {"input": 0, "output": 0, "cumulative": 0}
        })

    return {
        "sessionId": f"subagent-{agent_id}",
        "agentId": agent_id,
        "startedAt": runs[0].get('startedAt') if runs else None,
        "status": "completed" if all(r.get('endedAt') for r in runs) else "running",
        "steps": steps,
        "stats": {
            "totalDuration": sum((r.get('endedAt', 0) - r.get('startedAt', 0)) for r in runs if r.get('startedAt') and r.get('endedAt')),
            "totalInputTokens": 0,
            "totalOutputTokens": 0,
            "toolCallCount": 0,
            "stepCount": len(steps)
        }
    }


def _parse_session_file(
    session_file: Path,
    agent_id: str,
    session_id: Optional[str],
    limit: int
) -> Dict[str, Any]:
    """解析 session jsonl 文件"""
    steps: List[TimelineStep] = []
    step_index = 0
    cumulative_tokens = 0
    started_at: Optional[int] = None
    last_timestamp: Optional[int] = None
    session_status = "completed"
    tool_call_map: Dict[str, str] = {}

    with open(session_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            msg_type = data.get('type')

            if msg_type == 'session':
                started_at = _parse_timestamp(data.get('timestamp', 0))
                continue

            if msg_type != 'message':
                continue

            msg = data.get('message', {})
            role = msg.get('role')
            if not role:
                continue

            timestamp = _parse_timestamp(msg.get('timestamp') or data.get('timestamp', 0))

            duration = 0
            if last_timestamp and timestamp:
                duration = timestamp - last_timestamp
            last_timestamp = timestamp

            if not started_at:
                started_at = timestamp

            content_list = msg.get('content', [])
            if isinstance(content_list, str):
                content_list = [{'type': 'text', 'text': content_list}]

            usage = msg.get('usage', {})
            if usage:
                cumulative_tokens += usage.get('input', 0) + usage.get('output', 0)

            stop_reason = msg.get('stopReason')

            if stop_reason == 'error':
                session_status = "error"
                error_msg = msg.get('errorMessage', '')
                steps.append(TimelineStep(
                    id=f"step_{step_index}",
                    type=StepType.ERROR.value,
                    status=StepStatus.ERROR.value,
                    timestamp=timestamp,
                    duration=duration,
                    errorMessage=_truncate_text(error_msg, 1000),
                    errorType=_detect_error_type(error_msg),
                    tokens={"input": usage.get('input', 0), "output": usage.get('output', 0), "cumulative": cumulative_tokens}
                ))
                step_index += 1
                continue

            if role == 'user':
                user_text = ""
                for c in content_list:
                    if isinstance(c, dict) and c.get('type') == 'text':
                        user_text += c.get('text', '')

                steps.append(TimelineStep(
                    id=f"step_{step_index}",
                    type=StepType.USER.value,
                    status=StepStatus.SUCCESS.value,
                    timestamp=timestamp,
                    duration=duration,
                    content=_truncate_text(user_text, 1000)
                ))
                step_index += 1

            elif role == 'assistant':
                thinking_text = ""
                text_content = ""
                tool_calls = []

                for c in content_list:
                    if not isinstance(c, dict):
                        continue
                    ct = c.get('type')

                    if ct == 'thinking':
                        thinking_text += c.get('thinking', '')
                    elif ct == 'text':
                        text_content += c.get('text', '')
                    elif ct == 'toolCall':
                        tool_calls.append({
                            'name': c.get('name'),
                            'arguments': c.get('arguments'),
                            'id': c.get('id')
                        })

                if thinking_text:
                    steps.append(TimelineStep(
                        id=f"step_{step_index}",
                        type=StepType.THINKING.value,
                        status=StepStatus.SUCCESS.value,
                        timestamp=timestamp,
                        duration=duration if not text_content and not tool_calls else 0,
                        thinking=_truncate_text(thinking_text, 500),
                        collapsed=True,
                        tokens={"input": usage.get('input', 0), "output": 0, "cumulative": cumulative_tokens}
                    ))
                    step_index += 1
                    duration = 0

                for tc in tool_calls:
                    step_id = f"step_{step_index}"
                    tc_id = tc.get('id') or step_id
                    tool_call_map[tc_id] = step_id

                    steps.append(TimelineStep(
                        id=step_id,
                        type=StepType.TOOL_CALL.value,
                        status=StepStatus.SUCCESS.value,
                        timestamp=timestamp,
                        duration=duration,
                        toolName=tc.get('name'),
                        toolCallId=tc_id,
                        toolArguments=tc.get('arguments'),
                        tokens={"input": 0, "output": 0, "cumulative": cumulative_tokens}
                    ))
                    step_index += 1
                    duration = 0

                if text_content:
                    steps.append(TimelineStep(
                        id=f"step_{step_index}",
                        type=StepType.TEXT.value,
                        status=StepStatus.SUCCESS.value,
                        timestamp=timestamp,
                        duration=duration,
                        content=_truncate_text(text_content, 1000),
                        tokens={"input": usage.get('input', 0), "output": usage.get('output', 0), "cumulative": cumulative_tokens}
                    ))
                    step_index += 1

                if stop_reason not in ('end_turn', None):
                    session_status = "running"

            elif role == 'toolResult':
                tool_name = msg.get('toolName', 'unknown')
                tc_id = msg.get('toolCallId', '')
                details = msg.get('details', {})
                result_status = details.get('status', 'ok')

                result_content = ""
                for c in content_list:
                    if isinstance(c, dict):
                        if c.get('type') == 'text':
                            result_content += c.get('text', '')
                        elif c.get('type') == 'toolResult':
                            result_content += str(c.get('content', ''))

                if not result_content:
                    result_content = str(details)

                steps.append(TimelineStep(
                    id=f"step_{step_index}",
                    type=StepType.TOOL_RESULT.value,
                    status=StepStatus.ERROR.value if result_status == 'error' else StepStatus.SUCCESS.value,
                    timestamp=timestamp,
                    duration=duration,
                    toolName=tool_name,
                    toolCallId=tc_id,
                    toolResult=_truncate_text(result_content, 2000),
                    toolResultStatus=result_status,
                    tokens={"input": 0, "output": 0, "cumulative": cumulative_tokens}
                ))
                step_index += 1

    total_duration = 0
    total_input = 0
    total_output = 0
    tool_call_count = 0

    for step in steps:
        if step.duration:
            total_duration += step.duration
        if step.tokens:
            total_input += step.tokens.get('input', 0)
            total_output += step.tokens.get('output', 0)
        if step.type == StepType.TOOL_CALL.value:
            tool_call_count += 1

    if len(steps) > limit:
        steps = steps[-limit:]

    return {
        "sessionId": session_id,
        "agentId": agent_id,
        "startedAt": started_at,
        "status": session_status,
        "steps": [s.to_dict() for s in steps],
        "stats": {
            "totalDuration": total_duration,
            "totalInputTokens": total_input,
            "totalOutputTokens": total_output,
            "toolCallCount": tool_call_count,
            "stepCount": len(steps)
        }
    }
