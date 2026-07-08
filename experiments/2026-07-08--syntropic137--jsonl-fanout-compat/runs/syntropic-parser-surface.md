# Syntropic137 Parser Surface

## hook_parser.py excerpt
"""Hook event parsing logic.

Extracted from HookWatcher to reduce module complexity.
"""

from __future__ import annotations

import logging
from typing import Any

from syn_collector.events.types import CollectedEvent, EventType
from syn_collector.watcher.event_id import dispatch_event_id
from syn_collector.watcher.parsing import parse_timestamp

logger = logging.getLogger(__name__)

# Mapping from hook event types to our EventType enum
HOOK_EVENT_MAP: dict[str, EventType] = {
    # Session lifecycle events
    "session_started": EventType.SESSION_STARTED,
    "session_ended": EventType.SESSION_ENDED,
    "agent_stopped": EventType.AGENT_STOPPED,
    "subagent_started": EventType.SUBAGENT_STARTED,
    "subagent_stopped": EventType.SUBAGENT_STOPPED,
    # Tool execution events
    "tool_execution_started": EventType.TOOL_EXECUTION_STARTED,
    "tool_execution_completed": EventType.TOOL_EXECUTION_COMPLETED,
    "tool_blocked": EventType.TOOL_BLOCKED,
    # User interaction events
    "user_prompt_submitted": EventType.USER_PROMPT_SUBMITTED,
    "notification_sent": EventType.NOTIFICATION_SENT,
    # Context management
    "pre_compact": EventType.PRE_COMPACT,
    # Git operations (current emitter names from agentic_events.EventType)
    "git_commit": EventType.GIT_COMMIT,
    "git_push": EventType.GIT_PUSH,
    "git_merge": EventType.GIT_MERGE,
    "git_rewrite": EventType.GIT_REWRITE,
    "git_checkout": EventType.GIT_CHECKOUT,
    "git_branch_changed": EventType.GIT_BRANCH_CHANGED,
    "git_operation": EventType.GIT_OPERATION,
    # Legacy git event names (kept for backward compat)
    "git_branch_created": EventType.GIT_BRANCH_CREATED,
    "git_branch_switched": EventType.GIT_BRANCH_SWITCHED,
    "git_merge_completed": EventType.GIT_MERGE_COMPLETED,
    "git_commits_rewritten": EventType.GIT_COMMITS_REWRITTEN,
    "git_push_started": EventType.GIT_PUSH_STARTED,
    "git_push_completed": EventType.GIT_PUSH_COMPLETED,
    # Hook handler name mappings (alternative names)
    "pre-tool-use": EventType.TOOL_EXECUTION_STARTED,
    "post-tool-use": EventType.TOOL_EXECUTION_COMPLETED,
    "session-start": EventType.SESSION_STARTED,
    "session-end": EventType.SESSION_ENDED,
    "user-prompt": EventType.USER_PROMPT_SUBMITTED,
    "stop": EventType.AGENT_STOPPED,
    "subagent-start": EventType.SUBAGENT_STARTED,
    "subagent-stop": EventType.SUBAGENT_STOPPED,
    "notification": EventType.NOTIFICATION_SENT,
}


def parse_hook_event(
    data: dict[str, Any],
    session_id_override: str | None = None,
) -> CollectedEvent | None:
    """Parse a hook event dict into CollectedEvent.

    Args:
        data: Raw JSON data from hook file.
        session_id_override: Fallback session ID if not in data.

    Returns:
        CollectedEvent or None if invalid.
    """
    raw_event_type = data.get("event_type") or data.get("handler", "")
    event_type = HOOK_EVENT_MAP.get(raw_event_type)

    if event_type is None:
        logger.debug(f"Unknown hook event type: {raw_event_type}")
        return None

    session_id = data.get("session_id") or session_id_override
    if not session_id:
        logger.warning("Hook event missing session_id")
        return None

    timestamp = parse_timestamp(data.get("timestamp"))
    event_id = dispatch_event_id(event_type, session_id, timestamp, data)

    event_data = {
        k: v
        for k, v in data.items()
        if k not in ("event_type", "handler", "session_id", "timestamp")
    }

    return CollectedEvent(
        event_id=event_id,
        event_type=event_type,
        session_id=session_id,
        timestamp=timestamp,
        data=event_data,
    )

