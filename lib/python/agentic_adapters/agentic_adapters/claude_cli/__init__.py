"""Claude CLI Adapter - Generate .claude/hooks/ Python files.

This adapter generates hook files for the Claude CLI that integrate
agentic-primitives security and observability.

Usage:
    from agentic_adapters.claude_cli import generate_hooks
    from agentic_security import SecurityPolicy

    generate_hooks(
        output_dir=".claude/hooks",
        security_policy=SecurityPolicy.with_defaults(),
        observability_backend="jsonl",
    )
"""

from agentic_adapters.claude_cli.generator import (
    generate_hooks,
    generate_pre_tool_use_hook,
    generate_post_tool_use_hook,
    HookTemplate,
)

__all__ = [
    "generate_hooks",
    "generate_pre_tool_use_hook",
    "generate_post_tool_use_hook",
    "HookTemplate",
]
