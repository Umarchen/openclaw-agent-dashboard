"""
FileChangeClassifier — determines what a file change means for agent state.

Extracts agent_id from file paths and classifies change types.
Used by file_watcher.py to create FileChangeEvent objects for EventBus.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.event_types import FileChangeEvent

_LOG = logging.getLogger(__name__)


def extract_agent_id_from_path(filepath: str) -> Optional[str]:
    """Extract agent_id from a file path.

    Handles paths like:
    - agents/<agent_id>/sessions/<file>.jsonl
    - subagents/runs.json (returns None — not agent-specific)
    """
    try:
        # Normalize backslashes for Windows-style paths
        normalized = filepath.replace("\\", "/")
        path = Path(normalized)
        parts = path.parts
        try:
            agents_idx = parts.index("agents")
        except ValueError:
            return None
        if agents_idx + 2 < len(parts) and parts[agents_idx + 2] == "sessions":
            return parts[agents_idx + 1]
        return None
    except Exception:
        return None


def classify(filepath: str, change_type: str = "modified") -> FileChangeEvent:
    """Classify a file path into a FileChangeEvent.

    Args:
        filepath: The absolute or relative file path that changed.
        change_type: One of 'created', 'modified', 'deleted'.

    Returns:
        FileChangeEvent with agent_id extracted (if determinable).
    """
    agent_id = extract_agent_id_from_path(filepath)
    return FileChangeEvent(
        filepath=filepath,
        agent_id=agent_id,
        change_type=change_type,
    )


def classify_session_change(filepath: str) -> Optional[str]:
    """Return agent_id if the path is under an agent's sessions directory."""
    return extract_agent_id_from_path(filepath)


def classify_memory_change(filepath: str) -> Optional[str]:
    """Classify a memory file change.

    Memory files under workspace/memory don't directly map to a single agent.
    For C0, we don't extract agent_id from memory changes.
    Returns None.
    """
    return None


def classify_subagent_change(filepath: str) -> Optional[str]:
    """Classify a subagent file change (e.g., runs.json).

    For C0, subagent changes are tracked globally, not per-agent.
    Returns None.
    """
    return None
