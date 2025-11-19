"""Pydantic models for normalized analytics events

These models represent the standardized event structure after normalization.
They are provider-agnostic and follow a consistent schema regardless of the source.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Event type enumeration
EventType = Literal[
    "session_started",
    "session_completed",
    "user_prompt_submitted",
    "tool_execution_started",
    "tool_execution_completed",
    "permission_requested",
    "agent_stopped",
    "subagent_stopped",
    "system_notification",
    "context_compacted",
]


# Context models for different event types
class ToolExecutionContext(BaseModel):
    """Context for tool execution events (started/completed)"""

    tool_name: str = Field(description="Name of the tool")
    tool_input: dict[str, Any] = Field(description="Input parameters")
    tool_response: dict[str, Any] | None = Field(
        default=None, description="Response (only for completed events)"
    )
    tool_use_id: str | None = Field(default=None, description="Tool use identifier")


class UserPromptContext(BaseModel):
    """Context for user prompt submission events"""

    prompt: str = Field(description="The prompt text")
    prompt_length: int = Field(description="Length of prompt in characters")


class SessionContext(BaseModel):
    """Context for session start/end events"""

    source: str | None = Field(
        default=None, description="Session start source (startup, resume, etc.)"
    )
    reason: str | None = Field(default=None, description="Session end reason (exit, error, etc.)")


class NotificationContext(BaseModel):
    """Context for system notifications"""

    notification_type: str = Field(description="Type of notification")
    message: str = Field(description="Notification message")


class CompactContext(BaseModel):
    """Context for context compaction events"""

    trigger: str = Field(description="Trigger type (manual or auto)")
    custom_instructions: str | None = Field(
        default=None, description="Custom instructions if manual"
    )


class StopContext(BaseModel):
    """Context for agent/subagent stop events"""

    stop_hook_active: bool = Field(description="Whether stop hook was active")


# Metadata model
class EventMetadata(BaseModel):
    """Metadata about the event and its source"""

    hook_event_name: str = Field(description="Original hook event name from provider")
    transcript_path: str | None = Field(default=None, description="Path to conversation transcript")
    permission_mode: str | None = Field(default=None, description="Permission mode at event time")
    raw_event: dict[str, Any] | None = Field(
        default=None, description="Raw event data from provider"
    )


# Main normalized event model
class NormalizedEvent(BaseModel):
    """Normalized analytics event (provider-agnostic)

    This is the standard format after normalization, regardless of source provider.
    All analytics backends should work with this model.
    """

    event_type: EventType = Field(description="Type of analytics event")
    timestamp: datetime = Field(description="When the event occurred (ISO 8601)")
    session_id: str = Field(description="Session identifier")
    provider: str = Field(description="Source provider (claude, openai, etc.)")

    # Context varies by event type
    context: (
        ToolExecutionContext
        | UserPromptContext
        | SessionContext
        | NotificationContext
        | CompactContext
        | StopContext
        | dict[str, Any]
    ) = Field(description="Event-specific context data")

    # Metadata about the event
    metadata: EventMetadata = Field(description="Event metadata and provenance")

    # Optional fields
    cwd: str | None = Field(default=None, description="Current working directory")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_type": "tool_execution_started",
                    "timestamp": "2025-11-19T12:34:56.789Z",
                    "session_id": "abc123-def456",
                    "provider": "claude",
                    "context": {
                        "tool_name": "Write",
                        "tool_input": {"file_path": "src/main.py", "contents": "print('Hello')"},
                        "tool_use_id": "toolu_01ABC123",
                    },
                    "metadata": {
                        "hook_event_name": "PreToolUse",
                        "transcript_path": "/path/to/transcript.jsonl",
                        "permission_mode": "default",
                    },
                    "cwd": "/Users/dev/project",
                },
                {
                    "event_type": "session_started",
                    "timestamp": "2025-11-19T12:00:00.000Z",
                    "session_id": "abc123-def456",
                    "provider": "claude",
                    "context": {"source": "startup"},
                    "metadata": {
                        "hook_event_name": "SessionStart",
                        "transcript_path": "/path/to/transcript.jsonl",
                    },
                },
            ]
        }
    }


# Event type mapping (from hook events to analytics events)
HOOK_EVENT_TO_ANALYTICS_EVENT: dict[str, EventType] = {
    "SessionStart": "session_started",
    "SessionEnd": "session_completed",
    "UserPromptSubmit": "user_prompt_submitted",
    "PreToolUse": "tool_execution_started",
    "PostToolUse": "tool_execution_completed",
    "PermissionRequest": "permission_requested",
    "Stop": "agent_stopped",
    "SubagentStop": "subagent_stopped",
    "Notification": "system_notification",
    "PreCompact": "context_compacted",
}
