"""Claude SDK Adapter - Generate ClaudeAgentOptions with hooks.

This adapter integrates agentic-primitives security and observability
with the Claude Agent SDK.

Usage:
    from agentic_adapters.claude_sdk import create_agent_options
    from agentic_security import SecurityPolicy

    options = create_agent_options(
        security_policy=SecurityPolicy.with_defaults(),
        observability_enabled=True,
    )

    # Use with Claude SDK
    agent = Agent(options=options)
"""

from agentic_adapters.claude_sdk.options import (
    create_agent_options,
    create_security_hooks,
    create_observability_hooks,
    HookConfig,
)

__all__ = [
    "create_agent_options",
    "create_security_hooks",
    "create_observability_hooks",
    "HookConfig",
]
