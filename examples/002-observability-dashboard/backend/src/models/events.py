"""Event models matching the hook output format."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditContext(BaseModel):
    """Audit trail context from Claude Code."""

    transcript_path: str | None = None
    cwd: str | None = None
    permission_mode: str | None = None


class AgentEvent(BaseModel):
    """Base event model matching hook analytics output."""

    timestamp: datetime
    event_type: str
    handler: str
    hook_event: str | None = None
    tool_name: str | None = None
    session_id: str | None = None
    tool_use_id: str | None = None
    audit: AuditContext | None = None

    # Computed fields (not from hooks)
    id: str | None = None  # Generated UUID
    estimated_tokens: int | None = None
    estimated_cost_usd: float | None = None


class HookDecisionEvent(AgentEvent):
    """PreToolUse hook decision event."""

    decision: str  # "allow" or "block"
    reason: str | None = None
    tool_input_preview: str | None = None
    validators_run: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class ToolExecutionEvent(AgentEvent):
    """PostToolUse tool execution event."""

    success: bool = True
    output_preview: str | None = None
    input_preview: str | None = None


class UserPromptEvent(AgentEvent):
    """UserPromptSubmit event."""

    prompt_preview: str | None = None
    pii_detected: bool = False
    pii_types: list[str] = Field(default_factory=list)


class SessionEvent(AgentEvent):
    """Session start/end event."""

    session_start: datetime | None = None
    session_end: datetime | None = None
    model: str | None = None
