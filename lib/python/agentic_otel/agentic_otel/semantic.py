"""Semantic conventions for agent telemetry.

Based on OpenTelemetry GenAI semantic conventions with extensions
for AI agent operations, tool execution, and security decisions.
"""


class AgentSemanticConventions:
    """Attribute names for agent telemetry.

    These follow OpenTelemetry naming conventions:
    - Namespaced with dots (e.g., "agent.session.id")
    - Lowercase with underscores for multi-word names
    - Specific to general ordering
    """

    # =========================================================================
    # Session Attributes (from Claude CLI, don't override)
    # =========================================================================
    AGENT_SESSION_ID = "agent.session.id"

    # =========================================================================
    # Tool Execution Attributes (from hooks)
    # =========================================================================
    TOOL_NAME = "tool.name"
    TOOL_USE_ID = "tool.use_id"
    TOOL_INPUT = "tool.input"  # JSON string, may be truncated
    TOOL_OUTPUT_PREVIEW = "tool.output.preview"  # First N chars of output
    TOOL_SUCCESS = "tool.success"  # Boolean
    TOOL_DURATION_MS = "tool.duration_ms"
    TOOL_ERROR = "tool.error"  # Error message if failed

    # =========================================================================
    # Security Decision Attributes (from hooks)
    # =========================================================================
    HOOK_TYPE = "hook.type"  # pre_tool_use, post_tool_use, etc.
    HOOK_DECISION = "hook.decision"  # allow, block, warn
    HOOK_REASON = "hook.reason"  # Why blocked/warned
    HOOK_VALIDATORS = "hook.validators_run"  # List of validators that ran

    # =========================================================================
    # Token Metrics (from CLI, for reference)
    # =========================================================================
    TOKEN_TYPE = "token.type"  # input, output, cache_read, cache_creation
    TOKEN_COUNT = "token.count"
    TOKEN_MODEL = "token.model"

    # =========================================================================
    # Cost Attributes
    # =========================================================================
    COST_USD = "cost.usd"
    COST_CURRENCY = "cost.currency"

    # =========================================================================
    # Event Names (for OTel Events/Logs)
    # =========================================================================
    EVENT_SECURITY_DECISION = "security.decision"
    EVENT_TOOL_STARTED = "tool.started"
    EVENT_TOOL_COMPLETED = "tool.completed"
    EVENT_TOOL_BLOCKED = "tool.blocked"
