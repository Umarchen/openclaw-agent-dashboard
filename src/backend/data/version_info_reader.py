"""
版本信息读取器

负责从 package.json / openclaw.plugin.json 读取版本信息，支持缓存机制。
在应用启动时读取并缓存，后续请求直接返回缓存数据。

插件安装目录与开发仓库目录结构不同：通过向上枚举父目录并尝试多个文件名，避免 vunknown。
"""
from pathlib import Path
from typing import Optional, Any, Dict, List
import json
import logging
import os

logger = logging.getLogger(__name__)


def _candidate_roots() -> List[Path]:
    """从本文件位置向上取若干级目录，覆盖插件 dashboard/data 与开发 src/backend/data。"""
    here = Path(__file__).resolve()
    roots: List[Path] = []
    # parents[0]=data, [1]=dashboard|backend, [2]=插件根或 src, [3]=仓库根或 extensions 等
    for i in (2, 3, 4):
        if i < len(here.parents):
            roots.append(here.parents[i])
    seen = set()
    out: List[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _merge_manifest(into: Dict[str, str], data: Dict[str, Any], filename: str) -> None:
    """将单个 JSON 文件中的字段合并进 meta（后者不覆盖已有非空 version/name）。"""
    v = data.get("version")
    if v is not None and str(v).strip():
        into["version"] = str(v).strip()
    if filename == "openclaw.plugin.json":
        name = data.get("name") or data.get("id")
    else:
        name = data.get("name")
    if name is not None and str(name).strip():
        into["name"] = str(name).strip()
    desc = data.get("description")
    if desc is not None:
        into["description"] = str(desc)


def _load_metadata_from_files() -> Dict[str, str]:
    """
    在候选目录中依次尝试 package.json、openclaw.plugin.json，合并得到版本信息。
    """
    meta = {"version": "", "name": "", "description": ""}
    for root in _candidate_roots():
        for fname in ("package.json", "openclaw.plugin.json"):
            path = root / fname
            if not path.is_file():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    continue
                _merge_manifest(meta, data, fname)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("读取 %s 失败: %s", path, e)
                continue
    if not meta["version"]:
        meta["version"] = "unknown"
    if not meta["name"]:
        meta["name"] = "openclaw-agent-dashboard"
    return meta


class VersionInfoReader:
    """版本信息读取器，支持缓存"""

    def __init__(self, package_json_path: Optional[Path] = None):
        """
        Args:
            package_json_path: 已废弃保留参数；实际从多路径探测元数据。
        """
        self._legacy_path = package_json_path
        self._cached_info: Optional[dict] = None

    def read_version_info(self) -> dict:
        if self._cached_info is not None:
            return self._cached_info

        try:
            if self._legacy_path is not None:
                with open(self._legacy_path, "r", encoding="utf-8") as f:
                    package_data = json.load(f)
                self._cached_info = {
                    "version": str(package_data.get("version", "unknown") or "unknown"),
                    "name": str(package_data.get("name", "openclaw-agent-dashboard") or "openclaw-agent-dashboard"),
                    "description": str(package_data.get("description", "") or ""),
                }
            else:
                m = _load_metadata_from_files()
                self._cached_info = {
                    "version": m["version"],
                    "name": m["name"],
                    "description": m["description"],
                }

            build_date = self._read_build_date()
            if build_date:
                self._cached_info["build_date"] = build_date

            git_commit = self._read_git_commit()
            if git_commit:
                self._cached_info["git_commit"] = git_commit

            logger.info("成功读取版本信息: %s %s", self._cached_info.get("name"), self._cached_info.get("version"))
            return self._cached_info

        except Exception as e:
            logger.error("读取版本信息失败: %s", e, exc_info=True)
            self._cached_info = {
                "version": "unknown",
                "name": "openclaw-agent-dashboard",
                "description": "",
            }
            return self._cached_info

    def _read_build_date(self) -> Optional[str]:
        return os.getenv("DASHBOARD_BUILD_DATE")

    def _read_git_commit(self) -> Optional[str]:
        return os.getenv("DASHBOARD_GIT_COMMIT")

    def clear_cache(self):
        self._cached_info = None


_version_reader: Optional[VersionInfoReader] = None


def get_version_reader() -> VersionInfoReader:
    global _version_reader
    if _version_reader is None:
        _version_reader = VersionInfoReader()
    return _version_reader
