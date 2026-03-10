"""
任务历史持久化 - 保存已完成任务，避免 runs.json 清空后数据丢失
数据存放在 Dashboard 自有目录，不修改 OpenClaw 的 ~/.openclaw 目录结构。
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Any

# 旧路径（兼容迁移）：~/.openclaw/dashboard/ → ~/.openclaw-dashboard/ → ~/.openclaw-agent-dashboard/
_LEGACY_DASHBOARD_DIR = Path.home() / ".openclaw" / "dashboard"
_LEGACY_TASK_HISTORY_PATH = _LEGACY_DASHBOARD_DIR / "task_history.json"
_PREV_DASHBOARD_DIR = Path.home() / ".openclaw-dashboard"
_PREV_TASK_HISTORY_PATH = _PREV_DASHBOARD_DIR / "task_history.json"


def get_dashboard_data_dir() -> Path:
    """Dashboard 数据目录：优先 OPENCLAW_AGENT_DASHBOARD_DATA，否则 ~/.openclaw-agent-dashboard"""
    env = os.environ.get("OPENCLAW_AGENT_DASHBOARD_DATA")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".openclaw-agent-dashboard"


DASHBOARD_DATA_DIR = get_dashboard_data_dir()
TASK_HISTORY_PATH = DASHBOARD_DATA_DIR / "task_history.json"
MAX_HISTORY_ITEMS = 200


def _ensure_dir():
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _migrate_from_legacy_if_needed() -> None:
    """若新路径下无文件，则从旧路径迁移一次（顺序：~/.openclaw/dashboard → ~/.openclaw-dashboard）"""
    if TASK_HISTORY_PATH.exists():
        return
    for src in (_LEGACY_TASK_HISTORY_PATH, _PREV_TASK_HISTORY_PATH):
        if not src.exists():
            continue
        try:
            _ensure_dir()
            with open(src, 'r', encoding='utf-8') as f:
                data = json.load(f)
            with open(TASK_HISTORY_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[TaskHistory] 已从 {src} 迁移到 {TASK_HISTORY_PATH}")
        except Exception as e:
            print(f"[TaskHistory] 迁移旧数据失败: {e}")
        return


def load_task_history() -> List[Dict[str, Any]]:
    """加载任务历史"""
    _migrate_from_legacy_if_needed()
    if not TASK_HISTORY_PATH.exists():
        return []
    try:
        with open(TASK_HISTORY_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        tasks = data.get('tasks', [])
        return tasks if isinstance(tasks, list) else []
    except Exception as e:
        print(f"加载任务历史失败: {e}")
        return []


def save_task_history(tasks: List[Dict[str, Any]]) -> None:
    """保存任务历史，保留最近 N 条"""
    _ensure_dir()
    trimmed = tasks[:MAX_HISTORY_ITEMS]
    try:
        with open(TASK_HISTORY_PATH, 'w', encoding='utf-8') as f:
            json.dump({'tasks': trimmed, 'version': 1}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存任务历史失败: {e}")


def merge_with_history(
    current_runs: List[Dict[str, Any]],
    run_to_task_fn,
) -> List[Dict[str, Any]]:
    """
    合并当前 runs 与历史，并持久化新完成的任务
    
    Args:
        current_runs: 从 runs.json 读取的当前运行记录
        run_to_task_fn: 将 run 转为 task 格式的函数 (run) -> dict
    """
    history = load_task_history()
    history_ids = {t.get('id') for t in history if t.get('id')}
    
    # 当前 runs 转为 tasks
    current_tasks = []
    new_completed = []
    for run in current_runs:
        task = run_to_task_fn(run)
        current_tasks.append(task)
        run_id = run.get('runId', '')
        if run.get('endedAt') and run_id and run_id not in history_ids:
            new_completed.append(task)
            history_ids.add(run_id)
    
    # 新完成的任务加入历史
    if new_completed:
        for t in reversed(new_completed):
            history.insert(0, t)
        save_task_history(history)
    
    # 合并：当前 runs 中的任务 + 历史中已不在 runs 里的
    current_ids = {r.get('runId') for r in current_runs}
    for h in history:
        if h.get('id') not in current_ids:
            current_tasks.append(h)
    
    # 按开始时间倒序
    current_tasks.sort(key=lambda x: x.get('startTime') or 0, reverse=True)
    return current_tasks[:100]  # 最多返回 100 条
