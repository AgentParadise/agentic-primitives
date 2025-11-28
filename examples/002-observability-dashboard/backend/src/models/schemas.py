"""API response schemas."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class EventResponse(BaseModel):
    """Single event in API response."""

    model_config = ConfigDict(ser_json_timedelta="iso8601")

    id: str
    timestamp: datetime

    @field_serializer("timestamp")
    def serialize_timestamp(self, dt: datetime) -> str:
        """Serialize timestamp with UTC timezone for JS compatibility."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    event_type: str
    handler: str
    hook_event: str | None = None
    tool_name: str | None = None
    session_id: str | None = None
    decision: str | None = None
    reason: str | None = None
    success: bool | None = None
    estimated_tokens: int | None = None
    estimated_cost_usd: float | None = None
    input_preview: str | None = None  # File path, command, etc.


class SessionSummary(BaseModel):
    """Session summary for list view."""

    session_id: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    model: str | None = None
    total_events: int = 0
    tool_calls: int = 0
    blocked_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0


class SessionDetail(SessionSummary):
    """Session detail with events."""

    events: list[EventResponse] = Field(default_factory=list)
    tools_used: dict[str, int] = Field(default_factory=dict)  # tool_name -> count


class MetricsResponse(BaseModel):
    """Aggregated metrics response."""

    # Totals
    total_sessions: int = 0
    total_events: int = 0
    total_tool_calls: int = 0
    total_blocked: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0

    # By time period
    tokens_last_hour: int = 0
    tokens_last_24h: int = 0
    cost_last_hour: float = 0.0
    cost_last_24h: float = 0.0

    # By tool
    calls_by_tool: dict[str, int] = Field(default_factory=dict)
    blocks_by_tool: dict[str, int] = Field(default_factory=dict)

    # By model
    tokens_by_model: dict[str, int] = Field(default_factory=dict)
    cost_by_model: dict[str, float] = Field(default_factory=dict)


class TimeSeriesPoint(BaseModel):
    """Single point in time series data."""

    timestamp: datetime
    value: float


class TimeSeriesResponse(BaseModel):
    """Time series data for charts."""

    metric: str  # "tokens", "cost", "events"
    interval: str  # "hour", "day"
    data: list[TimeSeriesPoint] = Field(default_factory=list)
