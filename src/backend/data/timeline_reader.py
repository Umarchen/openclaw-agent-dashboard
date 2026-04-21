"""
时序数据读取器 - 将 session jsonl 解析为可视化时序步骤
"""
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Iterable
from dataclasses import dataclass, asdict
from enum import Enum

LOG = logging.getLogger(__name__)

# 大 jsonl：先尝试只读尾部，避免整文件逐行解析
LARGE_JSONL_BYTES = 512 * 1024
TAIL_JSONL_BYTES = 2 * 1024 * 1024
TAIL_JSONL_MAX_LINES = 4000


class StepType(str, Enum):
    """步骤类型"""
    USER = "user"                 # 用户消息
    THINKING = "thinking"         # Agent 思考
    TEXT = "text"                 # Agent 文本响应
    TOOL_CALL = "toolCall"        # 工具调用
    TOOL_RESULT = "toolResult"    # 工具结果
    ERROR = "error"               # 错误
    SUBAGENT_RESULT = "subagentResult"  # 子 Agent 回传结果


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
    content: Optional[str] = None
    thinking: Optional[str] = None
    toolName: Optional[str] = None
    toolCallId: Optional[str] = None
    toolArguments: Optional[Dict[str, Any]] = None
    toolResult: Optional[str] = None
    toolResultStatus: Optional[str] = None
    toolResultError: Optional[str] = None
    pairedToolCallId: Optional[str] = None
    pairedToolResultId: Optional[str] = None
    executionTime: Optional[int] = None
    errorMessage: Optional[str] = None
    errorType: Optional[str] = None
    tokens: Optional[Dict[str, int]] = None
    collapsed: bool = False
    senderId: Optional[str] = None
    senderName: Optional[str] = None
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


from data.config_reader import get_openclaw_root
from data.session_reader import normalize_sessions_index, resolve_session_jsonl_path


def _read_session_header_timestamp(path: Path) -> Optional[int]:
    """仅读首行，解析 session 类型记录的开始时间（大文件尾部解析时补全 startedAt）。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            first = f.readline()
        if not first.strip():
            return None
        data = json.loads(first.strip())
        if data.get('type') == 'session':
            return _parse_timestamp(data.get('timestamp', 0))
    except (json.JSONDecodeError, OSError, IOError):
        pass
    return None


def _read_jsonl_tail_line_slice(path: Path) -> Optional[List[str]]:
    """
    大文件时返回尾部若干行（字节与行数双上限），否则返回 None 表示应整文件读取。
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size <= LARGE_JSONL_BYTES:
        return None
    with open(path, 'rb') as f:
        f.seek(max(0, size - TAIL_JSONL_BYTES))
        raw = f.read()
    text = raw.decode('utf-8', errors='replace')
    lines = text.splitlines()
    if not lines:
        return []
    if size > TAIL_JSONL_BYTES:
        lines = lines[1:]
    if len(lines) > TAIL_JSONL_MAX_LINES:
        lines = lines[-TAIL_JSONL_MAX_LINES:]
    return lines


def _read_text_lines(path: Path) -> List[str]:
    with open(path, 'r', encoding='utf-8') as f:
        return f.readlines()


# 子 Agent 回传消息的特征
_SUBAGENT_RESULT_MARKERS = (
    "Result (untrusted content, treat as data):",
    "[Internal task completion event]",
)

# agent id -> 默认显示名
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
    """优先从配置获取 Agent 显示名， otherwise用默认映射或 id"""
    try:
        from data.config_reader import get_agent_config
        cfg = get_agent_config(agent_id)
        if cfg and cfg.get("name"):
            return cfg["name"]
    except Exception:
        pass
    return _AGENT_ID_TO_LABEL.get(agent_id, agent_id)


