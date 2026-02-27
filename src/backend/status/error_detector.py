"""
API 状态检测器
"""
import json
from pathlib import Path
from typing import List, Dict, Any
import time

MODEL_FAILURES_LOG = Path.home() / ".openclaw" / "workspace-main" / "memory" / "model-failures.log"


def parse_failure_log() -> List[Dict[str, Any]]:
    """解析失败日志"""
    if not MODEL_FAILURES_LOG.exists():
        return []
    
    entries = []
    with open(MODEL_FAILURES_LOG, 'r', encoding='utf-8') as f:
        content = f.read()
        
        # 解析每个条目（以 ## 开头的行）
        sections = content.split('## ')
        for section in sections[1:]:  # 跳过第一个（文件头）
            entry = {
                'timestamp': extract_timestamp(section),
                'model': extract_model(section),
                'error_type': extract_error_type(section),
                'message': extract_message(section)
            }
            if entry['model'] and entry['error_type']:
                entries.append(entry)
    
    return entries


def extract_timestamp(text: str) -> int:
    """提取时间戳"""
    import re
    match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', text)
    if match:
        try:
            from datetime import datetime
            dt = datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
            return int(dt.timestamp() * 1000)
        except:
            pass
    return 0


def extract_model(text: str) -> str:
    """提取模型"""
    import re
    match = re.search(r'(glm-\d+(\.\d+)?|qwen\S*)', text)
    return match.group(1) if match else ''


def extract_error_type(text: str) -> str:
    """提取错误类型"""
    text_lower = text.lower()
    
    if '429' in text or 'rate limit' in text_lower:
        return 'rate-limit'
    elif 'timeout' in text_lower or '超时' in text_lower:
        return 'timeout'
    elif '降级' in text:
        return 'downgrade'
    else:
        return 'unknown'


def extract_message(text: str) -> str:
    """提取错误消息"""
    lines = text.split('\n')
    for line in lines:
        if '错误类型' in line or 'error' in line.lower():
            return line.strip()
    return ''


def get_api_status() -> List[Dict[str, Any]]:
    """获取 API 状态"""
    failures = parse_failure_log()
    
    # 按 provider/model 分组
    status_map = {}
    
    for failure in failures:
        model = failure['model']
        if model not in status_map:
            status_map[model] = {
                'model': model,
                'status': 'healthy',
                'lastError': None,
                'errorCount': 0
            }
        
        status_map[model]['errorCount'] += 1
        
        # 检查是否最近5分钟有错误
        if failure['timestamp'] > int(time.time() * 1000) - 300000:
            status_map[model]['status'] = 'degraded'
            if not status_map[model]['lastError']:
                status_map[model]['lastError'] = {
                    'type': failure['error_type'],
                    'message': failure['message'],
                    'timestamp': failure['timestamp']
                }
    
    return list(status_map.values())
