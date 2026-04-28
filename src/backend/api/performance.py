"""
性能监控 - 真实 TPM/RPM 统计（逐条消息解析）
支持按分钟查看调用详情，便于分析调用瓶颈
"""
from fastapi import APIRouter
from typing import List, Dict, Any, Optional
import json
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from data.session_reader import normalize_sessions_index, _load_sessions_index_file
from core.error_handler import record_error
from utils.data_repair import parse_session_jsonl_line

# 详情展示使用 Asia/Shanghai 时区
TZ_DISPLAY = ZoneInfo('Asia/Shanghai')

router = APIRouter()


def _extract_trigger_text(msg: Dict) -> str:
    """从消息中提取触发内容（完整展示）"""
    content = msg.get('content') or []
    if isinstance(content, str):
        return content.replace('\n', ' ')
    if not isinstance(content, list):
        return ''
    for item in content:
        if isinstance(item, dict):
            if item.get('type') == 'text' and item.get('text'):
                text = str(item['text'])
                if '[Subagent Task]' in text:
                    m = re.search(r'\*\*任务[：:]\s*(.+?)\*\*', text)
                    if m:
                        return f"子任务: {m.group(1).strip()}"
                return text.replace('\n', ' ')
            if item.get('type') == 'toolCall':
                return f"工具调用: {item.get('name', '?')}"
    return ''


def _extract_tool_call_detail(msg: Dict, tool_call_id: str) -> str:
    """从 assistant 消息的 content 中提取 toolCall 的 arguments 详情"""
    content = msg.get('content') or []
    if not isinstance(content, list):
        return ''
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get('type') == 'toolCall' and item.get('id') == tool_call_id:
            name = item.get('name', '')
            args = item.get('arguments') or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if not isinstance(args, dict):
                args = {}
            if name == 'exec' and args:
                cmd = args.get('command', '')
                if cmd:
                    return f"exec: {cmd}"
            if name == 'read' and args:
                path = args.get('path', '')
                if path:
                    return f"read: {path}"
            if name == 'write' and args:
                path = args.get('path', '')
                if path:
                    return f"write: {path}"
            if name == 'process' and args:
                action = args.get('action', '')
                sid = args.get('sessionId', '')
                if action and sid:
                    return f"process: {action} ({sid})"
                if action:
                    return f"process: {action}"
            if name == 'sessions_spawn' and args:
                task = (args.get('task') or '').replace(chr(10), ' ')
                agent = args.get('agentId', '')
                if task and agent:
                    return f"sessions_spawn: {agent} - {task}"
                if agent:
                    return f"sessions_spawn: {agent}"
            # 其他工具：显示完整 arguments
            if args:
                try:
                    s = json.dumps(args, ensure_ascii=False)
                    return f"{name}: {s}"
                except Exception:
                    pass
            return f"工具: {name}"
    return ''


def parse_session_file_with_details(session_path: Path, agent_id: str) -> List[Dict]:
    """解析 session，返回带详情的 API 调用记录（assistant 消息）"""
    records = []
    id_to_msg = {}
    
    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data, msg = parse_session_jsonl_line(line)
                    if not data or data.get('type') != 'message' or not msg:
                        continue

                    msg_id = data.get('id', '')
                    id_to_msg[msg_id] = {'data': data, 'msg': msg}

                    if msg.get('role') != 'assistant':
                        continue
                    if 'usage' not in msg:
                        continue

                    ts_raw = data.get('timestamp')
                    if not ts_raw:
                        continue
                    try:
                        ts = datetime.fromisoformat(str(ts_raw).replace('Z', '+00:00'))
                    except Exception:
                        continue
                    
                    usage = msg.get('usage', {})
                    tokens = usage.get('totalTokens', 0) or 0
                    model = msg.get('model', '')
                    
                    trigger = ''
                    parent_id = data.get('parentId')
                    if parent_id and parent_id in id_to_msg:
                        parent = id_to_msg[parent_id]['msg']
                        parent_role = parent.get('role', '')
                        if parent_role == 'user':
                            trigger = _extract_trigger_text(parent)
                        elif parent_role == 'toolResult':
                            tool = parent.get('toolName', '') or (parent.get('details') or {}).get('tool', '?')
                            tool_call_id = parent.get('toolCallId', '')
                            # 从 toolResult 的 parent（发起调用的 assistant）获取 toolCall 详情
                            parent_data = id_to_msg.get(parent_id, {})
                            parent_of_tr = parent_data.get('data', {})
                            tr_parent_id = parent_of_tr.get('parentId', '')
                            if tool_call_id and tr_parent_id and tr_parent_id in id_to_msg:
                                detail = _extract_tool_call_detail(id_to_msg[tr_parent_id]['msg'], tool_call_id)
                                # 重要：这是 toolResult 触发的消息，即工具执行完成后的回传，不是工具调用本身
                                # 【完成回传】前缀醒目，因果顺序：派发 → 子Agent执行 → 完成回传
                                trigger = f"【完成回传】{detail}" if detail else f"【完成回传】工具: {tool}"
                            else:
                                trigger = f"【完成回传】工具: {tool}"
                    
                    records.append({
                        'timestamp': ts,
                        'tokens': tokens,
                        'agentId': agent_id,
                        'sessionId': session_path.stem,
                        'model': model,
                        'trigger': trigger or '(用户输入)',
                        'inputTokens': usage.get('input', 0),
                        'outputTokens': usage.get('output', 0)
                    })
                except Exception:
                    continue
        return records
    except Exception as e:
        record_error("io-error", f"{session_path}: {e}", "performance:parse_session_details", exc=e)
        return []