## events/types.py CollectedEvent excerpt
"""Event type definitions for Syn137 collector.

Defines the core event types used throughout the collection system:
- CollectedEvent: Individual event with deterministic ID
- EventBatch: Batched events from a sidecar
- BatchResponse: Response from collector service
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - used at runtime by Pydantic
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """Event types collected from hooks and transcripts.

    Session lifecycle:
    - SESSION_STARTED: Agent session begins
    - SESSION_ENDED: Agent session ends
    - AGENT_STOPPED: Agent stopped (normal completion or interrupt)
    - SUBAGENT_STOPPED: Subagent completed

    Tool execution:
    - TOOL_EXECUTION_STARTED: Tool call initiated (PreToolUse)
    - TOOL_EXECUTION_COMPLETED: Tool call finished (PostToolUse)
    - TOOL_BLOCKED: Tool call blocked by validation

    User interaction:
    - USER_PROMPT_SUBMITTED: User submitted a prompt
    - NOTIFICATION_SENT: Notification sent to user

    Token usage:
    - TOKEN_USAGE: Per-turn token metrics from transcript

    Context management:
    - PRE_COMPACT: Context compaction triggered

    Git operations:
    - GIT_COMMIT: Git commit completed with metrics
    - GIT_BRANCH_CREATED: New branch created
    - GIT_BRANCH_SWITCHED: Switched to existing branch
    - GIT_MERGE_COMPLETED: Merge completed
    - GIT_COMMITS_REWRITTEN: Commits rewritten (rebase/amend)
    - GIT_PUSH_STARTED: Push operation started
    - GIT_PUSH_COMPLETED: Push operation completed

    Workspace lifecycle (isolated sandbox environments):
    - WORKSPACE_CREATING: Workspace creation started
    - WORKSPACE_CREATED: Workspace ready for use
    - WORKSPACE_COMMAND_EXECUTED: Command executed in workspace
    - WORKSPACE_DESTROYING: Workspace cleanup started
    - WORKSPACE_DESTROYED: Workspace fully cleaned up
    - WORKSPACE_ERROR: Workspace operation failed

    OTLP-sourced events (OTel channel — from workspace containers):
    - OTLP_LOG: Raw OTel log record (unrecognised event name)
    - API_REQUEST: Per-API-call metrics (model, cost, cache tokens, duration)
    - API_ERROR: API error with status code and retry count
    - OTLP_SESSION_COUNT: OTel session counter (distinct from hook SESSION_STARTED)
    - OTLP_COMMIT_COUNT: OTel commit counter (distinct from hook GIT_COMMIT)
    """

    # Session lifecycle
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    AGENT_STOPPED = "agent_stopped"
    SUBAGENT_STARTED = "subagent_started"
    SUBAGENT_STOPPED = "subagent_stopped"

    # Tool execution
    TOOL_EXECUTION_STARTED = "tool_execution_started"
    TOOL_EXECUTION_COMPLETED = "tool_execution_completed"
    TOOL_BLOCKED = "tool_blocked"

    # User interaction
    USER_PROMPT_SUBMITTED = "user_prompt_submitted"
    NOTIFICATION_SENT = "notification_sent"

    # Token usage
    TOKEN_USAGE = "token_usage"

    # Context management
    PRE_COMPACT = "pre_compact"

    # Git operations (current names - match syn_shared.events and agentic_events.EventType)
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    GIT_MERGE = "git_merge"
    GIT_REWRITE = "git_rewrite"
    GIT_CHECKOUT = "git_checkout"
    GIT_BRANCH_CHANGED = "git_branch_changed"
    GIT_OPERATION = "git_operation"
    # Legacy names (kept for backward compat with old hook events already in DB)
    GIT_BRANCH_CREATED = "git_branch_created"
    GIT_BRANCH_SWITCHED = "git_branch_switched"
    GIT_MERGE_COMPLETED = "git_merge_completed"
    GIT_COMMITS_REWRITTEN = "git_commits_rewritten"
    GIT_PUSH_STARTED = "git_push_started"
    GIT_PUSH_COMPLETED = "git_push_completed"

    # Workspace lifecycle (isolated sandbox environments)
    WORKSPACE_CREATING = "workspace_creating"
    WORKSPACE_CREATED = "workspace_created"
    WORKSPACE_COMMAND_EXECUTED = "workspace_command_executed"
    WORKSPACE_DESTROYING = "workspace_destroying"
    WORKSPACE_DESTROYED = "workspace_destroyed"
    WORKSPACE_ERROR = "workspace_error"

    # Cost tracking
    COST_RECORDED = "cost_recorded"
    SESSION_COST_FINALIZED = "session_cost_finalized"

    # OTLP-sourced events
    OTLP_LOG = "otlp_log"
    API_REQUEST = "api_request"  # Per-API-call cost, model, cache tokens, duration
    API_ERROR = "api_error"  # API error with status code and retry context
    OTLP_SESSION_COUNT = (
        "otlp_session_count"  # OTel session counter (distinct from hook session_started)
    )
    OTLP_COMMIT_COUNT = "otlp_commit_count"  # OTel commit counter (distinct from hook git_commit)


class CollectedEvent(BaseModel):
    """A single collected event with deterministic ID.

    The event_id is generated deterministically from content
    to enable deduplication across retries.

    Attributes:
        event_id: Deterministic ID for deduplication (SHA256 hash)
        event_type: Type of event (from EventType enum)
        session_id: Agent session identifier
        timestamp: When the event occurred (ISO 8601)
        data: Event-specific payload
    """

    event_id: str = Field(
        ...,
        description="Deterministic ID for deduplication",
        min_length=16,
        max_length=64,
    )
    event_type: EventType = Field(..., description="Type of event")
    session_id: str = Field(..., description="Agent session identifier")
    timestamp: datetime = Field(..., description="When the event occurred")
    data: dict[str, Any] = Field(default_factory=dict, description="Event-specific payload")

    model_config = {"frozen": True}


class EventBatch(BaseModel):
    """Batch of events from a sidecar.

    Events are batched to reduce network overhead.
    The batch_id is used for idempotent processing.

    Attributes:
        agent_id: Identifier for the agent sending events
        batch_id: Unique identifier for this batch
        events: List of collected events
    """
