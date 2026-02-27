"""
性能监控 - 真实 TPM/RPM 统计（逐条消息解析）
"""
from fastapi import APIRouter
from typing import List, Dict
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

router = APIRouter()


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
    # 将 range 转换为分钟数
    range_minutes = {
        "20m": 20,
        "1h": 60
    }.get(range, 20)
    
    stats = await get_real_stats(range_minutes)
    return stats


async def get_real_stats(range_minutes: int = 20) -> Dict:
    """获取真实的 TPM/RPM 统计
    
    Args:
        range_minutes: 时间范围（分钟）
    """
    stats = {
        'current': {
            'tpm': 0,
            'rpm': 0
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
        
        timestamps.append(minute_time.strftime('%H:%M'))
        
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