def parse_session_file(session_path: Path, range_hours: int = 1) -> List[Dict]:
    """解析单个 session 文件，提取每条消息的 token 统计

    Args:
        session_path: session 文件路径
        range_hours: 时间范围（小时），0 表示不限制
    """
    messages = []

    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    envelope, msg = parse_session_jsonl_line(line)
                    if (
                        not envelope
                        or envelope.get('type') != 'message'
                        or not msg
                        or 'usage' not in msg
                        or not envelope.get('timestamp')
                    ):
                        continue
                    usage = msg['usage']
                    tokens = usage.get('totalTokens', 0) or 0
                    is_request = msg.get('role') == 'assistant'

                    try:
                        timestamp = datetime.fromisoformat(
                            str(envelope['timestamp']).replace('Z', '+00:00')
                        )

                        if range_hours > 0:
                            now = datetime.now(timezone.utc)
                            time_ago = now - timedelta(hours=range_hours)
                            if timestamp < time_ago:
                                continue

                        messages.append({
                            'timestamp': timestamp,
                            'tokens': tokens,
                            'is_request': is_request
                        })
                    except Exception:
                        pass
                except Exception:
                    continue

        return messages
    except Exception as e:
        record_error("io-error", f"{session_path}: {e}", "performance:parse_session_file", exc=e)
        return []


@router.get("/performance")
async def get_performance_stats(range: str = "20m"):
    """获取性能统计

    Args:
        range: 时间范围 (20m, 1h, 24h)
    """
    range_config = {
        "20m": {"minutes": 20, "hours": 1, "granularity": "minute"},
        "1h": {"minutes": 60, "hours": 1, "granularity": "minute"},
        "24h": {"minutes": 1440, "hours": 24, "granularity": "hour"}
    }

    config = range_config.get(range, range_config["20m"])
    stats = await get_real_stats(config["minutes"], config["hours"], config["granularity"])
    return stats


