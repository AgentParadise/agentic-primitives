"""Pydantic models for hook input events from providers (Claude, OpenAI, etc.)

These models validate the JSON data received via stdin when a hook is triggered.
They are provider-specific and follow the exact schema from each provider's hook system.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


# Common base model for all Claude hook events
class ClaudeHookInputBase(BaseModel):
    """Base model for all Claude Code hook events with common fields"""

    session_id: str = Field(description="Unique identifier for the current session")
    transcript_path: str = Field(description="Path to the conversation JSONL file")
    cwd: str = Field(description="Current working directory when hook is invoked")
    permission_mode: Literal["default", "plan", "acceptEdits", "bypassPermissions"] = Field(
        description="Current permission mode"
    )
    hook_event_name: str = Field(description="Name of the hook event (e.g., PreToolUse)")


# PreToolUse event
class ClaudePreToolUseInput(ClaudeHookInputBase):
    """Hook input for PreToolUse event - before tool execution"""

    hook_event_name: Literal["PreToolUse"] = "PreToolUse"
    tool_name: str = Field(description="Name of the tool being executed")
    tool_input: dict[str, Any] = Field(description="Input parameters for the tool")
    tool_use_id: str = Field(description="Unique identifier for this tool use")


# PostToolUse event
class ClaudePostToolUseInput(ClaudeHookInputBase):
    """Hook input for PostToolUse event - after tool execution"""

    hook_event_name: Literal["PostToolUse"] = "PostToolUse"
    tool_name: str = Field(description="Name of the tool that was executed")
    tool_input: dict[str, Any] = Field(description="Input parameters for the tool")
    tool_response: dict[str, Any] = Field(description="Response from the tool execution")
    tool_use_id: str = Field(description="Unique identifier for this tool use")


# PermissionRequest event
class ClaudePermissionRequestInput(ClaudeHookInputBase):
    """Hook input for PermissionRequest event - when user is shown permission dialog"""

    hook_event_name: Literal["PermissionRequest"] = "PermissionRequest"
    tool_name: str = Field(description="Name of the tool requiring permission")
    tool_input: dict[str, Any] = Field(description="Input parameters for the tool")
    tool_use_id: str = Field(description="Unique identifier for this tool use")


# Notification event
class ClaudeNotificationInput(ClaudeHookInputBase):
    """Hook input for Notification event - when Claude sends notifications"""

    hook_event_name: Literal["Notification"] = "Notification"
    message: str = Field(description="Notification message content")
    notification_type: str = Field(
        description="Type of notification (e.g., permission_prompt, idle_prompt)"
    )


# UserPromptSubmit event
class ClaudeUserPromptSubmitInput(ClaudeHookInputBase):
    """Hook input for UserPromptSubmit event - when user submits a prompt"""

    hook_event_name: Literal["UserPromptSubmit"] = "UserPromptSubmit"
    prompt: str = Field(description="The prompt text submitted by the user")


# Stop event
class ClaudeStopInput(ClaudeHookInputBase):
    """Hook input for Stop event - when main agent finishes responding"""

    hook_event_name: Literal["Stop"] = "Stop"
    stop_hook_active: bool = Field(description="True if already continuing due to a stop hook")


# SubagentStop event
class ClaudeSubagentStopInput(ClaudeHookInputBase):
    """Hook input for SubagentStop event - when subagent finishes responding"""

    hook_event_name: Literal["SubagentStop"] = "SubagentStop"
    stop_hook_active: bool = Field(description="True if already continuing due to a stop hook")


# PreCompact event
class ClaudePreCompactInput(ClaudeHookInputBase):
    """Hook input for PreCompact event - before context compaction"""

    hook_event_name: Literal["PreCompact"] = "PreCompact"
    trigger: Literal["manual", "auto"] = Field(
        description="Trigger type (manual from /compact, auto from full context)"
    )
    custom_instructions: str = Field(
        default="", description="Custom instructions from user (manual only)"
    )


# SessionStart event
class ClaudeSessionStartInput(ClaudeHookInputBase):
    """Hook input for SessionStart event - when session starts or resumes"""

    hook_event_name: Literal["SessionStart"] = "SessionStart"
    source: Literal["startup", "resume", "clear", "compact"] = Field(
        description="Source of session start"
    )


# SessionEnd event
class ClaudeSessionEndInput(ClaudeHookInputBase):
    """Hook input for SessionEnd event - when session ends"""

    hook_event_name: Literal["SessionEnd"] = "SessionEnd"
    reason: Literal["exit", "error", "compact", "clear", "other"] = Field(
        description="Reason for session ending"
    )


# Union type for all Claude hook events
ClaudeHookInput = (
    ClaudePreToolUseInput
    | ClaudePostToolUseInput
    | ClaudePermissionRequestInput
    | ClaudeNotificationInput
    | ClaudeUserPromptSubmitInput
    | ClaudeStopInput
    | ClaudeSubagentStopInput
    | ClaudePreCompactInput
    | ClaudeSessionStartInput
    | ClaudeSessionEndInput
)


# Generic hook input model (provider-agnostic wrapper)
class HookInput(BaseModel):
    """Generic hook input that can be from any provider

    This is the top-level model that middleware should validate against.
    It contains provider identification and the raw event data.
    """

    provider: str = Field(
        default="unknown",
        description=(
            "Provider name (e.g., claude, openai, cursor, gemini). Determined by hook caller."
        ),
    )
    event: str = Field(description="Event name from the provider's hook system")
    data: dict[str, Any] = Field(description="Provider-specific event data")

    def to_claude_input(self) -> ClaudeHookInput:
        """Convert generic input to Claude-specific input model

        Returns:
            ClaudeHookInput: Validated Claude hook input

        Raises:
            ValidationError: If data doesn't match Claude schema
        """
        # Add hook_event_name to data if not present
        if "hook_event_name" not in self.data:
            self.data["hook_event_name"] = self.event

        # Discriminate based on event type
        event_name = self.data.get("hook_event_name", self.event)

        if event_name == "PreToolUse":
            return ClaudePreToolUseInput.model_validate(self.data)
        elif event_name == "PostToolUse":
            return ClaudePostToolUseInput.model_validate(self.data)
        elif event_name == "PermissionRequest":
            return ClaudePermissionRequestInput.model_validate(self.data)
        elif event_name == "Notification":
            return ClaudeNotificationInput.model_validate(self.data)
        elif event_name == "UserPromptSubmit":
            return ClaudeUserPromptSubmitInput.model_validate(self.data)
        elif event_name == "Stop":
            return ClaudeStopInput.model_validate(self.data)
        elif event_name == "SubagentStop":
            return ClaudeSubagentStopInput.model_validate(self.data)
        elif event_name == "PreCompact":
            return ClaudePreCompactInput.model_validate(self.data)
        elif event_name == "SessionStart":
            return ClaudeSessionStartInput.model_validate(self.data)
        elif event_name == "SessionEnd":
            return ClaudeSessionEndInput.model_validate(self.data)
        else:
            raise ValueError(f"Unknown Claude hook event: {event_name}")
