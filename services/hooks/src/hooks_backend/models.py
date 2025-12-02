"""Pydantic models for the hooks backend service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class HookEventIn(BaseModel):
    """Input model for hook events received via API.

    Attributes:
        event_type: Type of event (e.g., "session_started").
        session_id: Unique session identifier.
        event_id: Optional unique event identifier (auto-generated if not provided).
        workflow_id: Optional workflow identifier.
        phase_id: Optional phase identifier.
        milestone_id: Optional milestone identifier.
        data: Flexible event data payload.
        timestamp: Event timestamp (auto-generated if not provided).
    """

    event_type: str
    session_id: str
    event_id: str | None = Field(default_factory=lambda: str(uuid4()))
    workflow_id: str | None = None
    phase_id: str | None = None
    milestone_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"extra": "ignore"}


class HookEventStored(BaseModel):
    """Model for stored hook events.

    Same as HookEventIn but with required fields populated.
    """

    event_id: str
    event_type: str
    session_id: str
    workflow_id: str | None = None
    phase_id: str | None = None
    milestone_id: str | None = None
    data: dict[str, Any]
    timestamp: datetime

    @classmethod
    def from_input(cls, event: HookEventIn) -> HookEventStored:
        """Create stored event from input event.

        Args:
            event: Input event from API.

        Returns:
            Stored event with all fields populated.
        """
        return cls(
            event_id=event.event_id or str(uuid4()),
            event_type=event.event_type,
            session_id=event.session_id,
            workflow_id=event.workflow_id,
            phase_id=event.phase_id,
            milestone_id=event.milestone_id,
            data=event.data,
            timestamp=event.timestamp or datetime.now(UTC),
        )


class EventsAcceptedResponse(BaseModel):
    """Response model for accepted events.

    Attributes:
        accepted: Number of events accepted.
        message: Optional message.
    """

    accepted: int
    message: str = "Events accepted"


class HealthResponse(BaseModel):
    """Response model for health check.

    Attributes:
        status: Health status ("healthy" or "unhealthy").
        storage: Storage backend type in use.
        version: Service version.
    """

    status: str
    storage: str
    version: str


class MetricsResponse(BaseModel):
    """Response model for metrics.

    Attributes:
        events_received_total: Total events received.
        events_stored_total: Total events stored.
        storage_errors_total: Total storage errors.
        uptime_seconds: Service uptime in seconds.
    """

    events_received_total: int
    events_stored_total: int
    storage_errors_total: int
    uptime_seconds: float