async def get_real_stats(range_minutes: int = 20, range_hours: int = 1, granularity: str = "minute") -> Dict:
    """获取真实的 TPM/RPM 统计

    Args:
        range_minutes: 时间范围（分钟）
        range_hours: 用于解析 session 的时间范围（小时）
        granularity: 聚合粒度 (minute, hour)
    """
    stats = {
        'current': {
            'tpm': 0,
            'rpm': 0,
            'windowTotal': {
                'tokens': 0,
                'requests': 0
            }
        },
        'history': {
            'tpm': [],
            'rpm': [],
            'timestamps': []
        },
        'statistics': {
            'avgTpm': 0,
            'peakTpm': 0,
            'peakTime': ''
        }
    }

    # 使用环境变量或默认路径
    openclaw_path = _openclaw_path()
    agents_path = openclaw_path / 'agents'

    if not agents_path.exists():
        return stats

    # 按时间槽统计（分钟或小时）
    time_slot_stats = {}

    # 扫描所有 agent 的 sessions
    for agent_dir in agents_path.iterdir():
        if not agent_dir.is_dir():
            continue

        sessions_path = agent_dir / 'sessions'
        if not sessions_path.exists():
            continue

        # 扫描所有 .jsonl 文件
        for session_file in sessions_path.glob('*.jsonl'):
            # 跳过 lock 和 deleted 文件
            if 'lock' in session_file.name or 'deleted' in session_file.name:
                continue

            # 解析 session 文件，获取所有消息
            messages = parse_session_file(session_file, range_hours)

            # 按时间槽逐条累加
            for msg in messages:
                if granularity == "hour":
                    slot_key = msg['timestamp'].strftime('%Y-%m-%d %H:00')
                else:
                    slot_key = msg['timestamp'].strftime('%Y-%m-%d %H:%M')

                if slot_key not in time_slot_stats:
                    time_slot_stats[slot_key] = {
                        'tokens': 0,
                        'requests': 0
                    }

                time_slot_stats[slot_key]['tokens'] += msg['tokens']
                if msg['is_request']:
                    time_slot_stats[slot_key]['requests'] += 1

    # 填充时间槽数据
    timestamps = []
    tpm_data = []
    rpm_data = []
    now = datetime.now(timezone.utc)

    if granularity == "hour":
        # 24h 模式：24 个小时槽
        for i in range(24):
            hour_time = now - timedelta(hours=(23 - i))
            slot_key = hour_time.strftime('%Y-%m-%d %H:00')
            timestamps.append(int(hour_time.timestamp() * 1000))

            if slot_key in time_slot_stats:
                tpm_data.append(time_slot_stats[slot_key]['tokens'])
                rpm_data.append(time_slot_stats[slot_key]['requests'])
            else:
                tpm_data.append(0)
                rpm_data.append(0)
    else:
        # 20m / 1h 模式：分钟槽
        for i in range(range_minutes):
            minute_time = now - timedelta(minutes=(range_minutes - i - 1))
            slot_key = minute_time.strftime('%Y-%m-%d %H:%M')
            timestamps.append(int(minute_time.timestamp() * 1000))

            if slot_key in time_slot_stats:
                tpm_data.append(time_slot_stats[slot_key]['tokens'])
                rpm_data.append(time_slot_stats[slot_key]['requests'])
            else:
                tpm_data.append(0)
                rpm_data.append(0)

    stats['history']['tpm'] = tpm_data
    stats['history']['rpm'] = rpm_data
    stats['history']['timestamps'] = timestamps

    # 当前时间槽的统计
    if granularity == "hour":
        current_slot = now.strftime('%Y-%m-%d %H:00')
    else:
        current_slot = now.strftime('%Y-%m-%d %H:%M')

    if current_slot in time_slot_stats:
        stats['current']['tpm'] = time_slot_stats[current_slot]['tokens']
        stats['current']['rpm'] = time_slot_stats[current_slot]['requests']

    # 时间窗口总计
    stats['current']['windowTotal']['tokens'] = sum(tpm_data)
    stats['current']['windowTotal']['requests'] = sum(rpm_data)

    # 统计摘要
    non_zero_tpm = [t for t in tpm_data if t > 0]
    if non_zero_tpm:
        stats['statistics']['avgTpm'] = int(sum(non_zero_tpm) / len(non_zero_tpm))
        stats['statistics']['peakTpm'] = max(non_zero_tpm)
        peak_idx = tpm_data.index(max(non_zero_tpm))
        # 格式化峰值时间
        peak_ts = datetime.fromtimestamp(timestamps[peak_idx] / 1000, tz=TZ_DISPLAY)
        if granularity == "hour":
            stats['statistics']['peakTime'] = peak_ts.strftime('%H:00')
        else:
            stats['statistics']['peakTime'] = peak_ts.strftime('%H:%M')

    return stats


