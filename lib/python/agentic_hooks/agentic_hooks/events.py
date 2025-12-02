"""Event schemas for agentic hooks.

This module defines the canonical event types emitted by agent systems.
All events follow a common structure with session context and flexible data payload.

Event Types:
    - SESSION_STARTED: Agent session begins
    - SESSION_COMPLETED: Agent session ends
    - TOOL_EXECUTION_STARTED: Tool execution begins
    - TOOL_EXECUTION_COMPLETED: Tool execution ends
    - TOOL_BLOCKED: Tool blocked by security hook
    - AGENT_REQUEST_STARTED: Agent request begins
    - AGENT_REQUEST_COMPLETED: Agent request ends
    - USER_PROMPT_SUBMITTED: User prompt received
    - HOOK_DECISION: Hook decision made
    - CUSTOM: Custom event type

Example:
    from agentic_hooks import HookEvent, EventType

    event = HookEvent(
        event_type=EventType.TOOL_EXECUTION_STARTED,
        session_id="session-123",
        workflow_id="workflow-456",
        data={"tool_name": "Write", "file_path": "app.py"},
    )
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4


def _now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(UTC)


def _new_id() -> str:
    """Generate new UUID string."""
    return str(uuid4())


class EventType(str, Enum):
    """Canonical hook event types.

    These represent the standard lifecycle events in agent systems.
    Use CUSTOM for application-specific events.
    """

    # Session lifecycle
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"

    # Tool execution
    TOOL_EXECUTION_STARTED = "tool_execution_started"
    TOOL_EXECUTION_COMPLETED = "tool_execution_completed"
    TOOL_BLOCKED = "tool_blocked"

    # Agent requests
    AGENT_REQUEST_STARTED = "agent_request_started"
    AGENT_REQUEST_COMPLETED = "agent_request_completed"

    # User prompts
    USER_PROMPT_SUBMITTED = "user_prompt_submitted"

    # Hook decisions
    HOOK_DECISION = "hook_decision"

    # Custom events
    CUSTOM = "custom"


@dataclass
class HookEvent:
    """Event emitted by hooks for observability.

    This is the primary event type used throughout the hook system.
    Events are buffered, batched, and sent to the backend service.

    Attributes:
        event_type: Type of event (from EventType enum or custom string)
        session_id: Unique identifier for the agent session
        workflow_id: Optional workflow identifier
        phase_id: Optional phase identifier within workflow
        milestone_id: Optional milestone identifier within phase
        data: Flexible data payload (tool inputs, decisions, etc.)
        event_id: Auto-generated unique event identifier
        timestamp: Auto-generated UTC timestamp

    Example:
        event = HookEvent(
            event_type=EventType.TOOL_EXECUTION_STARTED,
            session_id="session-123",
            data={"tool_name": "Write", "file_path": "app.py"},
        )
    """

    event_type: EventType | str
    session_id: str

    # Optional context identifiers
    workflow_id: str | None = None
    phase_id: str | None = None
    milestone_id: str | None = None

    # Flexible data payload
    data: dict[str, Any] = field(default_factory=dict)

    # Auto-generated fields
    event_id: str = field(default_factory=_new_id)
    timestamp: datetime = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation suitable for JSON encoding.
        """
        return {
            "event_id": self.event_id,
            "event_type": (
                self.event_type.value if isinstance(self.event_type, EventType) else self.event_type
            ),
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "phase_id": self.phase_id,
            "milestone_id": self.milestone_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HookEvent":
        """Create HookEvent from dictionary.

        Args:
            data: Dictionary with event fields.

        Returns:
            HookEvent instance.
        """
        # Handle event_type - try to convert to enum, fallback to string
        event_type_raw = data.get("event_type", "custom")
        try:
            event_type: EventType | str = EventType(event_type_raw)
        except ValueError:
            event_type = event_type_raw

        # Parse timestamp
        timestamp_raw = data.get("timestamp")
        if isinstance(timestamp_raw, str):
            timestamp = datetime.fromisoformat(timestamp_raw)
        elif isinstance(timestamp_raw, datetime):
            timestamp = timestamp_raw
        else:
            timestamp = _now()

        return cls(
            event_type=event_type,
            session_id=data.get("session_id", ""),
            workflow_id=data.get("workflow_id"),
            phase_id=data.get("phase_id"),
            milestone_id=data.get("milestone_id"),
            data=data.get("data", {}),
            event_id=data.get("event_id", _new_id()),
            timestamp=timestamp,
        )
