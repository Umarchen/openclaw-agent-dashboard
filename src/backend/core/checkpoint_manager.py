"""
CheckpointManager — C1: JSONL offset tracking + checkpoint persistence.

Tracks per-file byte offsets for incremental jsonl reads. Persists
checkpoints to disk periodically (JSON format). Detects file
truncate/rotate via inode + mtime validation.

Spec: REQ_ECS_008
"""
from __future__ import annotations

import json
import logging
import os
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


@dataclass
class FileCheckpoint:
    """Per-file checkpoint entry."""
    filepath: str                          # canonical absolute path
    offset: int = 0                         # byte offset for next read
    inode: int = 0                          # file inode number (for rotation detection)
    mtime: float = 0.0                     # file modification time
    last_read_ts: float = 0.0              # monotonic timestamp of last successful read
    # Total bytes read since last checkpoint flush (for metric reporting)
    bytes_read_since_flush: int = 0


class CheckpointManager:
    """JSONL offset checkpoint manager (REQ_ECS_008).

    Responsibilities:
    1. Track per-file byte offsets for incremental reads
    2. Persist checkpoints to JSON file periodically
    3. Detect file truncate/rotate via inode + mtime validation
    4. Startup recovery: load checkpoints from disk
    """

    def __init__(
        self,
        checkpoint_dir: Optional[str] = None,
        flush_interval_sec: float = 10.0,
    ) -> None:
        self._checkpoint_dir = Path(checkpoint_dir or "~/.openclaw-agent-dashboard/checkpoints").expanduser()
        self._flush_interval_sec = flush_interval_sec

        # In-memory offset store: canonical_path -> FileCheckpoint
        self._offsets: Dict[str, FileCheckpoint] = {}
        self._lock = threading.Lock()

        # Flush state
        self._last_flush_ts: float = 0.0
        self._flush_count: int = 0
        self._reset_count: int = 0

        # Metrics: total bytes read
        self._total_bytes_read: int = 0

    # ── public API ──────────────────────────────────────────────

    def get_offset(self, filepath: str) -> int:
        """Return the current byte offset for *filepath*.

        Returns 0 if no checkpoint exists (first read = tail-read).
        """
        canonical = os.path.realpath(filepath)
        with self._lock:
            entry = self._offsets.get(canonical)
            if entry is None:
                return 0
            # Validate checkpoint against current file state
            if self._is_checkpoint_valid(canonical, entry):
                return entry.offset
            else:
                # Checkpoint invalid — reset
                _LOG.warning(
                    "Checkpoint invalid for %s (inode=%s, offset=%s), resetting",
                    canonical, entry.inode, entry.offset,
                )
                self._do_reset(canonical, entry)
                return 0

    def update_offset(
        self,
        filepath: str,
        offset: int,
        bytes_read: int = 0,
    ) -> None:
        """Update the stored offset for *filepath* after a successful read.

        Args:
            filepath: Path to the file that was read.
            offset: New byte offset (position after the last byte read).
            bytes_read: Number of bytes consumed in this read (for metrics).
        """
        canonical = os.path.realpath(filepath)
        now = time.monotonic()
        try:
            st = os.stat(canonical)
            inode = st.st_ino
            mtime = st.st_mtime
        except OSError:
            inode = 0
            mtime = 0.0

        with self._lock:
            entry = self._offsets.get(canonical)
            if entry is None:
                entry = FileCheckpoint(filepath=canonical)
                self._offsets[canonical] = entry

            entry.offset = offset
            entry.inode = inode
            entry.mtime = mtime
            entry.last_read_ts = now
            entry.bytes_read_since_flush += bytes_read
            self._total_bytes_read += bytes_read

        # Check if periodic flush is needed
        self._maybe_flush(now)

    def remove_checkpoint(self, filepath: str) -> None:
        """Remove checkpoint for a file (e.g., file deleted)."""
        canonical = os.path.realpath(filepath)
        with self._lock:
            self._offsets.pop(canonical, None)

    def reset_all(self) -> int:
        """Reset all checkpoints (return to tail-read behavior).

        Returns the number of checkpoints reset.
        """
        with self._lock:
            count = len(self._offsets)
            self._offsets.clear()
            self._reset_count += count
            _LOG.info("All checkpoints reset (%d entries)", count)
            return count

    def load_checkpoints(self) -> int:
        """Load checkpoints from disk on startup.

        Returns the number of checkpoints loaded.
        Discards corrupted entries (fallback to C0 tail-read).
        """
        self._ensure_dir()
        cp_file = self._checkpoint_path()

        if not cp_file.exists():
            _LOG.info("No checkpoint file found at %s — starting fresh", cp_file)
            return 0

        loaded = 0
        discarded = 0
        try:
            with open(cp_file, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry_data = json.loads(line)
                    except json.JSONDecodeError:
                        _LOG.warning(
                            "Corrupt checkpoint line %d: %s", line_no, line[:80]
                        )
                        discarded += 1
                        continue

                    fp = entry_data.get("filepath", "")
                    if not fp:
                        discarded += 1
                        continue

                    canonical = os.path.realpath(fp)
                    cp = FileCheckpoint(
                        filepath=canonical,
                        offset=entry_data.get("offset", 0),
                        inode=entry_data.get("inode", 0),
                        mtime=entry_data.get("mtime", 0.0),
                        last_read_ts=entry_data.get("last_read_ts", 0.0),
                    )

                    # Validate on load
                    if self._is_checkpoint_valid(canonical, cp):
                        self._offsets[canonical] = cp
                        loaded += 1
                    else:
                        _LOG.info(
                            "Checkpoint for %s invalid on load (inode changed or file truncated), discarding",
                            canonical,
                        )
                        discarded += 1
                        self._reset_count += 1

            _LOG.info(
                "Loaded %d checkpoints, discarded %d from %s",
                loaded, discarded, cp_file,
            )
        except OSError as e:
            _LOG.error("Failed to load checkpoints from %s: %s", cp_file, e)

        return loaded

    def flush(self) -> bool:
        """Force-persist all checkpoints to disk.

        Returns True if flush succeeded.
        """
        self._ensure_dir()
        cp_file = self._checkpoint_path()
        now = time.monotonic()

        with self._lock:
            entries = list(self._offsets.values())

        try:
            # Write atomically via temp file
            tmp_file = cp_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                for entry in entries:
                    line = json.dumps({
                        "filepath": entry.filepath,
                        "offset": entry.offset,
                        "inode": entry.inode,
                        "mtime": entry.mtime,
                        "last_read_ts": entry.last_read_ts,
                    })
                    f.write(line + "\n")

            # Atomic rename
            tmp_file.replace(cp_file)

            # Restrict permissions: 0600 (owner read/write only)
            try:
                os.chmod(cp_file, stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                pass

            with self._lock:
                self._last_flush_ts = now
                self._flush_count += 1
                # Reset per-entry bytes_read_since_flush counters
                for entry in self._offsets.values():
                    entry.bytes_read_since_flush = 0

            _LOG.debug("Flushed %d checkpoints to %s", len(entries), cp_file)
            return True

        except OSError as e:
            _LOG.error("Failed to flush checkpoints to %s: %s", cp_file, e)
            return False

    def get_status(self) -> Dict[str, Any]:
        """Return checkpoint manager status (for diagnostics/metrics)."""
        with self._lock:
            return {
                "implemented": True,
                "version": "c1",
                "checkpoint_dir": str(self._checkpoint_dir),
                "num_checkpoints": len(self._offsets),
                "flush_count": self._flush_count,
                "reset_count": self._reset_count,
                "total_bytes_read": self._total_bytes_read,
                "last_flush_ts": self._last_flush_ts,
                "flush_interval_sec": self._flush_interval_sec,
            }

    @property
    def total_bytes_read(self) -> int:
        """Total bytes read across all tracked files (for metrics)."""
        with self._lock:
            return self._total_bytes_read

    @property
    def reset_count(self) -> int:
        """Number of checkpoint resets due to invalidation."""
        with self._lock:
            return self._reset_count

    # ── internal methods ─────────────────────────────────────────

    def _checkpoint_path(self) -> Path:
        return self._checkpoint_dir / "offsets.jsonl"

    def _ensure_dir(self) -> None:
        try:
            self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
            # Restrict directory permissions: 0700
            try:
                os.chmod(self._checkpoint_dir, stat.S_IRWXU)
            except OSError:
                pass
        except OSError as e:
            _LOG.error("Cannot create checkpoint dir %s: %s", self._checkpoint_dir, e)

    def _is_checkpoint_valid(self, canonical: str, entry: FileCheckpoint) -> bool:
        """Check if checkpoint is still valid (inode + mtime + offset vs size).

        Invalid conditions:
        - File doesn't exist
        - inode changed (file replaced/rotated)
        - File size < offset (file truncated)
        """
        try:
            st = os.stat(canonical)
        except OSError:
            return False  # File doesn't exist

        # Check inode (rotation/replacement detection)
        if entry.inode > 0 and st.st_ino != entry.inode:
            _LOG.info(
                "Inode mismatch for %s: checkpoint=%s, current=%s",
                canonical, entry.inode, st.st_ino,
            )
            return False

        # Check truncation
        file_size = st.st_size
        if entry.offset > file_size:
            _LOG.info(
                "File truncated: %s (checkpoint offset=%s > file size=%s)",
                canonical, entry.offset, file_size,
            )
            return False

        return True

    def _do_reset(self, canonical: str, entry: FileCheckpoint) -> None:
        """Reset a single checkpoint entry."""
        entry.offset = 0
        entry.inode = 0
        entry.mtime = 0.0
        entry.bytes_read_since_flush = 0
        self._reset_count += 1

    def _maybe_flush(self, now: float) -> None:
        """Flush if flush interval has elapsed since last flush."""
        if self._flush_interval_sec <= 0:
            return  # Periodic flush disabled
        if now - self._last_flush_ts >= self._flush_interval_sec:
            if not self._offsets:
                return
            try:
                self.flush()
            except Exception:
                pass  # Don't let flush failures interrupt the calling code


# ── module-level singleton ─────────────────────────────────────

_manager: Optional[CheckpointManager] = None


def get_checkpoint_manager() -> CheckpointManager:
    global _manager
    if _manager is None:
        try:
            from core.config_fortify import get_fortify_config
            cfg = get_fortify_config()
            _manager = CheckpointManager(
                checkpoint_dir=getattr(cfg, "ecs_checkpoint_dir", None),
                flush_interval_sec=getattr(cfg, "ecs_checkpoint_flush_interval_sec", 10.0),
            )
        except Exception:
            # Config not ready yet — use defaults
            _manager = CheckpointManager()
    return _manager


def reset_checkpoint_manager_for_tests() -> None:
    global _manager
    if _manager is not None:
        _manager.reset_all()
    _manager = None
