"""OpenAI provider adapter for event normalization"""

from typing import Any

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


class OpenAIAdapter(BaseProviderAdapter):
    """Adapter for OpenAI provider hook events

    Handles OpenAI-specific field extraction and transformation.
    Note: OpenAI hook format may differ from Claude, this adapter provides
    sensible defaults and field mapping for provider-agnostic normalization.
    """

    def extract_session_id(self, hook_input: HookInput) -> str:
        """Extract session ID from OpenAI hook data

        OpenAI may use different field names. Try common variations.

        Args:
            hook_input: OpenAI hook input

        Returns:
            str: Session ID
        """
        # Try common field names for session ID
        return str(
            hook_input.data.get("session_id")
            or hook_input.data.get("sessionId")
            or hook_input.data.get("conversation_id")
            or hook_input.data.get("conversationId")
            or "unknown-session"
        )

    def extract_context(self, hook_input: HookInput) -> dict[str, Any]:
        """Extract event context based on OpenAI hook event type

        Args:
            hook_input: OpenAI hook input

        Returns:
            dict: Event-specific context data
        """
        event_name = hook_input.data.get("hook_event_name", hook_input.event)

        # Tool execution events
        if event_name in ["PreToolUse", "PostToolUse", "PermissionRequest"]:
            return ToolExecutionContext(
                tool_name=str(
                    hook_input.data.get("tool_name")
                    or hook_input.data.get("function_name")
                    or "unknown"
                ),
                tool_input=dict(
                    hook_input.data.get("tool_input") or hook_input.data.get("function_args") or {}
                ),
                tool_response=hook_input.data.get("tool_response")
                or hook_input.data.get("function_response"),
                tool_use_id=hook_input.data.get("tool_use_id") or hook_input.data.get("call_id"),
            ).model_dump()

        # Session events
        elif event_name == "SessionStart":
            return SessionContext(
                source=hook_input.data.get("source") or hook_input.data.get("trigger"),
                reason=None,
            ).model_dump()

        elif event_name == "SessionEnd":
            return SessionContext(
                source=None,
                reason=hook_input.data.get("reason") or hook_input.data.get("end_reason"),
            ).model_dump()

        # User prompt events
        elif event_name == "UserPromptSubmit":
            prompt = str(
                hook_input.data.get("prompt")
                or hook_input.data.get("message")
                or hook_input.data.get("user_message")
                or ""
            )
            return UserPromptContext(
                prompt=prompt,
                prompt_length=len(prompt),
            ).model_dump()

        # Notification events
        elif event_name == "Notification":
            return NotificationContext(
                notification_type=str(
                    hook_input.data.get("notification_type")
                    or hook_input.data.get("type")
                    or "unknown"
                ),
                message=str(hook_input.data.get("message") or hook_input.data.get("content") or ""),
            ).model_dump()

        # Stop events
        elif event_name in ["Stop", "SubagentStop"]:
            return StopContext(
                stop_hook_active=bool(
                    hook_input.data.get("stop_hook_active")
                    or hook_input.data.get("hook_active", False)
                ),
            ).model_dump()

        # Compaction events
        elif event_name == "PreCompact":
            return CompactContext(
                trigger=str(
                    hook_input.data.get("trigger")
                    or hook_input.data.get("compact_trigger")
                    or "unknown"
                ),
                custom_instructions=hook_input.data.get("custom_instructions")
                or hook_input.data.get("instructions"),
            ).model_dump()

        # Fallback for unknown events
        else:
            return dict(hook_input.data)

    def extract_metadata(self, hook_input: HookInput) -> dict[str, Any]:
        """Extract OpenAI-specific metadata

        Args:
            hook_input: OpenAI hook input

        Returns:
            dict: Event metadata
        """
        return EventMetadata(
            hook_event_name=str(hook_input.data.get("hook_event_name", hook_input.event)),
            transcript_path=hook_input.data.get("transcript_path")
            or hook_input.data.get("log_path"),
            permission_mode=hook_input.data.get("permission_mode") or hook_input.data.get("mode"),
            raw_event=dict(hook_input.data),
        ).model_dump()
