"""Claude provider adapter for event normalization"""

from typing import Any

from pydantic import ValidationError
from pydantic_core import InitErrorDetails

from analytics.adapters.base import BaseProviderAdapter
from analytics.models.events import (
    CompactContext,
    EventMetadata,
    NotificationContext,
    SessionContext,
    StopContext,
    ToolExecutionContext,
    UserPromptContext,
)
from analytics.models.hook_input import HookInput


class ClaudeAdapter(BaseProviderAdapter):
    """Adapter for Claude provider hook events

    Handles Claude-specific field extraction and transformation.
    """

    def extract_session_id(self, hook_input: HookInput) -> str:
        """Extract session ID from Claude hook data

        Args:
            hook_input: Claude hook input

        Returns:
            str: Session ID
        """
        return str(hook_input.data["session_id"])

    def extract_context(self, hook_input: HookInput) -> dict[str, Any]:
        """Extract event context based on Claude hook event type

        Args:
            hook_input: Claude hook input

        Returns:
            dict: Event-specific context data

        Raises:
            ValidationError: If required fields are missing
        """
        event_name = hook_input.data.get("hook_event_name", hook_input.event)

        try:
            # Tool execution events (PreToolUse, PostToolUse, PermissionRequest)
            if event_name in ["PreToolUse", "PostToolUse", "PermissionRequest"]:
                return ToolExecutionContext(
                    tool_name=str(hook_input.data["tool_name"]),
                    tool_input=dict(hook_input.data["tool_input"]),
                    tool_response=hook_input.data.get("tool_response"),
                    tool_use_id=hook_input.data.get("tool_use_id"),
                ).model_dump()

            # Session events (SessionStart, SessionEnd)
            elif event_name == "SessionStart":
                return SessionContext(
                    source=hook_input.data.get("source"),
                    reason=None,
                ).model_dump()

            elif event_name == "SessionEnd":
                return SessionContext(
                    source=None,
                    reason=hook_input.data.get("reason"),
                ).model_dump()

            # User prompt events
            elif event_name == "UserPromptSubmit":
                prompt = str(hook_input.data["prompt"])
                return UserPromptContext(
                    prompt=prompt,
                    prompt_length=len(prompt),
                ).model_dump()

            # Notification events
            elif event_name == "Notification":
                return NotificationContext(
                    notification_type=str(hook_input.data["notification_type"]),
                    message=str(hook_input.data["message"]),
                ).model_dump()

            # Stop events (Stop, SubagentStop)
            elif event_name in ["Stop", "SubagentStop"]:
                return StopContext(
                    stop_hook_active=bool(hook_input.data.get("stop_hook_active", False)),
                ).model_dump()

            # Compaction events
            elif event_name == "PreCompact":
                return CompactContext(
                    trigger=str(hook_input.data["trigger"]),
                    custom_instructions=hook_input.data.get("custom_instructions"),
                ).model_dump()

            # Fallback for unknown events (provider-agnostic future-proofing)
            else:
                return dict(hook_input.data)

        except KeyError as e:
            error_details: InitErrorDetails = {
                "type": "missing",
                "loc": ("data", str(e.args[0])),
                "input": hook_input.data,
            }
            raise ValidationError.from_exception_data("value_error", [error_details]) from e

    def extract_metadata(self, hook_input: HookInput) -> dict[str, Any]:
        """Extract Claude-specific metadata

        Args:
            hook_input: Claude hook input

        Returns:
            dict: Event metadata
        """
        return EventMetadata(
            hook_event_name=str(hook_input.data.get("hook_event_name", hook_input.event)),
            transcript_path=hook_input.data.get("transcript_path"),
            permission_mode=hook_input.data.get("permission_mode"),
            raw_event=dict(hook_input.data),
        ).model_dump()
