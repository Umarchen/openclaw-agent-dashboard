"""
AgentStateIngestor — C1: offset-read upgrade from C0 tail-read.

Listens for FileChangeEvent via EventBus, extracts agent state via offset-read
(C1) or tail-read (fallback), and writes to StateStore.

C1 changes:
- Uses CheckpointManager to track per-file byte offsets
- First read: tail-read (equivalent to C0 behavior)
- Subsequent reads: seek from last offset to EOF
- Records bytes read for metrics
- On checkpoint invalidation (truncate/rotate), falls back to tail-read
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.event_bus import EventBus, get_event_bus, TOPIC_FILE_CHANGES, TOPIC_HEARTBEAT
from core.event_types import BaseEvent, FileChangeEvent, HeartbeatTickEvent
from core.file_change_classifier import extract_agent_id_from_path
from core.metrics_collector import MetricsCollector, get_metrics
from core.state_store import StateStore, get_state_store

_LOG = logging.getLogger(__name__)


class AgentStateIngestor:
    """Converts FileChangeEvents into StateStore updates.

    Subscribes to TOPIC_FILE_CHANGES on the EventBus.
    For each event:
    1. Determine which agents are affected (from event.agent_id or all agents)
    2. For each affected agent, extract state via offset-read (C1) or tail-read (C0 fallback)
    3. On read failure, fallback to calculate_agent_status()
    4. Write state to StateStore

    C1 upgrade:
    - Uses CheckpointManager for per-file offset tracking
    - Incremental reads from last known offset
    - Falls back to tail-read on checkpoint invalidation
    """

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        state_store: Optional[StateStore] = None,
        metrics: Optional[MetricsCollector] = None,
    ) -> None:
        self._event_bus = event_bus or get_event_bus()
        self._state_store = state_store or get_state_store()
        self._metrics = metrics or get_metrics()
        self._initialized = False
        self._checkpoint_manager = None  # Lazy init in initialize()

    def initialize(self) -> None:
        """Subscribe to EventBus topics and load checkpoints. Call once during startup."""
        if self._initialized:
            return
        self._event_bus.subscribe(TOPIC_FILE_CHANGES, self._on_file_change)
        self._event_bus.subscribe(TOPIC_HEARTBEAT, self._on_heartbeat_tick)

        # C1: Load checkpoints from disk
        try:
            from core.checkpoint_manager import get_checkpoint_manager
            self._checkpoint_manager = get_checkpoint_manager()
            loaded = self._checkpoint_manager.load_checkpoints()
            if loaded > 0:
                _LOG.info("C1: Loaded %d file offset checkpoints", loaded)
        except Exception as e:
            _LOG.warning("C1: Failed to initialize CheckpointManager: %s", e)

        self._initialized = True
        _LOG.info("AgentStateIngestor initialized (C1: offset-read)")

    def shutdown(self) -> None:
        """Unsubscribe from EventBus and flush checkpoints."""
        self._initialized = False
        # C1: Flush pending checkpoints on shutdown
        if self._checkpoint_manager is not None:
            try:
                self._checkpoint_manager.flush()
            except Exception as e:
                _LOG.warning("C1: Failed to flush checkpoints on shutdown: %s", e)
        _LOG.info("AgentStateIngestor shutdown")

    def _on_file_change(self, event: BaseEvent) -> None:
        """Handle FileChangeEvent: extract affected agents and ingest."""
        if not isinstance(event, FileChangeEvent):
            return

        self._metrics.increment(MetricsCollector.EVT_PROCESSED)
        start = time.monotonic()

        try:
            if event.agent_id:
                self._ingest_agent(event.agent_id)
            else:
                self._ingest_all_agents()
        except Exception as e:
            _LOG.error("Ingestor error for %s: %s", event.filepath or "all", e)
        finally:
            lag_ms = (time.monotonic() - start) * 1000
            self._metrics.record_latency(MetricsCollector.INGEST_LATENCY, lag_ms)

    def _on_heartbeat_tick(self, event: BaseEvent) -> None:
        """Handle HeartbeatTickEvent.

        Per C0 constraints: NO cache invalidation, NO broadcast_full_state,
        NO full-agent recalculation. Just record the tick.
        """
        self._metrics.increment(MetricsCollector.EVT_PROCESSED)

    def _ingest_all_agents(self) -> None:
        """Ingest state for all known agents."""
        try:
            from data.config_reader import get_agents_list
            agents = get_agents_list()
        except Exception:
            return

        for agent in agents:
            aid = agent.get("id")
            if aid:
                try:
                    self._ingest_agent(aid)
                except Exception as e:
                    _LOG.warning("Ingestor error for agent %s: %s", aid, e)

    def _ingest_agent(self, agent_id: str) -> None:
        """Extract state for a single agent and write to StateStore.

        C1: Uses offset-read via CheckpointManager. Falls back to tail-read
        when no checkpoint exists or checkpoint is invalid.
        """
        state = self._extract_agent_state(agent_id)
        if state:
            self._state_store.update_agent(agent_id, state)
            self._metrics.increment(MetricsCollector.STATE_UPDATE)

    def _extract_agent_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Extract agent state. C1: offset-read first, fallback to calculator."""
        # C1: Try offset-read first
        session_file = self._get_session_file(agent_id)
        if session_file:
            try:
                result = self._offset_read_session(session_file, agent_id)
                if result:
                    return result
            except Exception as e:
                _LOG.debug("offset_read failed for %s: %s, falling back", agent_id, e)

        # Fallback: C0 tail-read
        try:
            from data.session_reader import tail_read_session

            tail = tail_read_session(agent_id)
            if tail:
                # Update checkpoint after successful tail-read
                if session_file and self._checkpoint_manager:
                    self._checkpoint_manager.update_offset(
                        str(session_file),
                        offset=session_file.stat().st_size,
                        bytes_read=session_file.stat().st_size,
                    )
                return self._tail_to_state(agent_id, tail)
        except Exception as e:
            _LOG.debug("tail_read failed for %s: %s, falling back", agent_id, e)

        # Final fallback: calculate_agent_status for this agent only
        try:
            return self._calculator_fallback(agent_id)
        except Exception as e:
            _LOG.error("calculator fallback failed for %s: %s", agent_id, e)
            return None

    def _get_session_file(self, agent_id: str) -> Optional[Any]:
        """Get the latest session file path for an agent."""
        try:
            from data.session_reader import get_latest_session_file
            return get_latest_session_file(agent_id)
        except Exception:
            return None

    def _offset_read_session(
        self, session_file: Any, agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """C1: Read session file incrementally from last checkpoint offset.

        Returns None if no new data to read (offset == file size).
        """
        from pathlib import Path

        fp = Path(session_file)
        if not fp.exists():
            return None

        file_size = fp.stat().st_size
        filepath_str = str(fp)

        # Get offset from checkpoint manager
        offset = 0
        if self._checkpoint_manager:
            offset = self._checkpoint_manager.get_offset(filepath_str)

        if offset >= file_size:
            # No new data — skip (nothing to parse)
            return None

        # Read from offset to EOF
        lines = self._read_from_offset(fp, offset, max_lines=200)
        if not lines:
            return None

        # Parse lines and extract state
        state = self._parse_jsonl_lines_to_state(lines, agent_id)
        if state:
            # Update checkpoint
            bytes_read = file_size - offset
            if self._checkpoint_manager:
                self._checkpoint_manager.update_offset(
                    filepath_str,
                    offset=file_size,
                    bytes_read=bytes_read,
                )
            return state

        return None

    def _read_from_offset(self, fp: Any, offset: int, max_lines: int = 200) -> List[str]:
        """Read lines from file starting at byte offset.

        Returns at most max_lines non-empty lines from the offset.
        """
        try:
            with open(fp, "rb") as f:
                if offset > 0:
                    f.seek(offset)
                    buf = f.read(512 * 1024)  # Read up to 512KB from offset
                else:
                    # First read: fall back to tail-read behavior (512KB from end)
                    size = f.seek(0, 2)
                    to_read = min(512 * 1024, size)
                    f.seek(size - to_read)
                    buf = f.read(to_read)

                if not buf:
                    return []

                # Split into lines and limit
                lines = buf.split(b"\n")
                decoded = []
                for ln in lines:
                    ln = ln.decode("utf-8", errors="replace").strip()
                    if ln:
                        decoded.append(ln)
                        if len(decoded) >= max_lines:
                            break
                return decoded
        except (IOError, OSError):
            return []

    def _parse_jsonl_lines_to_state(
        self, lines: List[str], agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """Parse JSONL lines and extract agent state fields.

        Scans lines in reverse for the latest status indicators.
        """
        import json

        partial: Dict[str, Any] = {}

        for line in reversed(lines):
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")
            role = msg.get("role", "")

            # Check for thinking content in assistant messages
            if role == "assistant" and not msg.get("stopReason"):
                content = msg.get("content", [])
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "thinking":
                            partial["has_thinking"] = True
                            break

            # Check for pending tool calls
            if role == "assistant":
                content = msg.get("content", [])
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "toolCall":
                            tc_id = c.get("id")
                            if tc_id and not partial.get("has_pending_tool"):
                                partial["has_pending_tool"] = True
                                partial["pending_tool_name"] = c.get("name", "")

            # Check for tool results
            if role == "toolResult":
                tc_id = msg.get("toolCallId") or msg.get("tool_call_id")
                if tc_id:
                    partial.setdefault("tool_results", set()).add(tc_id)

            # Check for errors
            if msg.get("stopReason") == "error":
                partial["error"] = {
                    "type": "unknown",
                    "message": msg.get("errorMessage", ""),
                    "timestamp": msg.get("timestamp", 0),
                }

            # Check for active timestamp
            ts = msg.get("timestamp", 0)
            if isinstance(ts, (int, float)) and ts > partial.get("last_ts", 0):
                partial["last_ts"] = ts

        # Convert to state dict
        if not partial:
            return None

        return self._partial_to_state(agent_id, partial)

    def _partial_to_state(
        self, agent_id: str, partial: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convert parsed partial data to StateStore-compatible state dict."""
        from data.session_reader import get_session_updated_at
        from data.subagent_reader import is_agent_working
        from status.status_calculator import format_last_active

        status = "idle"
        current_task = ""
        error = None

        # Determine status
        if partial.get("error"):
            status = "down"
            error = partial["error"]
        elif partial.get("has_thinking"):
            status = "working"
        elif partial.get("has_pending_tool"):
            status = "working"
            current_task = f"执行: {partial.get('pending_tool_name', '')}"
        elif is_agent_working(agent_id):
            status = "working"

        # Get task info
        if not current_task:
            try:
                from status.status_calculator import get_current_task
                current_task = get_current_task(agent_id)
                if status == "idle" and not current_task:
                    current_task = ""
            except Exception:
                pass

        # Get last active time
        last_active = 0
        try:
            last_active = get_session_updated_at(agent_id) or 0
        except Exception:
            last_active = partial.get("last_ts", 0)

        return {
            "status": status,
            "currentTask": current_task,
            "lastActiveAt": last_active,
            "error": error,
        }

    def _tail_to_state(self, agent_id: str, tail: Dict[str, Any]) -> Dict[str, Any]:
        """Convert tail_read_session output to StateStore state dict."""
        from data.session_reader import get_session_updated_at
        from data.subagent_reader import is_agent_working
        from status.status_calculator import format_last_active

        # Determine status from tail data
        status = "idle"
        current_task = ""
        error = None

        # Check for errors
        if tail.get("stop_reason") == "error":
            status = "down"
            error = {
                "type": "unknown",
                "message": tail.get("error_message", ""),
                "timestamp": tail.get("last_message_timestamp", 0),
            }
        elif tail.get("has_thinking") or (
            tail.get("pending_tool_call") and not tail.get("pending_tool_call", {}).get("hasResult")
        ):
            status = "working"
            tc = tail.get("pending_tool_call")
            if tc:
                current_task = f"执行: {tc.get('name', '')}"
        elif is_agent_working(agent_id):
            status = "working"
        elif tail.get("is_active"):
            status = "working"

        # Get task info
        if not current_task:
            try:
                from status.status_calculator import get_current_task
                current_task = get_current_task(agent_id)
                if status == "idle" and not current_task:
                    current_task = ""
            except Exception:
                pass

        # Get last active time
        last_active = 0
        try:
            last_active = get_session_updated_at(agent_id) or 0
        except Exception:
            last_active = tail.get("last_message_timestamp", 0)

        return {
            "status": status,
            "currentTask": current_task,
            "lastActiveAt": last_active,
            "error": error,
        }

    def _calculator_fallback(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Fallback: use calculate_agent_status() for this single agent."""
        from status.status_calculator import (
            calculate_agent_status,
            get_current_task,
            get_last_active_time,
            get_last_error,
        )

        status = calculate_agent_status(agent_id, use_cache=False)
        current_task = get_current_task(agent_id)
        if status == "idle" and not current_task:
            current_task = ""
        last_active = get_last_active_time(agent_id)
        error = get_last_error(agent_id) if status == "down" else None

        return {
            "status": status,
            "currentTask": current_task,
            "lastActiveAt": last_active,
            "error": error,
        }


# ── module-level singleton ─────────────────────────────────────

_ingestor: Optional[AgentStateIngestor] = None


def get_ingestor() -> AgentStateIngestor:
    global _ingestor
    if _ingestor is None:
        _ingestor = AgentStateIngestor()
    return _ingestor


def reset_ingestor_for_tests() -> None:
    global _ingestor
    _ingestor = None