def _detect_subagent_sender(user_text: str) -> Optional[str]:
    """检测 user 消息是否为子 Agent 回传"""
    if not user_text or not isinstance(user_text, str):
        return None
    text = user_text.strip()
    if not any(m in text for m in _SUBAGENT_RESULT_MARKERS):
        return None
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
                sub_id = segs[1]
                if sub_id and not _looks_like_uuid(sub_id):
                    candidates.append(sub_id)
    for sub_id in reversed(candidates):
        if sub_id and sub_id.lower() != "main":
            display_name = _get_subagent_display_name(sub_id)
            return f"{display_name}回传"
    if candidates:
        return "子任务回传"
    return "子 Agent 回传"


def _looks_like_uuid(s: str) -> bool:
    """简单判断是否为 UUID"""
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
    """获取子代理运行记录，按 agent_id 分组（按 mtime 缓存，单次请求内多次调用不重复读盘）。"""
    runs_file = get_openclaw_root() / "subagents" / "runs.json"
    if not runs_file.exists():
        return {}
    try:
        mtime = runs_file.stat().st_mtime
    except OSError:
        return {}
    return _get_subagent_runs_cached(mtime)


@lru_cache(maxsize=16)
def _get_subagent_runs_cached(mtime: float) -> Dict[str, List[Dict]]:
    runs_file = get_openclaw_root() / "subagents" / "runs.json"
    try:
        with open(runs_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return {}
    runs_by_agent: Dict[str, List[Dict]] = {}
    runs = data.get('runs', {})
    for run_id, run_info in runs.items():
        if not isinstance(run_info, dict):
            continue
        child_key = run_info.get('childSessionKey', '')
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
                    'childSessionKey': child_key,
                    'requesterSessionKey': run_info.get('requesterSessionKey', '')
                })
    return runs_by_agent


def _get_requester_info_for_session(agent_id: str, session_key: Optional[str]) -> Dict[str, Optional[str]]:
    """获取子 Agent 会话的消息来源（requester）信息"""
    # 方法1：从 sessions.json 的 spawnedBy 字段获取
    sessions_index = get_openclaw_root() / f"agents/{agent_id}/sessions/sessions.json"
    if sessions_index.exists():
        try:
            with open(sessions_index, 'r', encoding='utf-8') as f:
                index_data = json.load(f)
            index_map = normalize_sessions_index(index_data)
            if not session_key:
                entries = list(index_map.items())
                if entries:
                    entries.sort(
                        key=lambda x: (x[1].get('updatedAt') or x[1].get('lastMessageAt') or 0),
                        reverse=True,
                    )
                    session_key = entries[0][0]
            if session_key:
                entry = index_map.get(session_key)
                if isinstance(entry, dict):
                    spawned_by = entry.get('spawnedBy', '')
                    if spawned_by and ':' in spawned_by:
                        parts = spawned_by.split(':')
                        if len(parts) >= 2 and parts[0] == 'agent':
                            requester_id = parts[1]
                            requester_name = _get_agent_display_name(requester_id)
                            return {'senderId': requester_id, 'senderName': requester_name}
        except Exception:
            pass
    # 方法2：从 runs.json 查找 requesterSessionKey
    if not session_key:
        runs = get_subagent_runs().get(agent_id, [])
        if runs:
            runs.sort(key=lambda x: x.get('startedAt', 0), reverse=True)
            session_key = runs[0].get('childSessionKey')
    if not session_key:
        return {}
    runs_file = get_openclaw_root() / "subagents" / "runs.json"
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


def _get_main_agent_id() -> str:
    """获取主 Agent ID"""
    try:
        from data.config_reader import get_main_agent_id
        return get_main_agent_id()
    except Exception:
        return "main"


