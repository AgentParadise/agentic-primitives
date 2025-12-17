#!/usr/bin/env python3
"""OTel-First Agent Example.

Demonstrates running Claude CLI with OTel observability.

Usage:
    uv run python main.py "Your task here"
    uv run python main.py --help
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def run_agent(task: str, verbose: bool = False) -> int:
    """Run an agent with OTel observability.

    Args:
        task: The task to give the agent
        verbose: Enable verbose output

    Returns:
        Exit code (0 = success)
    """
    from agentic_otel import OTelConfig
    from agentic_adapters.claude_cli import ClaudeCLIRunner

    # Create OTel configuration
    # This reads from environment or uses defaults
    config = OTelConfig(
        endpoint="http://localhost:4317",
        service_name="otel-first-example",
        resource_attributes={
            "example.name": "003-otel-first-agent",
            "example.version": "1.0.0",
        },
    )

    if verbose:
        print(f"OTel Endpoint: {config.endpoint}")
        print(f"Service Name: {config.service_name}")
        print(f"Resource Attributes: {config.resource_attributes}")
        print()

    # Create the runner with OTel config
    runner = ClaudeCLIRunner(
        otel_config=config,
        working_directory=Path.cwd(),
    )

    print(f"🚀 Running task: {task}")
    print("-" * 50)

    # Run the agent
    result = await runner.run(task)

    print("-" * 50)
    print(f"✅ Exit code: {result.exit_code}")

    if result.stdout:
        print(f"\n📝 Output:\n{result.stdout[:500]}...")

    if result.stderr and verbose:
        print(f"\n⚠️ Stderr:\n{result.stderr[:200]}...")

    return result.exit_code


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run Claude CLI agent with OTel observability",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s "Create a hello world script"
    %(prog)s "List files in current directory" --verbose
    %(prog)s "Explain this codebase" -v
        """,
    )

    parser.add_argument(
        "task",
        help="The task to give the agent",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    exit_code = asyncio.run(run_agent(args.task, args.verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
