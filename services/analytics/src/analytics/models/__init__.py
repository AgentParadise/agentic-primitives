"""Analytics models package

This package contains all Pydantic models for the analytics system:
- hook_input: Provider-specific hook input models
- events: Normalized analytics event models
- config: Configuration models with environment variable support
"""

from analytics.models.config import AnalyticsConfig
from analytics.models.events import (
    HOOK_EVENT_TO_ANALYTICS_EVENT,
    CompactContext,
    EventMetadata,
    EventType,
    NormalizedEvent,
    NotificationContext,
    SessionContext,
    StopContext,
    ToolExecutionContext,
    UserPromptContext,
)
from analytics.models.hook_input import (
    ClaudeHookInput,
    ClaudeHookInputBase,
    ClaudeNotificationInput,
    ClaudePermissionRequestInput,
    ClaudePostToolUseInput,
    ClaudePreCompactInput,
    ClaudePreToolUseInput,
    ClaudeSessionEndInput,
    ClaudeSessionStartInput,
    ClaudeStopInput,
    ClaudeSubagentStopInput,
    ClaudeUserPromptSubmitInput,
    HookInput,
)

__all__ = [
    "HOOK_EVENT_TO_ANALYTICS_EVENT",
    # Configuration
    "AnalyticsConfig",
    "ClaudeHookInput",
    "ClaudeHookInputBase",
    "ClaudeNotificationInput",
    "ClaudePermissionRequestInput",
    "ClaudePostToolUseInput",
    "ClaudePreCompactInput",
    "ClaudePreToolUseInput",
    "ClaudeSessionEndInput",
    "ClaudeSessionStartInput",
    "ClaudeStopInput",
    "ClaudeSubagentStopInput",
    "ClaudeUserPromptSubmitInput",
    "CompactContext",
    "EventMetadata",
    "EventType",
    # Hook inputs
    "HookInput",
    # Events
    "NormalizedEvent",
    "NotificationContext",
    "SessionContext",
    "StopContext",
    "ToolExecutionContext",
    "UserPromptContext",
]