def _pair_tool_calls_and_results(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """建立 toolCall 与 toolResult 的配对关系"""
    tool_call_map: Dict[str, Dict[str, Any]] = {}
    for step in steps:
        if step.get('type') == 'toolCall':
            tc_id = step.get('toolCallId') or step.get('id')
            tool_call_map[tc_id] = step
    for step in steps:
        if step.get('type') != 'toolResult':
            continue
        tc_id = step.get('toolCallId')
        if not tc_id or tc_id not in tool_call_map:
            continue
        call_step = tool_call_map[tc_id]
        step['pairedToolCallId'] = call_step.get('id')
        call_step['pairedToolResultId'] = step.get('id')
        call_time = call_step.get('timestamp', 0)
        result_time = step.get('timestamp', 0)
        if call_time and result_time:
            step['executionTime'] = result_time - call_time
    return steps


# 子 Agent 时序与 runs.json 中本次派发 run 对齐（含 PM/主链路 spawn 时刻）
_RUN_ANCHOR_SLACK_MS = 500


def _subagent_run_anchor_ms(agent_id: str, resolved_session_key: Optional[str]) -> Optional[int]:
    """
    返回 runs.json 中与子会话对应的本次 run 的 startedAt（毫秒）。
    用于从「派发/子 Agent 会话开始」起展示，去掉同文件内更早的噪声。
    """
    runs = get_subagent_runs().get(agent_id, [])
    if not runs:
        return None
    if resolved_session_key:
        for r in runs:
            if r.get('childSessionKey') == resolved_session_key:
                t = r.get('startedAt')
                if t is not None:
                    return int(t)
        return None
    ordered = sorted(runs, key=lambda x: x.get('startedAt') or 0, reverse=True)
    t = ordered[0].get('startedAt')
    return int(t) if t is not None else None


def _rebuild_subagent_timeline_payload(
    steps: List[Dict[str, Any]],
    result: Dict[str, Any],
    limit: int,
    round_mode: bool,
) -> None:
    """就地更新 result 的 steps / stats / rounds（步骤已为 dict 列表）。"""
    if len(steps) > limit:
        steps = steps[-limit:]
    result['steps'] = _pair_tool_calls_and_results(steps)
    total_duration = 0
    total_input = 0
    total_output = 0
    tool_call_count = 0
    for step in result['steps']:
        if step.get('duration'):
            total_duration += step['duration']
        tok = step.get('tokens') or {}
        total_input += tok.get('input', 0)
        total_output += tok.get('output', 0)
        if step.get('type') == StepType.TOOL_CALL.value:
            tool_call_count += 1
    result['stats'] = {
        'totalDuration': total_duration,
        'totalInputTokens': total_input,
        'totalOutputTokens': total_output,
        'toolCallCount': tool_call_count,
        'stepCount': len(result['steps']),
    }
    if round_mode:
        result['rounds'] = _build_llm_rounds(result['steps'])
        result['roundMode'] = True


def _apply_subagent_run_anchor_to_result(
    result: Dict[str, Any],
    anchor_ms: int,
    limit: int,
    round_mode: bool,
) -> Dict[str, Any]:
    """去掉 anchor 之前的步骤；若过滤后为空则保留原步骤。"""
    steps_in = result.get('steps') or []
    if not steps_in:
        return result
    cutoff = anchor_ms - _RUN_ANCHOR_SLACK_MS
    filtered = [s for s in steps_in if (s.get('timestamp') or 0) >= cutoff]
    if not filtered:
        return result
    result['runStartedAt'] = anchor_ms
    if result.get('steps') and filtered[0].get('timestamp') is not None:
        result['startedAt'] = filtered[0]['timestamp']
    _rebuild_subagent_timeline_payload(filtered, result, limit, round_mode)
    return result


def _build_llm_rounds(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """根据步骤序列构建 LLM 轮次"""
    rounds: List[Dict[str, Any]] = []
    current_round: Optional[Dict[str, Any]] = None
    round_index = 0
    last_tool_result_name: Optional[str] = None
    last_was_tool_result = False
    for step in steps:
        step_type = step.get('type')
        step_id = step.get('id', '')
        if step_type in ('user', 'subagentResult'):
            if current_round:
                rounds.append(current_round)
            round_index += 1
            sender_name = step.get('senderName', '')
            sender_id = step.get('senderId', '')
            if step_type == 'subagentResult' or (sender_name and ('输出' in sender_name or '回传' in sender_name)):
                trigger = 'subagent_result'
                trigger_by = sender_name or '子代理输出'
            elif sender_name and sender_id and sender_name not in ('用户', ''):
                trigger = 'user_input'
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
        if step_type == 'toolResult':
            if current_round:
                rounds.append(current_round)
                current_round = None
            last_tool_result_name = step.get('toolName', '工具')
            last_was_tool_result = True
            continue
        if step_type in ('thinking', 'toolCall', 'text'):
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
            step_tokens = step.get('tokens')
            if step_tokens:
                if current_round['tokens'] is None:
                    current_round['tokens'] = {'input': 0, 'output': 0, 'cumulative': 0}
                current_round['tokens']['input'] += step_tokens.get('input', 0)
                current_round['tokens']['output'] += step_tokens.get('output', 0)
                current_round['tokens']['cumulative'] = step_tokens.get('cumulative', 0)
        if step_type == 'error':
            if current_round:
                rounds.append(current_round)
                current_round = None
            last_was_tool_result = False
    if current_round:
        rounds.append(current_round)
    return rounds


def resolve_agent_session_jsonl(
    agent_id: str,
    session_key: Optional[str] = None,
) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
    """
    定位 agents/{agent_id}/sessions 下应对应的 .jsonl。

    不再仅用目录 glob 判断「是否有会话」：OpenClaw 在 sessions.json 里记录的
    sessionFile（含绝对路径）可能与 glob 不同步；子 Agent 应优先走独立转写。

    返回 (jsonl_path, session_id, resolved_session_key)；无法解析时为 (None, None, None)。
    """
    sessions_path = get_openclaw_root() / f"agents/{agent_id}/sessions"
    if not sessions_path.exists():
        return None, None, None

    index_path = sessions_path / "sessions.json"
    index_map: Dict[str, Dict[str, Any]] = {}
    if index_path.exists():
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                index_map = normalize_sessions_index(json.load(f))
        except (json.JSONDecodeError, IOError):
            index_map = {}

    prefix = f"agent:{agent_id}:"

    if session_key:
        entry = index_map.get(session_key)
        if isinstance(entry, dict):
            p = resolve_session_jsonl_path(sessions_path, entry)
            if p and p.is_file():
                sid = entry.get('sessionId') or session_key
                return p, sid, session_key
        return None, None, None

    agent_keys = [
        k for k in index_map
        if isinstance(index_map.get(k), dict) and str(k).startswith(prefix)
    ]

    # 1) 与当前子任务最一致：runs.json 中该 agent 最近一次 run 的 childSessionKey
    runs = get_subagent_runs().get(agent_id, [])
    if runs:
        runs.sort(key=lambda x: x.get('startedAt', 0), reverse=True)
        preferred_key = runs[0].get('childSessionKey')
        if preferred_key and preferred_key in index_map:
            ent = index_map[preferred_key]
            if isinstance(ent, dict):
                p = resolve_session_jsonl_path(sessions_path, ent)
                if p and p.is_file():
                    sid = ent.get('sessionId') or preferred_key
                    return p, sid, preferred_key

    # 2) 目录下最新的 *.jsonl（mtime）
    jsonl_files = list(sessions_path.glob("*.jsonl"))
    if jsonl_files:
        jsonl_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        f = jsonl_files[0]
        sid = f.stem
        resolved_key: Optional[str] = None
        try:
            f_resolved = f.resolve()
        except OSError:
            f_resolved = None
        if f_resolved is not None:
            for k, ent in index_map.items():
                if not isinstance(ent, dict):
                    continue
                rp = resolve_session_jsonl_path(sessions_path, ent)
                if not rp or not rp.is_file():
                    continue
                try:
                    if rp.resolve() == f_resolved:
                        resolved_key = k
                        break
                except OSError:
                    continue
        return f, sid, resolved_key

    # 3) 仅有 sessions.json 索引、尚无 glob 到的文件时：按 updatedAt 试解析路径
    if agent_keys:
        agent_keys.sort(
            key=lambda k: (index_map[k].get('updatedAt') or index_map[k].get('lastMessageAt') or 0),
            reverse=True,
        )
        for k in agent_keys:
            ent = index_map[k]
            p = resolve_session_jsonl_path(sessions_path, ent)
            if p and p.is_file():
                sid = ent.get('sessionId') or k
                return p, sid, k

    return None, None, None


def _empty_main_agent_timeline(agent_id: str) -> Dict[str, Any]:
    """
    主 Agent 无法定位会话 jsonl 时的响应（勿走子 Agent 回退，否则会误显示「子代理」空态）。
    """
    root = get_openclaw_root()
    rel = f"agents/{agent_id}/sessions"
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
            "stepCount": 0,
        },
        "message": (
            f"未在 {root / rel} 下找到会话文件。请确认 OpenClaw 已运行并产生会话，"
            "且 Dashboard 与 OpenClaw 使用同一状态目录（OPENCLAW_STATE_DIR 或 ~/.openclaw）。"
        ),
        "isMainAgent": True,
    }


