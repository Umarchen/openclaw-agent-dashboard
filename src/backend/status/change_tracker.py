"""
变化跟踪 - 跟踪 Agent 状态变化
用于增量推送，只推送状态发生变化的 Agent
"""
import threading
import time
from typing import Dict, Any, List, Set, Optional


class ChangeTracker:
    """状态变化跟踪器（线程安全）
    
    功能：
    - 跟踪上次状态
    - 比较新旧状态，判断是否变化
    - 记录变化的 Agent ID
    - 支持批量获取变化列表
    - 清理旧状态快照，防止内存泄漏
    """
    
    # 保留的最大状态快照数
    MAX_SNAPSHOTS = 10
    
    def __init__(self):
        """初始化跟踪器"""
        self._last_states: Dict[str, Dict[str, Any]] = {}
        self._changed_agents: Set[str] = set()
        self._lock = threading.Lock()
    
    def update(self, agent_id: str, new_state: Dict[str, Any]) -> bool:
        """
        更新状态并返回是否变化
        
        Args:
            agent_id: Agent ID
            new_state: 新状态（必须包含 'status' 字段）
            
        Returns:
            状态是否发生变化
        """
        with self._lock:
            old_state = self._last_states.get(agent_id, {})
            
            # 比较关键字段
            is_changed = (
                old_state.get('status') != new_state.get('status') or
                old_state.get('currentTask') != new_state.get('currentTask') or
                old_state.get('lastActiveAt') != new_state.get('lastActiveAt') or
                bool(old_state.get('error')) != bool(new_state.get('error'))
            )
            
            # 更新状态（带时间戳用于清理）
            self._last_states[agent_id] = {
                **new_state.copy(),
                '_updated_at': time.time()
            }
            
            # 清理旧状态快照（保留最近 MAX_SNAPSHOTS 个）
            if len(self._last_states) > self.MAX_SNAPSHOTS:
                # 按更新时间排序，保留最近的
                sorted_keys = sorted(
                    self._last_states.keys(),
                    key=lambda k: self._last_states[k].get('_updated_at', 0),
                    reverse=True
                )[:self.MAX_SNAPSHOTS]
                self._last_states = {k: self._last_states[k] for k in sorted_keys}
            
            # 标记变化
            if is_changed:
                self._changed_agents.add(agent_id)
            
            return is_changed
    
    def get_changed_agents(self) -> List[str]:
        """
        获取所有状态变化的 Agent ID
        
        Returns:
            变化的 Agent ID 列表
        """
        with self._lock:
            return list(self._changed_agents)
    
    def clear_changes(self) -> None:
        """清除变化标记"""
        with self._lock:
            self._changed_agents.clear()
    
    def get_last_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        获取上次状态
        
        Args:
            agent_id: Agent ID
            
        Returns:
            上次状态，不存在返回 None
        """
        with self._lock:
            if agent_id not in self._last_states:
                return None
            # 返回状态副本，排除内部字段
            state = self._last_states[agent_id].copy()
            return {k: v for k, v in state.items() if not k.startswith('_')}


# 全局单例
_tracker = ChangeTracker()


def get_tracker() -> ChangeTracker:
    """获取全局跟踪器实例"""
    return _tracker
