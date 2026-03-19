"""
版本信息读取器

负责从 package.json 读取版本信息，支持缓存机制。
在应用启动时读取并缓存，后续请求直接返回缓存数据。
"""
from pathlib import Path
from typing import Optional
import json
import logging
import os

logger = logging.getLogger(__name__)


class VersionInfoReader:
    """版本信息读取器，支持缓存"""
    
    def __init__(self, package_json_path: Optional[Path] = None):
        """
        初始化版本信息读取器
        
        Args:
            package_json_path: package.json 文件路径，默认为项目根目录下的 package.json
        """
        # 默认路径：src/backend/data -> src/backend -> src -> package.json
        self.package_json_path = package_json_path or Path(__file__).parent.parent.parent / "package.json"
        self._cached_info: Optional[dict] = None
    
    def read_version_info(self) -> dict:
        """
        读取版本信息（带缓存）
        
        Returns:
            dict: 包含 version, name, description 等字段的字典
        """
        if self._cached_info is not None:
            return self._cached_info
        
        try:
            with open(self.package_json_path, 'r', encoding='utf-8') as f:
                package_data = json.load(f)
            
            self._cached_info = {
                "version": package_data.get("version", "unknown"),
                "name": package_data.get("name", "openclaw-agent-dashboard"),
                "description": package_data.get("description", ""),
            }
            
            # 可选：读取构建时间（从环境变量）
            build_date = self._read_build_date()
            if build_date:
                self._cached_info["build_date"] = build_date
            
            # 可选：读取 Git 提交哈希
            git_commit = self._read_git_commit()
            if git_commit:
                self._cached_info["git_commit"] = git_commit
            
            logger.info(f"成功读取版本信息: {self._cached_info['version']}")
            return self._cached_info
            
        except Exception as e:
            # 降级：返回默认值
            logger.error(f"读取版本信息失败: {e}", exc_info=True)
            self._cached_info = {
                "version": "unknown",
                "name": "openclaw-agent-dashboard",
                "description": "",
            }
            return self._cached_info
    
    def _read_build_date(self) -> Optional[str]:
        """
        读取构建时间（从环境变量）
        
        Returns:
            Optional[str]: 构建时间字符串，如果未设置则返回 None
        """
        return os.getenv("DASHBOARD_BUILD_DATE")
    
    def _read_git_commit(self) -> Optional[str]:
        """
        读取 Git 提交哈希（从环境变量）
        
        Returns:
            Optional[str]: Git 提交哈希（短格式），如果未设置则返回 None
        """
        return os.getenv("DASHBOARD_GIT_COMMIT")
    
    def clear_cache(self):
        """清除缓存（用于测试或强制刷新）"""
        self._cached_info = None


# 全局单例实例
_version_reader: Optional[VersionInfoReader] = None


def get_version_reader() -> VersionInfoReader:
    """
    获取全局版本信息读取器实例
    
    Returns:
        VersionInfoReader: 版本信息读取器实例
    """
    global _version_reader
    if _version_reader is None:
        _version_reader = VersionInfoReader()
    return _version_reader