def get_timeline_steps(
    agent_id: str,
    session_key: Optional[str] = None,
    limit: int = 100,
    round_mode: bool = True
) -> Dict[str, Any]:
    """获取 Agent 会话的时序步骤"""
    session_file, session_id, resolved_key = resolve_agent_session_jsonl(agent_id, session_key)
    if session_file and session_file.exists():
        req_key = session_key if session_key else resolved_key
        requester_info = _get_requester_info_for_session(agent_id, req_key)
        result = _parse_session_file(session_file, agent_id, session_id, limit, requester_info, round_mode)
        # 子 Agent：从 runs.json 本次 run 的 startedAt 起展示（对应派发进子会话的时刻，含 PM 经链路下发）
        if agent_id != _get_main_agent_id():
            anchor = _subagent_run_anchor_ms(agent_id, resolved_key)
            if anchor is not None:
                result = _apply_subagent_run_anchor_to_result(result, anchor, limit, round_mode)
        return result
    if agent_id == _get_main_agent_id():
        return _empty_main_agent_timeline(agent_id)
    return _get_subagent_timeline(agent_id, limit)


def _get_subagent_timeline(agent_id: str, limit: int) -> Dict[str, Any]:
    """
    获取子 Agent 时序数据（仅在 resolve_agent_session_jsonl 无法定位独立 .jsonl 时进入）。

    数据源优先级（基于实时性）：
    1. runs.json - 更及时，适合判断创建/进行中/完成状态（spawn 和 complete 时立即写入）
    2. 主 Agent session - 从主会话中按子 Agent 过滤的步骤（旧逻辑，有延迟/不完整）

    正常情况应已通过 agents/{agent_id}/sessions 下独立 jsonl + sessions.json 解析
    （见 resolve_agent_session_jsonl）；此处为回退。
    """
    # 1. 从 runs.json 获取实时状态和基础信息
    runs_data = _get_subagent_timeline_from_runs(agent_id, limit)
    runs_status = runs_data.get('status', 'no_sessions')

    # 2. 尝试从主 Agent session 获取详细步骤
    main_agent_id = _get_main_agent_id()
    main_session_dir = get_openclaw_root() / f"agents/{main_agent_id}/sessions"
    jsonl_files = list(main_session_dir.glob("*.jsonl")) if main_session_dir.exists() else []

    if not jsonl_files:
        # 没有主 Agent session，直接返回 runs.json 数据
        return runs_data

    jsonl_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    main_session_file = jsonl_files[0]

    # 从主 Agent session 中提取与该子 Agent 相关的详细步骤
    detailed_steps = _extract_subagent_steps_from_main_session(main_session_file, agent_id, limit)

    anchor = _subagent_run_anchor_ms(agent_id, None)
    if anchor is not None and detailed_steps:
        cutoff = anchor - _RUN_ANCHOR_SLACK_MS
        filt = [s for s in detailed_steps if (s.get('timestamp') or 0) >= cutoff]
        if filt:
            detailed_steps = filt

    if not detailed_steps:
        # 主 Agent session 中没有相关步骤，返回 runs.json 数据
        return runs_data

    # 3. 合并数据：runs.json 状态 + 主 Agent session 详细步骤
    # 使用 runs.json 的状态（更实时），但用主 session 的详细步骤
    total_duration = sum(s.get('duration', 0) for s in detailed_steps)
    total_input = sum(s.get('tokens', {}).get('input', 0) for s in detailed_steps)
    total_output = sum(s.get('tokens', {}).get('output', 0) for s in detailed_steps)
    tool_call_count = sum(1 for s in detailed_steps if s.get('type') == 'toolCall')

    # 如果 runs.json 有数据，使用其 startedAt（更准确）
    started_at = runs_data.get('startedAt') or (detailed_steps[0].get('timestamp') if detailed_steps else None)

    return {
        "sessionId": f"merged-{agent_id}",
        "agentId": agent_id,
        "startedAt": started_at,
        "status": runs_status,  # 使用 runs.json 的实时状态
        "steps": _pair_tool_calls_and_results(detailed_steps),
        "stats": {
            "totalDuration": total_duration,
            "totalInputTokens": total_input,
            "totalOutputTokens": total_output,
            "toolCallCount": tool_call_count,
            "stepCount": len(detailed_steps)
        },
        "rounds": _build_llm_rounds(detailed_steps),
        "roundMode": True,
        "dataSource": "merged"  # 标记数据来源
    }