async def get_minute_details(
    timestamp_ms: int,
    granularity: str = "minute",
    agent: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "tokens_desc",
    limit: int = 50
) -> Dict[str, Any]:
    """获取指定时间窗口的调用详情，用于柱体点击钻取。时间展示使用 Asia/Shanghai 时区

    Args:
        timestamp_ms: Unix 毫秒时间戳
        granularity: 粒度 (minute, hour)
        agent: 筛选指定 Agent
        search: 搜索触发内容
        sort: 排序方式 (tokens_desc, tokens_asc, time_asc, time_desc)
        limit: 返回数量限制
    """
    try:
        ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        ts_local = ts.astimezone(TZ_DISPLAY)

        if granularity == "hour":
            time_key = ts_local.strftime('%Y-%m-%d %H:00')
            time_start = ts.replace(minute=0, second=0, microsecond=0)
            time_end = time_start + timedelta(hours=1)
        else:
            time_key = ts_local.strftime('%Y-%m-%d %H:%M')
            time_start = ts.replace(second=0, microsecond=0)
            time_end = time_start + timedelta(minutes=1)

        openclaw_path = _openclaw_path()
        agents_path = openclaw_path / 'agents'
        if not agents_path.exists():
            return {'timeWindow': time_key, 'calls': [], 'totalCalls': 0, 'totalTokens': 0, 'summary': {'avgTokens': 0}, 'agents': []}

        all_calls = []
        agent_set = set()

        for agent_dir in agents_path.iterdir():
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            agent_set.add(agent_id)

            # 如果指定了 agent 筛选，跳过不匹配的
            if agent and agent_id != agent:
                continue

            sessions_path = agent_dir / 'sessions'
            if not sessions_path.exists():
                continue

            for session_file in sessions_path.glob('*.jsonl'):
                if 'lock' in session_file.name or 'deleted' in session_file.name:
                    continue
                records = parse_session_file_with_details(session_file, agent_id)
                for r in records:
                    if time_start <= r['timestamp'] < time_end:
                        # 转为 Asia/Shanghai 时区展示
                        r_ts = r['timestamp']
                        if r_ts.tzinfo is None:
                            r_ts = r_ts.replace(tzinfo=timezone.utc)
                        r_local = r_ts.astimezone(TZ_DISPLAY)

                        call_item = {
                            'agentId': r['agentId'],
                            'sessionId': r['sessionId'],
                            'model': r['model'],
                            'tokens': r['tokens'],
                            'trigger': r['trigger'],
                            'inputTokens': r.get('inputTokens', 0),
                            'outputTokens': r.get('outputTokens', 0),
                            'time': r_local.strftime('%H:%M:%S'),
                            'timestamp': int(r_ts.timestamp() * 1000)
                        }

                        # 如果指定了搜索关键词，过滤触发内容
                        if search:
                            if search.lower() not in call_item['trigger'].lower():
                                continue

                        all_calls.append(call_item)

        # 排序
        if sort == "tokens_desc":
            all_calls.sort(key=lambda x: x['tokens'], reverse=True)
        elif sort == "tokens_asc":
            all_calls.sort(key=lambda x: x['tokens'])
        elif sort == "time_asc":
            all_calls.sort(key=lambda x: x['timestamp'])
        elif sort == "time_desc":
            all_calls.sort(key=lambda x: x['timestamp'], reverse=True)

        # 计算统计信息
        total_tokens = sum(c['tokens'] for c in all_calls)
        avg_tokens = int(total_tokens / len(all_calls)) if all_calls else 0

        # 分页
        total_count = len(all_calls)
        paginated_calls = all_calls[:limit]

        return {
            'timeWindow': time_key,
            'calls': paginated_calls,
            'totalCalls': total_count,
            'totalTokens': total_tokens,
            'summary': {
                'avgTokens': avg_tokens
            },
            'agents': sorted(list(agent_set)),
            'pagination': {
                'total': total_count,
                'limit': limit,
                'hasMore': total_count > limit
            }
        }
    except Exception as e:
        record_error("unknown", str(e), "performance:get_minute_details", exc=e)
        return {'timeWindow': '', 'calls': [], 'totalCalls': 0, 'totalTokens': 0, 'summary': {'avgTokens': 0}, 'agents': [], 'pagination': {'total': 0, 'limit': limit, 'hasMore': False}}


@router.get("/performance/details")
async def get_performance_details(
    timestamp: int,
    granularity: str = "minute",
    agent: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "tokens_desc",
    limit: int = 50
):
    """获取指定时间窗口的调用详情（柱体点击钻取）

    Args:
        timestamp: 时间窗口起始的 Unix 毫秒时间戳
        granularity: 粒度 (minute, hour)
        agent: 筛选指定 Agent
        search: 搜索触发内容
        sort: 排序方式 (tokens_desc, tokens_asc, time_asc, time_desc)
        limit: 返回数量限制
    """
    return await get_minute_details(timestamp, granularity, agent, search, sort, limit)


def _openclaw_path() -> Path:
    from data.config_reader import get_openclaw_root
    return get_openclaw_root()


