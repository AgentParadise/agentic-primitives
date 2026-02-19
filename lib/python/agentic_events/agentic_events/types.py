"""Event types for AI agent observability.

This module defines the standard event types emitted by agent hooks.
Based on the analytics-event-reference.md specification.
"""

from enum import StrEnum


class EventType(StrEnum):
    """Standard event types for agent observability.

    These event types cover the full lifecycle of an AI agent session,
    from startup to completion, including tool executions and security decisions.
    """

    # Session lifecycle
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"

    # Tool execution
    TOOL_EXECUTION_STARTED = "tool_execution_started"
    TOOL_EXECUTION_COMPLETED = "tool_execution_completed"

    # Security decisions
    SECURITY_DECISION = "security_decision"

    # Agent control
    AGENT_STOPPED = "agent_stopped"
    SUBAGENT_STOPPED = "subagent_stopped"

    # System events
    CONTEXT_COMPACTED = "context_compacted"
    SYSTEM_NOTIFICATION = "system_notification"

    # Subagent lifecycle
    SUBAGENT_STARTED = "subagent_started"

    # Tool failure
    TOOL_EXECUTION_FAILED = "tool_execution_failed"

    # Teammate events
    TEAMMATE_IDLE = "teammate_idle"

    # Task events
    TASK_COMPLETED = "task_completed"

    # User interaction
    USER_PROMPT_SUBMITTED = "user_prompt_submitted"
    PERMISSION_REQUESTED = "permission_requested"

    # Git operations (detected via PreToolUse/PostToolUse on Bash git commands)
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    GIT_BRANCH_CHANGED = "git_branch_changed"
    GIT_OPERATION = "git_operation"


class SecurityDecision(StrEnum):
    """Security decision outcomes."""

    ALLOW = "allow"
    BLOCK = "block"
    WARN = "warn"


class SessionSource(StrEnum):
    """How a session was started."""

    STARTUP = "startup"
    RESUME = "resume"
    CLEAR = "clear"
    COMPACT = "compact"
