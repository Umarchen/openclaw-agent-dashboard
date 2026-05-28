"""
TaskIngestor — C2: monitors runs.json file changes and produces
TaskChangedEvent (added/updated/removed) for each changed task.

Subscribes to EventBus TOPIC_FILE_CHANGES, filters for runs.json files,
calls get_tasks() to get latest task list, diffs against previous snapshot,
and publishes individual TaskChangedEvent for each changed task.

REQ_ECS_010 AC-010-3: only changed tasks included, not unchanged ones.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from core.error_handler import record_error
from core.event_bus import EventBus, get_event_bus, TOPIC_FILE_CHANGES, TOPIC_TASK_CHANGED
from core.event_types import BaseEvent, FileChangeEvent, TaskChangedEvent

_LOG = logging.getLogger(__name__)


class TaskIngestor:
    """C2: Produces TaskChangedEvent on runs.json file changes."""

    def __init__(self) -> None:
        self._snapshot: Dict[str, Dict[str, Any]] = {}  # task_id → task_data
        self._initialized = False

    def initialize(self, bus: Optional[EventBus] = None) -> None:
        """Register as EventBus subscriber for file change events."""
        if bus is None:
            bus = get_event_bus()
        bus.subscribe(TOPIC_FILE_CHANGES, self._on_file_change)
        _LOG.info("TaskIngestor initialized, subscribed to %s", TOPIC_FILE_CHANGES)

    def _on_file_change(self, event: BaseEvent) -> None:
        """EventBus callback: handle FileChangeEvent."""
        if not isinstance(event, FileChangeEvent):
            return

        filepath = event.filepath
        if not filepath:
            return

        # Only react to runs.json changes
        filename = Path(filepath).name
        if filename != "runs.json":
            return

        # Schedule async processing on the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(asyncio.ensure_future, self._process_change())
        except RuntimeError:
            pass

    async def _process_change(self) -> None:
        """Fetch latest tasks, diff against snapshot, publish events."""
        try:
            from api.subagents import get_tasks

            result = await get_tasks()
            current_tasks: List[Dict[str, Any]] = result.get("tasks", []) if isinstance(result, dict) else []

            # Build task_id → task_data map
            current_map: Dict[str, Dict[str, Any]] = {}
            for task in current_tasks:
                task_id = task.get("id") or task.get("runId", "")
                if task_id:
                    current_map[task_id] = task

            # First call: just store snapshot, no diff
            if not self._initialized or not self._snapshot:
                self._snapshot = current_map
                self._initialized = True
                return

            # Compute diff: added, updated, removed
            old_ids = set(self._snapshot.keys())
            new_ids = set(current_map.keys())

            bus = get_event_bus()

            # Added tasks
            for task_id in new_ids - old_ids:
                task_data = current_map[task_id]
                change_event = TaskChangedEvent(
                    change="added",
                    task_id=task_id,
                    task_data=_truncate_task_data(task_data),
                )
                bus.publish(TOPIC_TASK_CHANGED, change_event)

            # Updated tasks (data changed for same task_id)
            for task_id in new_ids & old_ids:
                old_data = self._snapshot[task_id]
                new_data = current_map[task_id]
                if _task_data_changed(old_data, new_data):
                    change_event = TaskChangedEvent(
                        change="updated",
                        task_id=task_id,
                        task_data=_truncate_task_data(new_data),
                    )
                    bus.publish(TOPIC_TASK_CHANGED, change_event)

            # Removed tasks
            for task_id in old_ids - new_ids:
                change_event = TaskChangedEvent(
                    change="removed",
                    task_id=task_id,
                    task_data=None,
                )
                bus.publish(TOPIC_TASK_CHANGED, change_event)

            # Update snapshot
            self._snapshot = current_map

        except Exception as e:
            _LOG.error("TaskIngestor error: %s", e, exc_info=True)
            record_error("unknown", str(e), "task_ingestor:process", exc=e)


def _task_data_changed(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
    """Check if task data has meaningfully changed.

    Compares key mutable fields that reflect actual task state.
    Ignores volatile fields like runtime that change every second.
    """
    # Fields that indicate real state change
    state_fields = ("status", "outcome", "error", "endedAt", "progress",
                     "output", "generatedFiles", "agentName")

    for field in state_fields:
        if old.get(field) != new.get(field):
            return True

    return False


def _truncate_task_data(task: Dict[str, Any], max_task_len: int = 500) -> Dict[str, Any]:
    """Truncate task data for payload size control."""
    truncated = dict(task)
    task_text = truncated.get("task")
    if isinstance(task_text, str) and len(task_text) > max_task_len:
        truncated["task"] = task_text[:max_task_len] + "...(truncated)"
    return truncated


# Module-level singleton
_instance: Optional[TaskIngestor] = None


def get_task_ingestor() -> TaskIngestor:
    global _instance
    if _instance is None:
        _instance = TaskIngestor()
    return _instance
