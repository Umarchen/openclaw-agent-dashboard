"""
AgentStateIngestor — C0 file change to state store pipeline.

Listens for FileChangeEvent via EventBus, extracts agent state via tail-read,
and writes to StateStore. On tail-read failure, falls back to calculate_agent_status()
for the affected agent only.
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
    2. For each affected agent, extract state via tail_read_session()
    3. On tail_read failure, fallback to calculate_agent_status()
    4. Write state to StateStore
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

    def initialize(self) -> None:
        """Subscribe to EventBus topics. Call once during startup."""
        if self._initialized:
            return
        self._event_bus.subscribe(TOPIC_FILE_CHANGES, self._on_file_change)
        self._event_bus.subscribe(TOPIC_HEARTBEAT, self._on_heartbeat_tick)
        self._initialized = True
        _LOG.info("AgentStateIngestor initialized")

    def shutdown(self) -> None:
        """Unsubscribe from EventBus."""
        # Note: current EventBus API requires SubscriptionHandle to unsubscribe.
        # For C0, we just flag as not initialized.
        self._initialized = False
        _LOG.info("AgentStateIngestor shutdown")

    def _on_file_change(self, event: BaseEvent) -> None:
        """Handle FileChangeEvent: extract affected agents and ingest."""
        if not isinstance(event, FileChangeEvent):
            return

        self._metrics.increment(MetricsCollector.EVT_PROCESSED)
        start = time.monotonic()

        try:
            if event.agent_id:
                # Single agent affected
                self._ingest_agent(event.agent_id)
            else:
                # No specific agent — could be runs.json (global), ingest all
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
        """Extract state for a single agent and write to StateStore."""
        state = self._extract_agent_state(agent_id)
        if state:
            self._state_store.update_agent(agent_id, state)
            self._metrics.increment(MetricsCollector.STATE_UPDATE)

    def _extract_agent_state(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Extract agent state. tail_read first, fallback to calculator."""
        # Try tail_read_session first
        try:
            from data.session_reader import tail_read_session

            tail = tail_read_session(agent_id)
            if tail:
                return self._tail_to_state(agent_id, tail)
        except Exception as e:
            _LOG.debug("tail_read failed for %s: %s, falling back", agent_id, e)

        # Fallback: calculate_agent_status for this agent only
        try:
            return self._calculator_fallback(agent_id)
        except Exception as e:
            _LOG.error("calculator fallback failed for %s: %s", agent_id, e)
            return None

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
