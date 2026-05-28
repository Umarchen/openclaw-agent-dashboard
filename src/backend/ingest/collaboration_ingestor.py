"""
CollaborationIngestor — C2: monitors agent session file changes and produces
CollaborationChangedEvent when collaboration data differs from the last snapshot.

Subscribes to EventBus TOPIC_FILE_CHANGES, filters for agent session files,
calls get_collaboration() to get latest data, diffs against previous snapshot,
and publishes CollaborationChangedEvent when diffs exist.

REQ_ECS_010 AC-010-2: payload size < 20% of full collaboration data.
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
from core.event_bus import EventBus, get_event_bus, TOPIC_FILE_CHANGES, TOPIC_COLLABORATION_CHANGED
from core.event_types import BaseEvent, FileChangeEvent, CollaborationChangedEvent

_LOG = logging.getLogger(__name__)


class CollaborationIngestor:
    """C2: Produces CollaborationChangedEvent on agent session file changes."""

    def __init__(self) -> None:
        self._snapshot: Optional[Dict[str, Any]] = None
        self._last_collab_ts: float = 0.0
        self._initialized = False

    def initialize(self, bus: Optional[EventBus] = None) -> None:
        """Register as EventBus subscriber for file change events."""
        if bus is None:
            bus = get_event_bus()
        bus.subscribe(TOPIC_FILE_CHANGES, self._on_file_change)
        _LOG.info("CollaborationIngestor initialized, subscribed to %s", TOPIC_FILE_CHANGES)

    def _on_file_change(self, event: BaseEvent) -> None:
        """EventBus callback: handle FileChangeEvent."""
        if not isinstance(event, FileChangeEvent):
            return

        # Only react to agent session changes (agent_session_changed)
        if event.type != "file_change":
            return

        # Filter: only care about session file changes that could affect collaboration
        # The event_type field on FileChangeEvent is "file_change" (from BaseEvent.type)
        # but the original classification was agent_session_changed.
        # Since we subscribe to TOPIC_FILE_CHANGES (all file events), we need to
        # check the filepath pattern.
        filepath = event.filepath
        if not filepath:
            return

        # Only react to agent session jsonl files
        if "/sessions/" not in filepath or not filepath.endswith(".jsonl"):
            return

        # Schedule async processing on the event loop
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(asyncio.ensure_future, self._process_change())
        except RuntimeError:
            # No running loop — skip
            pass

    async def _process_change(self) -> None:
        """Fetch latest collaboration data, diff against snapshot, publish events."""
        try:
            from api.collaboration import get_collaboration

            collab = await get_collaboration()
            # Convert Pydantic model to dict if needed
            if hasattr(collab, "model_dump"):
                current = collab.model_dump()
            elif hasattr(collab, "dict"):
                current = collab.dict()
            elif isinstance(collab, dict):
                current = collab
            else:
                return

            # First call: just store snapshot, no diff
            if not self._initialized or self._snapshot is None:
                self._snapshot = current
                self._initialized = True
                return

            # Compute field-level diff
            diffs = _compute_field_diffs(self._snapshot, current)

            if diffs:
                # Publish CollaborationChangedEvent
                change_event = CollaborationChangedEvent(diffs=diffs)
                bus = get_event_bus()
                bus.publish(TOPIC_COLLABORATION_CHANGED, change_event)
                _LOG.debug("CollaborationChangedEvent published with %d diffs", len(diffs))

            # Update snapshot
            self._snapshot = current
            self._last_collab_ts = time.time()

        except Exception as e:
            _LOG.error("CollaborationIngestor error: %s", e, exc_info=True)
            record_error("unknown", str(e), "collaboration_ingestor:process", exc=e)


def _compute_field_diffs(
    old: Dict[str, Any], new: Dict[str, Any], parent_key: str = ""
) -> List[Dict[str, Any]]:
    """Recursively compute field-level diffs between two dicts.

    Returns a list of diffs: [{"field": "nodes[0].status", "old_value": ..., "new_value": ...}]
    Stops recursion at non-dict, non-list leaf values.
    """
    diffs: List[Dict[str, Any]] = []
    all_keys = set(list(old.keys()) + list(new.keys()))

    for key in all_keys:
        full_key = f"{parent_key}.{key}" if parent_key else key

        old_val = old.get(key)
        new_val = new.get(key)

        # Both are dicts: recurse
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            diffs.extend(_compute_field_diffs(old_val, new_val, full_key))
            continue

        # Both are lists of dicts: compare as ordered list
        if isinstance(old_val, list) and isinstance(new_val, list):
            # For lists, do a shallow comparison first; if different, treat as a single field diff
            if old_val != new_val:
                diffs.append({
                    "field": full_key,
                    "old_value": _truncate(old_val),
                    "new_value": _truncate(new_val),
                })
            continue

        # Leaf comparison
        if old_val != new_val:
            diffs.append({
                "field": full_key,
                "old_value": _truncate(old_val),
                "new_value": _truncate(new_val),
            })

    return diffs


def _truncate(val: Any, max_len: int = 200) -> Any:
    """Truncate string values for payload size control (AC-010-2)."""
    if isinstance(val, str) and len(val) > max_len:
        return val[:max_len] + "...(truncated)"
    if isinstance(val, list) and len(val) > 10:
        return val[:10]
    return val


# Module-level singleton
_instance: Optional[CollaborationIngestor] = None


def get_collaboration_ingestor() -> CollaborationIngestor:
    global _instance
    if _instance is None:
        _instance = CollaborationIngestor()
    return _instance
