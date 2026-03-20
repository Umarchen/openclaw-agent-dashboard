"""
状态缓存 - 缓存 Agent 状态计算结果
通过缓存减少重复的文件读取操作，提升状态计算性能
"""
import threading
import time
from typing import Dict, Any, Optional


class StatusCache:
    """Agent 状态缓存（线程安全）
    
    功能：
    - 缓存 Agent 状态计算结果
    - TTL 机制自动过期
    - 文件变更时主动失效缓存
    - 线程安全（使用锁保护）
    - 最大条目数限制，超出时清理最旧条目
    """
    
    def __init__(self, ttl_ms: int = 1000, max_size: int = 100):
        """
        初始化缓存
        
        Args:
            ttl_ms: 缓存过期时间（毫秒），默认 1 秒
            max_size: 最大条目数，超出时清理最旧条目，默认 100
        """
        self.ttl_ms = ttl_ms
        self.max_size = max_size
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def get(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        获取缓存的状态
        
        Args:
            agent_id: Agent ID
            
        Returns:
            缓存的状态数据，未命中或已过期返回 None
        """
        with self._lock:
            entry = self._cache.get(agent_id)
            if not entry:
                return None
            
            # 检查是否过期
            now = time.time() * 1000
            if now - entry['_timestamp'] > self.ttl_ms:
                del self._cache[agent_id]
                return None
            
            # 返回状态数据（不包含元数据）
            return {k: v for k, v in entry.items() if not k.startswith('_')}
    
    def set(self, agent_id: str, data: Dict[str, Any]) -> None:
        """
        设置缓存
        
        Args:
            agent_id: Agent ID
            data: 状态数据
        """
        with self._lock:
            # 限制缓存大小：超出时删除最旧的条目
            if len(self._cache) >= self.max_size and agent_id not in self._cache:
                oldest_key = min(
                    self._cache.keys(),
                    key=lambda k: self._cache[k].get('_timestamp', 0)
                )
                del self._cache[oldest_key]
            
            self._cache[agent_id] = {
                **data,
                '_timestamp': time.time() * 1000
            }
    
    def invalidate(self, agent_id: Optional[str] = None) -> None:
        """
        失效缓存
        
        Args:
            agent_id: 指定 Agent ID，None 表示清空所有
        """
        with self._lock:
            if agent_id:
                self._cache.pop(agent_id, None)
            else:
                self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            {'size': int, 'ttl_ms': int, 'max_size': int}
        """
        with self._lock:
            return {
                'size': len(self._cache),
                'ttl_ms': self.ttl_ms,
                'max_size': self.max_size
            }


# 全局单例
_cache = StatusCache(ttl_ms=1000)


def get_cache() -> StatusCache:
    """获取全局缓存实例"""
    return _cache
