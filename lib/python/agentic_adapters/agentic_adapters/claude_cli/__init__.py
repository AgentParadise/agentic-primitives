"""Claude CLI Adapter - Run Claude CLI and generate hooks.

This adapter provides:
- ClaudeCLIRunner: Execute Claude CLI with OTel configuration
- generate_hooks: Generate .claude/hooks/ Python files

Usage:
    from agentic_otel import OTelConfig
    from agentic_adapters.claude_cli import ClaudeCLIRunner, generate_hooks

    # Run CLI with OTel
    config = OTelConfig(endpoint="http://collector:4317")
    runner = ClaudeCLIRunner(otel_config=config)
    result = await runner.run("Create a file")

    # Generate hooks for a workspace
    generate_hooks(
        output_dir=".claude/hooks",
        observability_backend="otel",
    )
"""

from agentic_adapters.claude_cli.generator import (
    HookTemplate,
    generate_hooks,
    generate_post_tool_use_hook,
    generate_pre_tool_use_hook,
)
from agentic_adapters.claude_cli.runner import ClaudeCLIRunner, CLIResult

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
