"""agentic-adapters: Runtime adapters for AI agent integrations.

Provides adapters for different AI agent runtimes:
- claude_sdk: Generate ClaudeAgentOptions with hooks
- claude_cli: Generate .claude/hooks/ Python files

Quick Start (SDK):
    from agentic_adapters.claude_sdk import create_agent_options
    from agentic_security import SecurityPolicy

    options = create_agent_options(
        security_policy=SecurityPolicy.with_defaults(),
        model="claude-sonnet-4-20250514",
    )

Quick Start (CLI):
    from agentic_adapters.claude_cli import generate_hooks

    generate_hooks(
        output_dir=".claude/hooks",
        security_enabled=True,
        observability_backend="jsonl",
    )
"""

from agentic_adapters.claude_sdk import (
    create_agent_options,
    create_security_hooks,
    create_observability_hooks,
    HookConfig,
)
from agentic_adapters.claude_cli import (
    generate_hooks,
    generate_pre_tool_use_hook,
    generate_post_tool_use_hook,
    HookTemplate,
)

__all__ = [
    # SDK adapter
    "create_agent_options",
    "create_security_hooks",
    "create_observability_hooks",
    "HookConfig",
    # CLI adapter
    "generate_hooks",
    "generate_pre_tool_use_hook",
    "generate_post_tool_use_hook",
    "HookTemplate",
]

__version__ = "0.1.0"