@router.get("/tokens/analysis")
async def get_tokens_analysis(range: str = "all"):
    """
    Token 分析视图：按 agent、按 session 汇总 usage

    Args:
        range: 时间范围 (20m, 1h, 24h, all)

    数据来源：sessions.json (inputTokens, outputTokens, cacheRead, cacheWrite)
    """
    # 保存参数避免与 Python 内置 range() 冲突
    time_range = range
    openclaw_path = _openclaw_path()
    agents_path = openclaw_path / 'agents'

    # 默认定价 (Claude 3.5 Sonnet)
    PRICING = {
        'inputPrice': 3.00,      # 每 1M Token
        'outputPrice': 15.00,
        'cacheReadPrice': 0.30,
        'cacheWritePrice': 3.75
    }

    result = {
        "summary": {
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0,
            "total": 0,
            "cacheHitRate": 0.0
        },
        "cost": {
            "input": 0.0,
            "output": 0.0,
            "cacheRead": 0.0,
            "cacheWrite": 0.0,
            "total": 0.0,
            "saved": 0.0,
            "savedPercent": 0.0
        },
        "byAgent": [],
        "trend": None
    }

    if not agents_path.exists():
        return result

    # 确定是否需要趋势数据
    need_trend = time_range in ('20m', '1h', '24h')
    trend_data = {"timestamps": [], "input": [], "output": []} if need_trend else None

    if need_trend:
        # 从 jsonl 文件计算带时间范围的统计
        now = datetime.now(timezone.utc)
        if time_range == '20m':
            time_ago = now - timedelta(minutes=20)
            granularity = 'minute'
            num_slots = 20
        elif time_range == '1h':
            time_ago = now - timedelta(hours=1)
            granularity = 'minute'
            num_slots = 60
        else:  # 24h
            time_ago = now - timedelta(hours=24)
            granularity = 'hour'
            num_slots = 24

        # 初始化时间槽数据
        slot_stats = {}
        for i in range(num_slots):
            if granularity == 'hour':
                slot_time = now - timedelta(hours=(num_slots - i - 1))
                slot_key = slot_time.strftime('%Y-%m-%d %H:00')
            else:
                slot_time = now - timedelta(minutes=(num_slots - i - 1))
                slot_key = slot_time.strftime('%Y-%m-%d %H:%M')
            slot_stats[slot_key] = {
                'timestamp': int(slot_time.timestamp() * 1000),
                'input': 0,
                'output': 0,
                'cacheRead': 0,
                'cacheWrite': 0
            }

        agent_totals = {}

        for agent_dir in agents_path.iterdir():
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            sessions_path = agent_dir / 'sessions'
            if not sessions_path.exists():
                continue

            agent_totals[agent_id] = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}

            for session_file in sessions_path.glob('*.jsonl'):
                if 'lock' in session_file.name or 'deleted' in session_file.name:
                    continue

                try:
                    with open(session_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            try:
                                envelope, msg = parse_session_jsonl_line(line)
                                if (
                                    envelope is None
                                    or envelope.get('type') != 'message'
                                    or msg is None
                                ):
                                    continue
                                if msg.get('role') != 'assistant' or 'usage' not in msg:
                                    continue

                                ts_raw = envelope.get('timestamp') or msg.get('timestamp')
                                ts = None
                                if isinstance(ts_raw, (int, float)):
                                    v = float(ts_raw)
                                    ts = datetime.fromtimestamp(
                                        (v / 1000.0) if v > 1e12 else v, tz=timezone.utc
                                    )
                                elif isinstance(ts_raw, str):
                                    try:
                                        ts = datetime.fromisoformat(
                                            ts_raw.replace('Z', '+00:00')
                                        )
                                        if ts.tzinfo is None:
                                            ts = ts.replace(tzinfo=timezone.utc)
                                    except ValueError:
                                        ts = None
                                if ts is None or ts < time_ago:
                                    continue

                                usage = msg['usage']
                                inp = usage.get('input', 0) or 0
                                out = usage.get('output', 0) or 0
                                cr = usage.get('cacheRead', 0) or 0
                                cw = usage.get('cacheWrite', 0) or 0

                                # 确定时间槽
                                if granularity == 'hour':
                                    slot_key = ts.strftime('%Y-%m-%d %H:00')
                                else:
                                    slot_key = ts.strftime('%Y-%m-%d %H:%M')

                                if slot_key in slot_stats:
                                    slot_stats[slot_key]['input'] += inp
                                    slot_stats[slot_key]['output'] += out
                                    slot_stats[slot_key]['cacheRead'] += cr
                                    slot_stats[slot_key]['cacheWrite'] += cw

                                agent_totals[agent_id]["input"] += inp
                                agent_totals[agent_id]["output"] += out
                                agent_totals[agent_id]["cacheRead"] += cr
                                agent_totals[agent_id]["cacheWrite"] += cw
                            except:
                                continue
                except:
                    continue

        # 汇总趋势数据
        sorted_slots = sorted(slot_stats.items())
        trend_data = {
            "timestamps": [s[1]['timestamp'] for s in sorted_slots],
            "input": [s[1]['input'] for s in sorted_slots],
            "output": [s[1]['output'] for s in sorted_slots]
        }

        # 汇总 agent 数据
        for agent_id, totals in agent_totals.items():
            total_tokens = totals["input"] + totals["output"]
            if total_tokens > 0:
                result["byAgent"].append({
                    "agent": agent_id,
                    "input": totals["input"],
                    "output": totals["output"],
                    "cacheRead": totals["cacheRead"],
                    "cacheWrite": totals["cacheWrite"],
                    "total": total_tokens
                })
            result["summary"]["input"] += totals["input"]
            result["summary"]["output"] += totals["output"]
            result["summary"]["cacheRead"] += totals["cacheRead"]
            result["summary"]["cacheWrite"] += totals["cacheWrite"]
    else:
        # 从 sessions.json 读取全部数据
        for agent_dir in agents_path.iterdir():
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            sessions_index = agent_dir / 'sessions' / 'sessions.json'
            if not sessions_index.exists():
                continue

            try:
                data = _load_sessions_index_file(sessions_index)
                if not data:
                    continue

                agent_total = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
                index_map = normalize_sessions_index(data)
                for session_key, entry in index_map.items():
                    if not isinstance(entry, dict):
                        continue
                    inp = entry.get('inputTokens', 0) or 0
                    out = entry.get('outputTokens', 0) or 0
                    cr = entry.get('cacheRead', 0) or 0
                    cw = entry.get('cacheWrite', 0) or 0
                    agent_total["input"] += inp
                    agent_total["output"] += out
                    agent_total["cacheRead"] += cr
                    agent_total["cacheWrite"] += cw

                agent_total_tokens = agent_total["input"] + agent_total["output"]
                result["byAgent"].append({
                    "agent": agent_id,
                    "input": agent_total["input"],
                    "output": agent_total["output"],
                    "cacheRead": agent_total["cacheRead"],
                    "cacheWrite": agent_total["cacheWrite"],
                    "total": agent_total_tokens
                })

                result["summary"]["input"] += agent_total["input"]
                result["summary"]["output"] += agent_total["output"]
                result["summary"]["cacheRead"] += agent_total["cacheRead"]
                result["summary"]["cacheWrite"] += agent_total["cacheWrite"]
            except Exception as e:
                record_error("unknown", str(e), "performance:tokens_analysis_agent", exc=e)
                continue

    # 计算汇总
    result["summary"]["total"] = result["summary"]["input"] + result["summary"]["output"]

    # 计算缓存命中率
    total_input = result["summary"]["input"] + result["summary"]["cacheRead"]
    if total_input > 0:
        result["summary"]["cacheHitRate"] = round(result["summary"]["cacheRead"] / total_input, 4)

    # 计算成本
    def calc_cost(tokens: int, price_per_m: float) -> float:
        return round((tokens / 1_000_000) * price_per_m, 4)

    result["cost"]["input"] = calc_cost(result["summary"]["input"], PRICING['inputPrice'])
    result["cost"]["output"] = calc_cost(result["summary"]["output"], PRICING['outputPrice'])
    result["cost"]["cacheRead"] = calc_cost(result["summary"]["cacheRead"], PRICING['cacheReadPrice'])
    result["cost"]["cacheWrite"] = calc_cost(result["summary"]["cacheWrite"], PRICING['cacheWritePrice'])
    result["cost"]["total"] = round(
        result["cost"]["input"] + result["cost"]["output"] +
        result["cost"]["cacheRead"] + result["cost"]["cacheWrite"], 4
    )

    # 计算节省金额（如果不用缓存，这些 input 要按原价付费）
    saved_by_cache = calc_cost(result["summary"]["cacheRead"], PRICING['inputPrice']) - result["cost"]["cacheRead"]
    result["cost"]["saved"] = round(saved_by_cache, 4)

    # 节省百分比
    if result["cost"]["total"] > 0:
        result["cost"]["savedPercent"] = round(saved_by_cache / (result["cost"]["total"] + saved_by_cache), 4)

    # 按 total 降序排序 byAgent
    result["byAgent"].sort(key=lambda x: x["total"], reverse=True)

    # 计算占比
    grand_total = result["summary"]["total"]
    if grand_total > 0:
        for agent in result["byAgent"]:
            agent["percent"] = round(agent["total"] / grand_total, 4)

    # 添加趋势数据
    if trend_data:
        result["trend"] = trend_data

    return result