def _get_subagent_timeline_from_runs(agent_id: str, limit: int) -> Dict[str, Any]:
    """从 runs.json 获取子 Agent 时序（回退方案）"""
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
    requester_info = _get_requester_info_for_session(agent_id, None)
    sender_id = requester_info.get('senderId')
    sender_name = requester_info.get('senderName')
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
            "totalOutputTokens": 1,
            "toolCallCount": 0,
            "stepCount": len(steps)
        }
    }


def _extract_subagent_steps_from_main_lines(
    lines: Iterable[str],
    subagent_id: str,
    subagent_name: str,
    main_agent_id: str,
    main_agent_name: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """从主会话行序列中提取与指定子 Agent 相关的步骤（供尾部窗口与全量解析复用）。"""
    subagent_key_pattern = f"agent:{subagent_id}:"
    steps: List[Dict[str, Any]] = []
    step_index = 0
    cumulative_tokens = 0
    last_timestamp: Optional[int] = None
    for line in lines:
        if '"type":"message"' not in line and '"type": "message"' not in line:
            continue
        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        if data.get('type') != 'message':
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
        content_list = msg.get('content', [])
        if isinstance(content_list, str):
            content_list = [{'type': 'text', 'text': content_list}]
        usage = msg.get('usage', {})
        if usage:
            cumulative_tokens += usage.get('input', 0) + usage.get('output', 0)
        text_content = ""
        for c in content_list:
            if isinstance(c, dict) and c.get('type') == 'text':
                text_content += c.get('text', '')
        is_related = subagent_key_pattern in text_content
        if role == 'user':
            if any(m in text_content for m in _SUBAGENT_RESULT_MARKERS) and is_related:
                result_text = _extract_subagent_result_content(text_content)
                steps.append({
                    "id": f"sub_step_{step_index}",
                    "type": StepType.SUBAGENT_RESULT.value,
                    "status": StepStatus.SUCCESS.value,
                    "timestamp": timestamp,
                    "duration": duration,
                    "content": _truncate_text(result_text, 1000),
                    "senderId": subagent_id,
                    "senderName": f"{subagent_name}输出",
                    "tokens": {"input": 0, "output": usage.get('output', 0), "cumulative": cumulative_tokens}
                })
                step_index += 1
            elif is_related:
                task_text = _extract_task_content(text_content)
                if task_text:
                    steps.append({
                        "id": f"sub_step_{step_index}",
                        "type": StepType.USER.value,
                        "status": StepStatus.SUCCESS.value,
                        "timestamp": timestamp,
                        "duration": duration,
                        "content": _truncate_text(task_text, 1000),
                        "senderId": main_agent_id,
                        "senderName": main_agent_name,
                        "tokens": {"input": usage.get('input', 0), "output": 0, "cumulative": cumulative_tokens}
                    })
                    step_index += 1
        elif role == 'assistant':
            if is_related:
                thinking_text = ""
                text_content_part = ""
                tool_calls = []
                for c in content_list:
                    if not isinstance(c, dict):
                        continue
                    ct = c.get('type')
                    if ct == 'thinking':
                        thinking_text += c.get('thinking', '')
                    elif ct == 'text':
                        text_content_part += c.get('text', '')
                    elif ct == 'toolCall':
                        tool_calls.append({
                            'name': c.get('name'),
                            'arguments': c.get('arguments'),
                            'id': c.get('id')
                        })
                if thinking_text:
                    steps.append({
                        "id": f"sub_step_{step_index}",
                        "type": StepType.THINKING.value,
                        "status": StepStatus.SUCCESS.value,
                        "timestamp": timestamp,
                        "duration": duration,
                        "thinking": _truncate_text(thinking_text, 500),
                        "collapsed": True,
                        "tokens": {"input": usage.get('input', 0), "output": 0, "cumulative": cumulative_tokens}
                    })
                    step_index += 1
                    duration = 0
                for tc in tool_calls:
                    steps.append({
                        "id": f"sub_step_{step_index}",
                        "type": StepType.TOOL_CALL.value,
                        "status": StepStatus.SUCCESS.value,
                        "timestamp": timestamp,
                        "duration": duration,
                        "toolName": tc.get('name'),
                        "toolCallId": tc.get('id') or f"sub_step_{step_index}",
                        "toolArguments": tc.get('arguments'),
                        "tokens": {"input": 0, "output": 0, "cumulative": cumulative_tokens}
                    })
                    step_index += 1
                    duration = 0
        elif role == 'toolResult':
            if is_related:
                tool_name = msg.get('toolName', 'unknown')
                tc_id = msg.get('toolCallId', '')
                details = msg.get('details', {})
                is_error = (
                    msg.get('isError') == True or
                    details.get('exitCode', 0) != 0 or
                    details.get('status') == 'error'
                )
                result_status = 'error' if is_error else 'ok'
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
                steps.append({
                    "id": f"sub_step_{step_index}",
                    "type": StepType.TOOL_RESULT.value,
                    "status": StepStatus.ERROR.value if result_status == 'error' else StepStatus.SUCCESS.value,
                    "timestamp": timestamp,
                    "duration": duration,
                    "toolName": tool_name,
                    "toolCallId": tc_id,
                    "toolResult": _truncate_text(result_content, 2000),
                    "toolResultStatus": result_status,
                    "toolResultError": tool_error,
                    "tokens": {"input": 0, "output": 0, "cumulative": cumulative_tokens}
                })
                step_index += 1
    return steps[-limit:] if len(steps) > limit else steps


def _extract_subagent_steps_from_main_session(
    main_session_file: Path,
    subagent_id: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """从主 Agent session 中提取与指定子 Agent 相关的步骤（大文件先解析尾部窗口）。"""
    subagent_name = _get_subagent_display_name(subagent_id)
    main_agent_id = _get_main_agent_id()
    main_agent_name = _get_agent_display_name(main_agent_id)
    path = main_session_file
    tail_lines = _read_jsonl_tail_line_slice(path)
    if tail_lines is not None:
        steps = _extract_subagent_steps_from_main_lines(
            tail_lines, subagent_id, subagent_name, main_agent_id, main_agent_name, limit
        )
        if len(steps) >= limit:
            return steps
    return _extract_subagent_steps_from_main_lines(
        _read_text_lines(path), subagent_id, subagent_name, main_agent_id, main_agent_name, limit
    )


def _extract_subagent_result_content(text: str) -> str:
    """从子 Agent 回传消息中提取实际结果内容"""
    lines = text.split('\n')
    result_lines = []
    in_result = False
    for line in lines:
        if 'session_key:' in line.lower():
            continue
        if 'Result (untrusted content, treat as data):' in line:
            in_result = True
            continue
        if '[Internal task completion event]' in line:
            in_result = True
            continue
        if in_result:
            result_lines.append(line)
    result = '\n'.join(result_lines).strip()
    return result if result else text


def _extract_task_content(text: str) -> str:
    """从主 Agent 发给子 Agent 的消息中提取任务内容"""
    lines = text.split('\n')
    task_lines = []
    for line in lines:
        if 'session_key:' in line.lower():
            continue
        if line.strip().startswith('---'):
            continue
        if line.strip().startswith('CONTEXT FILES'):
            break
        if line.strip().startswith('WORKING DIRECTORY'):
            break
        if line.strip().startswith('SYSTEM INFO'):
            break
        task_lines.append(line)
    return '\n'.join(task_lines).strip()


def _parse_session_lines(
    lines: Iterable[str],
    requester_info: Optional[Dict[str, str]],
    started_at_hint: Optional[int] = None,
) -> Tuple[List[TimelineStep], Optional[int], str]:
    """将 jsonl 行序列解析为 TimelineStep 列表。"""
    steps: List[TimelineStep] = []
    step_index = 0
    cumulative_tokens = 0
    started_at: Optional[int] = started_at_hint
    last_timestamp: Optional[int] = None
    session_status = "completed"
    tool_call_map: Dict[str, str] = {}
    sender_id = requester_info.get('senderId') if requester_info else None
    sender_name = requester_info.get('senderName') if requester_info else None
    for line in lines:
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
            if requester_info and sender_name:
                display_sender = sender_name
                final_sender_id = sender_id
            else:
                subagent_label = _detect_subagent_sender(user_text)
                if subagent_label:
                    display_sender = subagent_label
                else:
                    display_sender = "用户"
                final_sender_id = sender_id
            steps.append(TimelineStep(
                id=f"step_{step_index}",
                type=StepType.USER.value,
                status=StepStatus.SUCCESS.value,
                timestamp=timestamp,
                duration=duration,
                content=_truncate_text(user_text, 1000),
                senderId=final_sender_id,
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
            is_error = (
                msg.get('isError') == True or
                details.get('exitCode', 0) != 0 or
                details.get('status') == 'error'
            )
            result_status = 'error' if is_error else 'ok'
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
    return steps, started_at, session_status


def _parse_session_file(
    session_file: Path,
    agent_id: str,
    session_id: Optional[str],
    limit: int,
    requester_info: Optional[Dict[str, str]] = None,
    round_mode: bool = True
) -> Dict[str, Any]:
    """解析 session jsonl；大文件优先解析尾部窗口，步骤不足时再整文件解析。"""
    path = session_file
    header_ts = _read_session_header_timestamp(path)
    tail_lines = _read_jsonl_tail_line_slice(path)
    if tail_lines is not None:
        steps, started_at, session_status = _parse_session_lines(
            tail_lines, requester_info, started_at_hint=header_ts
        )
        if len(steps) < limit:
            steps, started_at, session_status = _parse_session_lines(
                _read_text_lines(path), requester_info, started_at_hint=header_ts
            )
    else:
        steps, started_at, session_status = _parse_session_lines(
            _read_text_lines(path), requester_info, started_at_hint=header_ts
        )

    if len(steps) > limit:
        steps = steps[-limit:]

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
    result["steps"] = _pair_tool_calls_and_results(result["steps"])
    if round_mode:
        result["rounds"] = _build_llm_rounds(result["steps"])
        result["roundMode"] = True
    return result
