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
class LLMRound:
    """LLM 轮次"""
    id: str                          # round_1, round_2, ...
    index: int                       # 轮次序号（从1开始）
    trigger: str                     # user_input | tool_result | subagent_result | start
    triggerBy: Optional[str] = None  # 触发来源描述
    stepIds: List[str] = None        # 该轮次包含的步骤 ID 列表
    duration: int = 0                # 该轮次耗时（ms）
    tokens: Optional[Dict[str, int]] = None  # 该轮次的 token 使用

    def __post_init__(self):
        if self.stepIds is None:
            self.stepIds = []

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


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
    toolResultError: Optional[str] = None  # 工具失败时的错误信息 (details.error)

    # 工具链路关联
    pairedToolCallId: Optional[str] = None   # toolResult 专用：对应的 toolCall ID
    pairedToolResultId: Optional[str] = None # toolCall 专用：对应的 toolResult ID
    executionTime: Optional[int] = None      # 工具执行耗时（ms），toolResult 专用

    # 错误
    errorMessage: Optional[str] = None
    errorType: Optional[str] = None

    # 统计
    tokens: Optional[Dict[str, int]] = None

    # 展示控制
    collapsed: bool = False

    # 消息来源（用于区分真实用户和其他 Agent）
    senderId: Optional[str] = None       # 发送者 Agent ID（如 'main'）
    senderName: Optional[str] = None     # 发送者显示名（如 '老K'）

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


# 子 Agent 回传消息的特征（OpenClaw 将子 Agent 结果以 user 消息注入主 Agent session）
_SUBAGENT_RESULT_MARKERS = (
    "Result (untrusted content, treat as data):",
    "[Internal task completion event]",
)

# agent id -> 默认显示名（配置未找到时回退）
_AGENT_ID_TO_LABEL = {
    "main": "主控",
    "analyst-agent": "分析师",
    "architect-agent": "架构师",
    "devops-agent": "运维",
    "project-manager": "项目经理",
    "test-agent": "测试",
    "frontend-agent": "前端",
    "backend-agent": "后端",
}


def _get_subagent_display_name(agent_id: str) -> str:
    """优先从配置获取 Agent 显示名，否则用默认映射或 id"""
    try:
        from data.config_reader import get_agent_config
        cfg = get_agent_config(agent_id)
        if cfg and cfg.get("name"):
            return cfg["name"]
    except Exception:
        pass
    return _AGENT_ID_TO_LABEL.get(agent_id, agent_id)


