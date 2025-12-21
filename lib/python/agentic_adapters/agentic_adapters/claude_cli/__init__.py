"""Claude CLI Adapter - Run Claude CLI and generate hooks.

This adapter provides:
- ClaudeCLIRunner: Execute Claude CLI and capture events
- generate_hooks: Generate .claude/hooks/ Python files

Usage:
    from agentic_adapters.claude_cli import ClaudeCLIRunner, generate_hooks

    # Run CLI and capture events
    runner = ClaudeCLIRunner(cwd="/workspace")
    result = await runner.run("Create a file")
    for event in result.events:
        print(event["event_type"])

    # Generate hooks for a workspace
    generate_hooks(
        output_dir=".claude/hooks",
        observability_backend="events",
    )
"""

from agentic_adapters.claude_cli.generator import (
    HookTemplate,
    generate_hooks,
    generate_post_tool_use_hook,
    generate_pre_tool_use_hook,
)
from agentic_adapters.claude_cli.runner import CLIResult, ClaudeCLIRunner

__all__ = [
    # Runner
    "ClaudeCLIRunner",
    "CLIResult",
    # Hook generation
    "generate_hooks",
    "generate_pre_tool_use_hook",
    "generate_post_tool_use_hook",
    "HookTemplate",
]
