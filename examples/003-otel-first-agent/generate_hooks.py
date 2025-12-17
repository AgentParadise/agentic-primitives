#!/usr/bin/env python3
"""Generate OTel-enabled security hooks for Claude CLI.

This script generates hook handlers that:
1. Validate tool usage with agentic_security
2. Emit OTel events for security decisions
3. Block dangerous commands

Usage:
    uv run python generate_hooks.py
    uv run python generate_hooks.py --output .claude/hooks
"""

from __future__ import annotations

import argparse
from pathlib import Path


def generate_hooks(output_dir: Path) -> None:
    """Generate hook handlers with OTel backend.

    Args:
        output_dir: Directory to write hooks to
    """
    from agentic_adapters.claude_cli import HookTemplate, generate_hooks as gen

    print(f"🔧 Generating hooks to: {output_dir}")

    # Configure hook template with OTel backend
    template = HookTemplate(
        observability_backend="otel",  # Use OTel instead of JSONL
        enable_security_validation=True,
        blocked_commands=[
            "rm -rf /",
            "curl | bash",
            "wget | sh",
        ],
        allowed_tools=[
            "Read",
            "Write",
            "Bash",
            "Glob",
            "Grep",
        ],
    )

    # Generate the hooks
    gen(
        output_dir=output_dir,
        template=template,
    )

    print("✅ Generated hooks:")
    for hook_file in sorted(output_dir.glob("handlers/*.py")):
        print(f"   - {hook_file.name}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate OTel-enabled security hooks",
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path(".claude/hooks"),
        help="Output directory for hooks (default: .claude/hooks)",
    )

    args = parser.parse_args()

    # Ensure output directory exists
    args.output.mkdir(parents=True, exist_ok=True)

    generate_hooks(args.output)


if __name__ == "__main__":
    main()
