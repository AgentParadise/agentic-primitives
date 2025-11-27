"""Models for analytics events.

Provides the HookDecision dataclass for recording hook decisions.
"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class HookDecision:
    """Record of a hook decision for the audit trail.

    Every hook logs a HookDecision after making its allow/block/warn decision.
    This creates a complete audit trail of all hook activity.

    Attributes:
        hook_id: Unique identifier for the hook (e.g., "bash-validator")
        event_type: The hook event type (e.g., "PreToolUse", "SessionStart")
        decision: The hook's decision ("allow", "block", or "warn")
        session_id: Session identifier from the agent
        tool_use_id: Unique identifier for the tool call (for correlation with agent events)
        provider: Agent provider name (default: "claude")
        tool_name: Name of the tool being used (if applicable)
        reason: Human-readable reason for the decision (especially for blocks)
        metadata: Additional context (tool input, file path, etc.)

    Example:
        decision = HookDecision(
            hook_id="bash-validator",
            event_type="PreToolUse",
            decision="block",
            session_id="sess-abc123",
            tool_use_id="toolu_01ABC123",
            tool_name="Bash",
            reason="Dangerous command: rm -rf /",
            metadata={"command": "rm -rf /", "blocked_pattern": "rm -rf /"},
        )
    """

    hook_id: str
    event_type: str
    decision: Literal["allow", "block", "warn"]
    session_id: str
    tool_use_id: str | None = None  # Correlation key for linking to agent tool_call events
    provider: str = "claude"
    tool_name: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "hook_id": self.hook_id,
            "event_type": self.event_type,
            "decision": self.decision,
            "session_id": self.session_id,
            "provider": self.provider,
            "tool_name": self.tool_name,
            "reason": self.reason,
            "metadata": self.metadata,
        }
        # Only include tool_use_id if present (backward compatible)
        if self.tool_use_id:
            result["tool_use_id"] = self.tool_use_id
        return result
