"""
CheckpointManager — C1 placeholder.

C1 scope: state persistence, crash recovery, snapshot save/load.
C0: no-op skeleton with logging warnings.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_LOG = logging.getLogger(__name__)


class CheckpointManager:
    """Checkpoint manager placeholder for C0.

    In C1, this will handle:
    - Periodic state snapshots to disk
    - Crash recovery from last checkpoint
    - State migration between versions

    In C0: all operations are no-ops with warning logs.
    """

    def save_checkpoint(self, state: Dict[str, Any]) -> None:
        """Save a state checkpoint (C0: no-op)."""
        _LOG.warning("CheckpointManager.save_checkpoint not implemented in C0 (no-op)")

    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Load the last checkpoint (C0: no-op, returns None)."""
        _LOG.warning("CheckpointManager.load_checkpoint not implemented in C0 (no-op)")
        return None

    def get_status(self) -> Dict[str, Any]:
        """Return checkpoint manager status."""
        return {
            "implemented": False,
            "version": "c0-placeholder",
            "last_checkpoint": None,
        }


# ── module-level singleton ─────────────────────────────────────

_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> CheckpointManager:
    global _manager
    if _manager is None:
        _manager = CheckpointManager()
    return _manager
