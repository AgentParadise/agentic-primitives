"""Canonical event schemas for agentic analytics.

These are the standard event types emitted by agent systems. All events
follow a common structure with provider-agnostic fields plus optional
provider-specific extensions.

Event Types:
    - SessionStarted: Agent session begins
    - TokensUsed: Tokens consumed per interaction
    - ToolCalled: Tool invocation with correlation ID
    - SessionEnded: Agent session ends with aggregates

Correlation:
    Events are linked via session_id and tool_use_id:
    - session_id: Groups all events in an agent session
    - tool_use_id: Links tool calls to hook decisions (per ADR-016)

Example:
    from agentic_analytics import SessionStarted, TokensUsed, ToolCalled, SessionEnded

    # Start session
    session = SessionStarted(
        session_id="sess-abc123",
        model="claude-sonnet-4-5-20250929",
        provider="anthropic",
    )

    # Track token usage
    tokens = TokensUsed(
        session_id="sess-abc123",
        input_tokens=1500,
        output_tokens=500,
    )

    # Track tool call
    tool = ToolCalled(
        session_id="sess-abc123",
        tool_use_id="toolu_01ABC",
        tool_name="Write",
        tool_input={"file_path": "app.py", "content": "..."},
    )
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


def _now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(UTC)


@dataclass
class AuditContext:
    """Provider-specific audit trail context.

    Used by Claude Code to provide additional debugging information.
    Other providers can extend this or create their own context.

    Attributes:
        transcript_path: Path to the full conversation transcript
        cwd: Current working directory during execution
        permission_mode: Permission level (e.g., "default", "full-auto")
        env_id: Environment identifier for multi-env setups
    """

    transcript_path: str | None = None
    cwd: str | None = None
    permission_mode: str | None = None
    env_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            k: v
            for k, v in {
                "transcript_path": self.transcript_path,
                "cwd": self.cwd,
                "permission_mode": self.permission_mode,
                "env_id": self.env_id,
            }.items()
            if v is not None
        }


@dataclass
class SessionStarted:
    """Emitted when an agent session begins.

    This is the first event in any session and establishes the context
    for all subsequent events.

    Attributes:
        session_id: Unique identifier for this session
        model: Model identifier (e.g., "claude-sonnet-4-5-20250929")
        provider: Provider name (e.g., "anthropic", "openai", "google")
        timestamp: When the session started (auto-generated if not provided)
        model_display_name: Human-readable model name
        pricing: Cost per token information for cost calculations
        audit: Optional provider-specific audit context
        metadata: Additional session context
    """

    session_id: str
    model: str
    provider: str
    timestamp: datetime = field(default_factory=_now)
    model_display_name: str | None = None
    pricing: dict[str, float] | None = None  # {"input_per_1m_tokens": X, "output_per_1m_tokens": Y}
    audit: AuditContext | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        return "session.started"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "session_id": self.session_id,
            "data": {
                "model": self.model,
                "provider": self.provider,
            },
        }
        if self.model_display_name:
            result["data"]["model_display_name"] = self.model_display_name
        if self.pricing:
            result["data"]["pricing"] = self.pricing
        if self.audit:
            result["audit"] = self.audit.to_dict()
        if self.metadata:
            result["data"]["metadata"] = self.metadata
        return result


@dataclass
class TokensUsed:
    """Emitted per interaction (prompt/response cycle).

    Tracks token consumption for cost estimation and efficiency metrics.

    Attributes:
        session_id: Session this interaction belongs to
        input_tokens: Tokens in the prompt/context
        output_tokens: Tokens in the response
        timestamp: When this interaction occurred
        duration_ms: Time taken for the interaction (optional)
        prompt_preview: First N chars of prompt for debugging
        response_preview: First N chars of response for debugging
        interaction_index: Position in session (0-based, optional)
        metadata: Additional interaction context
    """

    session_id: str
    input_tokens: int
    output_tokens: int
    timestamp: datetime = field(default_factory=_now)
    duration_ms: float | None = None
    prompt_preview: str | None = None
    response_preview: str | None = None
    interaction_index: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        return "tokens.used"

    @property
    def total_tokens(self) -> int:
        """Total tokens for this interaction."""
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "session_id": self.session_id,
            "data": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
            },
        }
        if self.duration_ms is not None:
            result["data"]["duration_ms"] = self.duration_ms
        if self.prompt_preview:
            result["data"]["prompt_preview"] = self.prompt_preview
        if self.response_preview:
            result["data"]["response_preview"] = self.response_preview
        if self.interaction_index is not None:
            result["data"]["interaction_index"] = self.interaction_index
        if self.metadata:
            result["data"]["metadata"] = self.metadata
        return result


@dataclass
class ToolCalled:
    """Emitted when a tool is invoked.

    This event captures tool usage for analytics and correlates with
    hook decisions via tool_use_id (per ADR-016).

    Attributes:
        session_id: Session this tool call belongs to
        tool_name: Name of the tool (e.g., "Write", "Bash", "Read")
        tool_input: Input parameters for the tool
        tool_use_id: Unique ID for correlating with hook decisions
        timestamp: When the tool was called
        tool_output: Output from the tool (optional, may be truncated)
        duration_ms: Time taken for the tool call
        blocked: Whether the tool call was blocked by a hook
        block_reason: Reason for blocking (if blocked)
        hook_decision: Decision from pre-tool-use hook ("allow", "block", "warn")
        metadata: Additional tool context
    """

    session_id: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str | None = None
    timestamp: datetime = field(default_factory=_now)
    tool_output: str | None = None
    duration_ms: float | None = None
    blocked: bool = False
    block_reason: str | None = None
    hook_decision: Literal["allow", "block", "warn"] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        return "tool.called"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "session_id": self.session_id,
            "data": {
                "tool_name": self.tool_name,
                "tool_input": self.tool_input,
                "blocked": self.blocked,
            },
        }
        if self.tool_use_id:
            result["tool_use_id"] = self.tool_use_id
        if self.tool_output:
            result["data"]["tool_output"] = self.tool_output
        if self.duration_ms is not None:
            result["data"]["duration_ms"] = self.duration_ms
        if self.block_reason:
            result["data"]["block_reason"] = self.block_reason
        if self.hook_decision:
            result["data"]["hook_decision"] = self.hook_decision
        if self.metadata:
            result["data"]["metadata"] = self.metadata
        return result


@dataclass
class SessionEnded:
    """Emitted when an agent session completes.

    Contains aggregate metrics for the entire session for efficiency
    and cost tracking.

    Attributes:
        session_id: Session that ended
        timestamp: When the session ended
        start_time: When the session started (for duration calculation)
        total_input_tokens: Sum of input tokens across all interactions
        total_output_tokens: Sum of output tokens across all interactions
        total_cost_usd: Estimated total cost in USD
        interaction_count: Number of prompt/response cycles
        tool_call_count: Total number of tool calls
        tool_calls_blocked: Number of tool calls blocked by hooks
        total_duration_ms: Total time for all interactions
        model: Model used (optional, already in SessionStarted)
        exit_reason: Why the session ended (e.g., "completed", "error", "timeout")
        metadata: Additional session summary context
    """

    session_id: str
    timestamp: datetime = field(default_factory=_now)
    start_time: datetime | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    interaction_count: int = 0
    tool_call_count: int = 0
    tool_calls_blocked: int = 0
    total_duration_ms: float = 0.0
    model: str | None = None
    exit_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        return "session.ended"

    @property
    def total_tokens(self) -> int:
        """Total tokens for entire session."""
        return self.total_input_tokens + self.total_output_tokens

    @property
    def avg_tokens_per_interaction(self) -> float:
        """Average tokens per interaction."""
        if self.interaction_count == 0:
            return 0.0
        return self.total_tokens / self.interaction_count

    @property
    def tokens_per_second(self) -> float:
        """Token velocity (tokens per second)."""
        if self.total_duration_ms == 0:
            return 0.0
        return self.total_tokens / (self.total_duration_ms / 1000)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "session_id": self.session_id,
            "data": {
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_tokens": self.total_tokens,
                "total_cost_usd": self.total_cost_usd,
                "interaction_count": self.interaction_count,
                "tool_call_count": self.tool_call_count,
                "tool_calls_blocked": self.tool_calls_blocked,
                "total_duration_ms": self.total_duration_ms,
                "avg_tokens_per_interaction": self.avg_tokens_per_interaction,
                "tokens_per_second": self.tokens_per_second,
            },
        }
        if self.start_time:
            result["data"]["start_time"] = self.start_time.isoformat()
        if self.model:
            result["data"]["model"] = self.model
        if self.exit_reason:
            result["data"]["exit_reason"] = self.exit_reason
        if self.metadata:
            result["data"]["metadata"] = self.metadata
        return result


# Type alias for all event types (useful for type hints)
AgentEvent = SessionStarted | TokensUsed | ToolCalled | SessionEnded
