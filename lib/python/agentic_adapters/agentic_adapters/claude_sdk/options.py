"""Generate ClaudeAgentOptions with security and observability hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from agentic_security import SecurityPolicy

# Type aliases for SDK hook functions
PreToolUseHook = Callable[[str, dict[str, Any]], dict[str, Any] | None]
PostToolUseHook = Callable[[str, dict[str, Any], Any, float | None], None]


@dataclass
class HookConfig:
    """Configuration for SDK hooks."""

    # Security
    security_policy: Any | None = None  # SecurityPolicy
    block_on_violation: bool = True

    # Observability
    observability_enabled: bool = True
    hook_client: Any | None = None  # HookClient from agentic_hooks

    # Custom hooks (user-provided)
    custom_pre_tool_use: list[PreToolUseHook] = field(default_factory=list)
    custom_post_tool_use: list[PostToolUseHook] = field(default_factory=list)

    # Logging
    log_tool_calls: bool = False


def create_security_hooks(
    policy: SecurityPolicy,
    *,
    block_on_violation: bool = True,
) -> tuple[PreToolUseHook, None]:
    """Create security hooks for Claude SDK.

    Args:
        policy: Security policy to enforce
        block_on_violation: Whether to block dangerous operations

    Returns:
        Tuple of (pre_tool_use_hook, None)
        Post hook is None as security only needs pre-validation
    """

    def pre_tool_use(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
        """Validate tool call before execution."""
        result = policy.validate(tool_name, tool_input)

        if not result.safe:
            if block_on_violation:
                # Return modified input that will cause tool to fail safely
                return {
                    "__blocked__": True,
                    "__reason__": result.reason,
                    "__original_input__": tool_input,
                }
            # Log but allow (for permissive mode)
            # Could emit warning event here

        return None  # Allow unchanged

    return pre_tool_use, None


def create_observability_hooks(
    hook_client: Any | None = None,
) -> tuple[PreToolUseHook, PostToolUseHook]:
    """Create observability hooks for Claude SDK.

    Note: These hooks are for CUSTOM/MCP tools only.
    Built-in tools (Bash, Write, Read) bypass Python hooks.
    Use message parsing for built-in tool observability.

    Args:
        hook_client: Optional HookClient for event emission

    Returns:
        Tuple of (pre_tool_use_hook, post_tool_use_hook)
    """
    import time

    # Track tool start times
    _tool_times: dict[str, float] = {}

    def pre_tool_use(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
        """Record tool start for custom tools."""
        tool_id = f"{tool_name}_{time.time_ns()}"
        _tool_times[tool_id] = time.time()

        if hook_client:
            try:
                # Emit tool_started event
                hook_client.emit_sync({
                    "type": "tool_started",
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "tool_id": tool_id,
                })
            except Exception:
                pass  # Non-blocking

        # Store tool_id in input for correlation
        return {**tool_input, "__tool_id__": tool_id}

    def post_tool_use(
        tool_name: str,
        tool_input: dict[str, Any],
        result: Any,
        duration_ms: float | None,
    ) -> None:
        """Record tool completion for custom tools."""
        tool_id = tool_input.get("__tool_id__", "unknown")
        start_time = _tool_times.pop(tool_id, None)

        if duration_ms is None and start_time:
            duration_ms = (time.time() - start_time) * 1000

        if hook_client:
            try:
                # Emit tool_completed event
                hook_client.emit_sync({
                    "type": "tool_completed",
                    "tool_name": tool_name,
                    "tool_id": tool_id,
                    "success": not isinstance(result, Exception),
                    "duration_ms": duration_ms,
                })
            except Exception:
                pass  # Non-blocking

    return pre_tool_use, post_tool_use


def create_agent_options(
    config: HookConfig | None = None,
    *,
    security_policy: Any | None = None,
    observability_enabled: bool = True,
    hook_client: Any | None = None,
    **extra_options: Any,
) -> dict[str, Any]:
    """Create ClaudeAgentOptions dictionary with configured hooks.

    This generates the options dict that can be passed to Claude Agent SDK.

    Args:
        config: Full hook configuration (or use individual params below)
        security_policy: Security policy to enforce
        observability_enabled: Whether to enable observability hooks
        hook_client: HookClient for event emission
        **extra_options: Additional options to include

    Returns:
        Dictionary suitable for ClaudeAgentOptions

    Example:
        options = create_agent_options(
            security_policy=SecurityPolicy.with_defaults(),
            model="claude-sonnet-4-20250514",
            max_turns=50,
        )
    """
    if config is None:
        config = HookConfig(
            security_policy=security_policy,
            observability_enabled=observability_enabled,
            hook_client=hook_client,
        )

    # Collect all hooks
    pre_hooks: list[PreToolUseHook] = []
    post_hooks: list[PostToolUseHook] = []

    # Add security hooks (must run first)
    if config.security_policy is not None:
        pre_hook, _ = create_security_hooks(
            config.security_policy,
            block_on_violation=config.block_on_violation,
        )
        pre_hooks.append(pre_hook)

    # Add observability hooks
    if config.observability_enabled:
        pre_obs, post_obs = create_observability_hooks(config.hook_client)
        pre_hooks.append(pre_obs)
        post_hooks.append(post_obs)

    # Add custom hooks
    pre_hooks.extend(config.custom_pre_tool_use)
    post_hooks.extend(config.custom_post_tool_use)

    # Create combined hooks
    def combined_pre_tool_use(
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Combined pre-tool-use hook."""
        current_input = tool_input
        for hook in pre_hooks:
            result = hook(tool_name, current_input)
            if result is not None:
                # Check if blocked
                if result.get("__blocked__"):
                    return result
                current_input = result
        return current_input if current_input != tool_input else None

    def combined_post_tool_use(
        tool_name: str,
        tool_input: dict[str, Any],
        result: Any,
        duration_ms: float | None,
    ) -> None:
        """Combined post-tool-use hook."""
        for hook in post_hooks:
            try:
                hook(tool_name, tool_input, result, duration_ms)
            except Exception:
                pass  # Non-blocking

    # Build options dict
    options: dict[str, Any] = {
        **extra_options,
    }

    # Only add hooks if we have any
    if pre_hooks:
        options["pre_tool_use"] = combined_pre_tool_use
    if post_hooks:
        options["post_tool_use"] = combined_post_tool_use

    return options
