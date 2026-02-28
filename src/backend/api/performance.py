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
                    data = json.loads(line)
                    if data.get('type') != 'message':
                        continue
                    msg = data.get('message', {})
                    if not msg:
                        continue
                    
                    msg_id = data.get('id', '')
                    id_to_msg[msg_id] = {'data': data, 'msg': msg}
                    
                    if msg.get('role') != 'assistant':
                        continue
                    if 'usage' not in msg:
                        continue
                    
                    try:
                        ts = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
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
        print(f"解析 session 详情失败 {session_path}: {e}")
        return []


def parse_session_file(session_path: Path) -> List[Dict]:
    """解析单个 session 文件，提取每条消息的 token 统计"""
    messages = []
    
    try:
        with open(session_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    
                    # 只处理有 usage 和 timestamp 的消息
                    if 'message' in data and 'usage' in data['message'] and 'timestamp' in data:
                        usage = data['message']['usage']
                        tokens = usage.get('totalTokens', 0) or 0
                        is_request = data.get('message', {}).get('role') == 'assistant'
                        
                        try:
                            timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
                            
                            # 只统计最近1小时的消息
                            now = datetime.now(timezone.utc)
                            one_hour_ago = now - timedelta(hours=1)
                            
                            if timestamp >= one_hour_ago:
                                messages.append({
                                    'timestamp': timestamp,
                                    'tokens': tokens,
                                    'is_request': is_request
                                })
                        except:
                            pass
                except:
                    continue
        
        return messages
    except Exception as e:
        print(f"解析 session 文件失败 {session_path}: {e}")
        return []


@router.get("/performance")
async def get_performance_stats(range: str = "20m"):
    """获取性能统计
    
    Args:
        range: 时间范围 (20m, 1h)
    """
    import time
    start = time.perf_counter()
    range_minutes = {
        "20m": 20,
        "1h": 60
    }.get(range, 20)
    
    stats = await get_real_stats(range_minutes)
    # 接口处理耗时作为延迟参考（毫秒）
    stats['current']['latency'] = int((time.perf_counter() - start) * 1000)
    return stats


async def get_real_stats(range_minutes: int = 20) -> Dict:
    """获取真实的 TPM/RPM 统计
    
    Args:
        range_minutes: 时间范围（分钟）
    """
    stats = {
        'current': {
            'tpm': 0,
            'rpm': 0,
            'latency': 0,
            'errorRate': 0.0
        },
        'history': {
            'tpm': [],
            'rpm': [],
            'timestamps': []
        },
        'total': {
            'tokens': 0,
            'requests': 0
        }
    }
    
    # 读取所有 session 文件
    openclaw_path = Path.home() / '.openclaw'
    agents_path = openclaw_path / 'agents'
    
    if not agents_path.exists():
        return stats
    
    # 按分钟统计
    minutes_stats = {}
    
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
            messages = parse_session_file(session_file)
            
            # 按分钟逐条累加
            for msg in messages:
                minute_key = msg['timestamp'].strftime('%Y-%m-%d %H:%M')
                
                if minute_key not in minutes_stats:
                    minutes_stats[minute_key] = {
                        'tokens': 0,
                        'requests': 0
                    }
                
                minutes_stats[minute_key]['tokens'] += msg['tokens']
                if msg['is_request']:
                    minutes_stats[minute_key]['requests'] += 1
    
    # 排序并转换为列表
    sorted_minutes = sorted(minutes_stats.items())
    
    # 填充最近 range_minutes 分钟的数据（缺失的分钟补0）
    timestamps = []
    tpm_data = []
    rpm_data = []
    
    now = datetime.now(timezone.utc)
    for i in range(range_minutes):
        minute_time = now - timedelta(minutes=(range_minutes - i - 1))
        minute_key = minute_time.strftime('%Y-%m-%d %H:%M')
        
        # 发送 Unix 时间戳(毫秒)，前端可正确转换为本地时区
        timestamps.append(int(minute_time.timestamp() * 1000))
        
        if minute_key in minutes_stats:
            tpm_data.append(minutes_stats[minute_key]['tokens'])
            rpm_data.append(minutes_stats[minute_key]['requests'])
        else:
            tpm_data.append(0)
            rpm_data.append(0)
    
    stats['history']['tpm'] = tpm_data
    stats['history']['rpm'] = rpm_data
    stats['history']['timestamps'] = timestamps
    
    # 当前分钟的统计
    current_minute = now.strftime('%Y-%m-%d %H:%M')
    if current_minute in minutes_stats:
        stats['current']['tpm'] = minutes_stats[current_minute]['tokens']
        stats['current']['rpm'] = minutes_stats[current_minute]['requests']
    else:
        stats['current']['tpm'] = 0
        stats['current']['rpm'] = 0

    # 总计（基于历史数据）
    total_tokens = sum([s['tokens'] for s in minutes_stats.values()])
    total_requests = sum([s['requests'] for s in minutes_stats.values()])
    
    stats['total']['tokens'] = total_tokens
    stats['total']['requests'] = total_requests
    
    return stats


async def get_minute_details(timestamp_ms: int) -> Dict[str, Any]:
    """获取指定分钟的调用详情，用于柱体点击钻取。时间展示使用 Asia/Shanghai 时区"""
    try:
        ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        ts_local = ts.astimezone(TZ_DISPLAY)
        minute_key = ts_local.strftime('%Y-%m-%d %H:%M')
        minute_start = ts.replace(second=0, microsecond=0)
        minute_end = minute_start + timedelta(minutes=1)
        
        openclaw_path = Path.home() / '.openclaw'
        agents_path = openclaw_path / 'agents'
        if not agents_path.exists():
            return {'minute': minute_key, 'calls': [], 'totalTokens': 0}
        
        all_calls = []
        for agent_dir in agents_path.iterdir():
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            sessions_path = agent_dir / 'sessions'
            if not sessions_path.exists():
                continue
            
            for session_file in sessions_path.glob('*.jsonl'):
                if 'lock' in session_file.name or 'deleted' in session_file.name:
                    continue
                records = parse_session_file_with_details(session_file, agent_id)
                for r in records:
                    if minute_start <= r['timestamp'] < minute_end:
                        # 转为 Asia/Shanghai 时区展示
                        r_ts = r['timestamp']
                        if r_ts.tzinfo is None:
                            r_ts = r_ts.replace(tzinfo=timezone.utc)
                        r_local = r_ts.astimezone(TZ_DISPLAY)
                        all_calls.append({
                            'agentId': r['agentId'],
                            'sessionId': r['sessionId'],
                            'model': r['model'],
                            'tokens': r['tokens'],
                            'trigger': r['trigger'],
                            'inputTokens': r.get('inputTokens', 0),
                            'outputTokens': r.get('outputTokens', 0),
                            'time': r_local.strftime('%H:%M:%S')
                        })
        
        all_calls.sort(key=lambda x: x['time'])
        total_tokens = sum(c['tokens'] for c in all_calls)
        return {
            'minute': minute_key,
            'calls': all_calls,
            'totalCalls': len(all_calls),
            'totalTokens': total_tokens
        }
    except Exception as e:
        print(f"获取分钟详情失败: {e}")
        import traceback
        traceback.print_exc()
        return {'minute': '', 'calls': [], 'totalTokens': 0}


@router.get("/performance/details")
async def get_performance_details(timestamp: int):
    """获取指定分钟的 TPM/RPM 调用详情（柱体点击钻取）
    
    Args:
        timestamp: 分钟起始的 Unix 毫秒时间戳
    """
    return await get_minute_details(timestamp)