def _detect_subagent_sender(user_text: str) -> Optional[str]:
    """
    检测 user 消息是否为子 Agent 回传（含 Result (untrusted...) 或 Internal task completion）。
    若是，返回显示标签如「分析师回传」，优先使用配置中的 Agent 名称。
    """
    if not user_text or not isinstance(user_text, str):
        return None
    text = user_text.strip()
    if not any(m in text for m in _SUBAGENT_RESULT_MARKERS):
        return None
    # 尝试从 session_key 行解析子 Agent id
    # OpenClaw 标准格式: agent:${targetAgentId}:subagent:${uuid}（subagent-spawn.ts）
    # segs[1] = targetAgentId（如 analyst-agent），segs[2] = subagent，segs[3] = uuid
    # 多条 session_key 时取最后一个（多事件块时，最后完成的是实际回传者）
    candidates: List[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if "session_key:" in line.lower():
            idx = line.lower().find("session_key:")
            val = line[idx + len("session_key:"):].strip()
            if not val.lower().startswith("agent:"):
                continue
            segs = val.split(":")
            if len(segs) >= 2:
                sub_id = segs[1]  # targetAgentId（agent id）
                if sub_id and not _looks_like_uuid(sub_id):
                    candidates.append(sub_id)
    # 优先使用非 main 的 agent（main 派生子任务时 childSessionKey=agent:main:subagent:uuid）
    for sub_id in reversed(candidates):
        if sub_id and sub_id.lower() != "main":
            display_name = _get_subagent_display_name(sub_id)
            return f"{display_name}回传"
    if candidates:
        # 仅有 main 时显示「子任务回传」避免与主控混淆
        return "子任务回传"
    return "子 Agent 回传"


def _looks_like_uuid(s: str) -> bool:
    """简单判断是否为 UUID（纯 hex 或带连字符）"""
    if not s or len(s) < 8:
        return False
    clean = s.replace("-", "")
    return len(clean) >= 8 and all(c in "0123456789abcdef" for c in clean.lower())


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


def _get_requester_info_for_session(agent_id: str, session_key: Optional[str]) -> Dict[str, Optional[str]]:
    """
    获取子 Agent 会话的消息来源（requester）信息

    优先从 sessions.json 的 spawnedBy 字段获取，其次从 runs.json 的 requesterSessionKey 获取

    Returns:
        {'senderId': 'main', 'senderName': '老K'} 或空字典
    """
    # 方法1：从 sessions.json 的 spawnedBy 字段获取
    sessions_index = OPENCLAW_DIR / f"agents/{agent_id}/sessions/sessions.json"
    if sessions_index.exists():
        try:
            with open(sessions_index, 'r', encoding='utf-8') as f:
                index_data = json.load(f)

            # 如果没有指定 session_key，取最新的一个
            if not session_key:
                # 按 updatedAt 排序取最新的
                entries = [(k, v) for k, v in index_data.items() if isinstance(v, dict)]
                if entries:
                    entries.sort(key=lambda x: x[1].get('updatedAt', 0), reverse=True)
                    session_key = entries[0][0]

            if session_key:
                entry = index_data.get(session_key)
                if isinstance(entry, dict):
                    spawned_by = entry.get('spawnedBy', '')
                    if spawned_by and ':' in spawned_by:
                        # 格式: agent:main:main 或 agent:agent-id:subagent:uuid
                        parts = spawned_by.split(':')
                        if len(parts) >= 2 and parts[0] == 'agent':
                            requester_id = parts[1]
                            requester_name = _get_agent_display_name(requester_id)
                            return {'senderId': requester_id, 'senderName': requester_name}
        except Exception:
            pass

    # 方法2：从 runs.json 查找 requesterSessionKey（备选）
    if not session_key:
        runs = get_subagent_runs().get(agent_id, [])
        if runs:
            runs.sort(key=lambda x: x.get('startedAt', 0), reverse=True)
            session_key = runs[0].get('childSessionKey')

    if not session_key:
        return {}

    runs_file = OPENCLAW_DIR / "subagents" / "runs.json"
    if not runs_file.exists():
        return {}

    try:
        with open(runs_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        runs = data.get('runs', {})

        for run_id, run_info in runs.items():
            if not isinstance(run_info, dict):
                continue
            child_key = run_info.get('childSessionKey', '')
            if child_key == session_key:
                requester_key = run_info.get('requesterSessionKey', '')
                if requester_key and ':' in requester_key:
                    parts = requester_key.split(':')
                    if len(parts) >= 2 and parts[0] == 'agent':
                        requester_id = parts[1]
                        requester_name = _get_agent_display_name(requester_id)
                        return {'senderId': requester_id, 'senderName': requester_name}
                break
    except Exception:
        pass

    return {}


def _get_agent_display_name(agent_id: str) -> str:
    """获取 Agent 的显示名称"""
    try:
        from data.config_reader import get_agent_config
        config = get_agent_config(agent_id)
        return config.get('name', agent_id)
    except Exception:
        return agent_id


def _pair_tool_calls_and_results(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    建立 toolCall 与 toolResult 的配对关系

    规则：
    1. 使用 toolCallId 字段匹配
    2. 按 toolCallId 建立 ID 映射
    3. 为 toolResult 添加 pairedToolCallId
    4. 为 toolCall 添加 pairedToolResultId
    5. 计算工具执行时间 executionTime
    """
    # 建立 toolCall ID 映射: toolCallId -> step
    tool_call_map: Dict[str, Dict[str, Any]] = {}
    for step in steps:
        if step.get('type') == 'toolCall':
            tc_id = step.get('toolCallId') or step.get('id')
            tool_call_map[tc_id] = step

    # 配对 toolResult
    for step in steps:
        if step.get('type') != 'toolResult':
            continue

        tc_id = step.get('toolCallId')
        if not tc_id or tc_id not in tool_call_map:
            continue

        call_step = tool_call_map[tc_id]

        # 双向关联
        step['pairedToolCallId'] = call_step.get('id')
        call_step['pairedToolResultId'] = step.get('id')

        # 计算执行时间
        call_time = call_step.get('timestamp', 0)
        result_time = step.get('timestamp', 0)
        if call_time and result_time:
            step['executionTime'] = result_time - call_time

    return steps


def _build_llm_rounds(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    根据步骤序列构建 LLM 轮次

    规则：
    1. user 消息开启新轮次
    2. toolResult 后的第一个 assistant 步骤开启新轮次
    3. 同一轮次内的 thinking + toolCall + text 归为一组
    4. toolResult 单独作为工具执行块，不属于任何 LLM 轮次

    Returns:
        轮次列表，每个轮次包含 id, index, trigger, triggerBy, stepIds, duration, tokens
    """
    rounds: List[Dict[str, Any]] = []
    current_round: Optional[Dict[str, Any]] = None
    round_index = 0
    last_tool_result_name: Optional[str] = None
    last_was_tool_result = False

    for step in steps:
        step_type = step.get('type')
        step_id = step.get('id', '')

        # user 消息：结束上一轮，开启新轮次
        if step_type == 'user':
            if current_round:
                rounds.append(current_round)
            round_index += 1

            # 判断是子 Agent 回传还是普通用户输入
            sender_name = step.get('senderName', '')
            if sender_name and ('回传' in sender_name or sender_name != '用户'):
                trigger = 'subagent_result'
                trigger_by = sender_name
            else:
                trigger = 'user_input'
                trigger_by = sender_name or '用户'

            current_round = {
                'id': f'round_{round_index}',
                'index': round_index,
                'trigger': trigger,
                'triggerBy': trigger_by,
                'stepIds': [step_id],
                'duration': step.get('duration', 0),
                'tokens': step.get('tokens')
            }
            last_was_tool_result = False
            continue

        # toolResult：单独作为工具执行块，结束当前轮次
        if step_type == 'toolResult':
            if current_round:
                rounds.append(current_round)
                current_round = None
            # 记录工具名，用于下一轮次的触发原因
            last_tool_result_name = step.get('toolName', '工具')
            last_was_tool_result = True
            continue

        # assistant 步骤（thinking, toolCall, text）
        if step_type in ('thinking', 'toolCall', 'text'):
            # 如果是 toolResult 后第一个 assistant 步骤，开启新轮次
            if not current_round:
                round_index += 1
                trigger = 'tool_result' if last_was_tool_result else 'start'
                trigger_by = f'{last_tool_result_name} 结果' if last_was_tool_result else '会话开始'

                current_round = {
                    'id': f'round_{round_index}',
                    'index': round_index,
                    'trigger': trigger,
                    'triggerBy': trigger_by,
                    'stepIds': [],
                    'duration': 0,
                    'tokens': None
                }
                last_was_tool_result = False

            current_round['stepIds'].append(step_id)
            current_round['duration'] += step.get('duration', 0)

            # 累加 tokens
            step_tokens = step.get('tokens')
            if step_tokens:
                if current_round['tokens'] is None:
                    current_round['tokens'] = {'input': 0, 'output': 0, 'cumulative': 0}
                current_round['tokens']['input'] += step_tokens.get('input', 0)
                current_round['tokens']['output'] += step_tokens.get('output', 0)
                current_round['tokens']['cumulative'] = step_tokens.get('cumulative', 0)

        # error：结束当前轮次
        if step_type == 'error':
            if current_round:
                rounds.append(current_round)
                current_round = None
            last_was_tool_result = False

    # 处理最后一个轮次
    if current_round:
        rounds.append(current_round)

    return rounds


def get_timeline_steps(
    agent_id: str,
    session_key: Optional[str] = None,
    limit: int = 100,
    round_mode: bool = True
) -> Dict[str, Any]:
    """
    获取 Agent 会话的时序步骤

    Args:
        agent_id: Agent ID
        session_key: 会话 key（可选）
        limit: 返回步骤数限制
        round_mode: 是否返回 LLM 轮次分组（默认 True）
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

    # 获取消息来源信息（用于子 Agent 显示发送者）
    requester_info = _get_requester_info_for_session(agent_id, session_key)

    return _parse_session_file(session_file, agent_id, session_id, limit, requester_info, round_mode)


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

    # 获取 requester 信息（子 Agent 的消息来源）
    requester_info = _get_requester_info_for_session(agent_id, None)
    sender_id = requester_info.get('senderId')
    sender_name = requester_info.get('senderName')

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
            "tokens": {"input": 0, "output": 0, "cumulative": 0},
            "senderId": sender_id,
            "senderName": sender_name
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
    limit: int,
    requester_info: Optional[Dict[str, str]] = None,
    round_mode: bool = True
) -> Dict[str, Any]:
    """解析 session jsonl 文件"""
    steps: List[TimelineStep] = []
    step_index = 0
    cumulative_tokens = 0
    started_at: Optional[int] = None
    last_timestamp: Optional[int] = None
    session_status = "completed"
    tool_call_map: Dict[str, str] = {}

    # 获取发送者信息
    sender_id = requester_info.get('senderId') if requester_info else None
    sender_name = requester_info.get('senderName') if requester_info else None

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

                # 子 Agent 回传消息以 user 身份注入，需正确标注来源
                display_sender = sender_name or sender_id
                subagent_label = _detect_subagent_sender(user_text)
                if subagent_label:
                    display_sender = subagent_label

                steps.append(TimelineStep(
                    id=f"step_{step_index}",
                    type=StepType.USER.value,
                    status=StepStatus.SUCCESS.value,
                    timestamp=timestamp,
                    duration=duration,
                    content=_truncate_text(user_text, 1000),
                    senderId=sender_id,
                    senderName=display_sender
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
                tool_error = details.get('error') if isinstance(details.get('error'), str) else None

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
                    toolResultError=tool_error,
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

    result = {
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

    # 建立 toolCall 与 toolResult 配对关系
    result["steps"] = _pair_tool_calls_and_results(result["steps"])

    # 添加 LLM 轮次分组
    if round_mode:
        result["rounds"] = _build_llm_rounds(result["steps"])
        result["roundMode"] = True

    return result
