#!/usr/bin/env python3
"""Run Claude CLI Agent in an Isolated Docker Container.

This demonstrates the full isolation + OTel pattern:
1. Create an isolated Docker workspace
2. Inject OTel configuration for telemetry
3. Run Claude CLI inside the container
4. Collect results and cleanup

Usage:
    # Run with Docker isolation
    uv run python run_isolated.py "Create a hello world script"

    # Run with local isolation (no Docker)
    uv run python run_isolated.py "List files" --local

    # Verbose mode
    uv run python run_isolated.py "Explain this code" -v
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def run_isolated_agent(
    task: str,
    provider: str = "docker",
    verbose: bool = False,
) -> int:
    """Run Claude CLI in an isolated container with OTel.

    Args:
        task: The task to give the agent
        provider: Isolation provider ("docker" or "local")
        verbose: Enable verbose output

    Returns:
        Exit code (0 = success)
    """
    from agentic_isolation import IsolatedWorkspace, ResourceLimits
    from agentic_otel import OTelConfig

    # Create OTel configuration for container injection
    otel_config = OTelConfig(
        endpoint="http://host.docker.internal:4317",  # Docker → host
        service_name="isolated-agent-example",
        resource_attributes={
            "example.name": "003-otel-first-agent",
            "isolation.provider": provider,
        },
    )

    # Resource limits for the container
    limits = ResourceLimits(
        memory_mb=2048,
        cpu_cores=2.0,
        timeout_seconds=300,
    )

    if verbose:
        print(f"🐳 Provider: {provider}")
        print(f"🔭 OTel Endpoint: {otel_config.endpoint}")
        print(f"📊 Resource Limits: {limits}")
        print()

    print(f"🚀 Starting isolated workspace...")

    # Create isolated workspace with OTel env vars injected
    async with IsolatedWorkspace.create(
        provider=provider,
        image="ghcr.io/anthropics/claude-code:latest" if provider == "docker" else None,
        environment=otel_config.to_env(),  # Inject OTel config!
        resource_limits=limits,
        mounts=[
            # Mount current directory as read-only context
            (str(Path.cwd()), "/workspace/context", True),
        ] if provider == "docker" else None,
    ) as workspace:
        print(f"✅ Workspace ready: {workspace.path}")

        # Write the task to a file for Claude to read
        await workspace.write_file(
            "TASK.md",
            f"# Task\n\n{task}\n",
        )

        if verbose:
            print(f"📝 Wrote task to {workspace.path}/TASK.md")

        # Run Claude CLI inside the container
        print(f"\n🤖 Running Claude CLI with task: {task[:50]}...")
        print("-" * 50)

        result = await workspace.execute(
            f'claude --print "Read TASK.md and complete the task described there"',
            timeout=limits.timeout_seconds,
        )

        print("-" * 50)
        print(f"\n✅ Exit code: {result.exit_code}")

        if result.stdout:
            output = result.stdout[:1000]
            print(f"\n📝 Output:\n{output}")
            if len(result.stdout) > 1000:
                print("... [truncated]")

        if result.stderr and verbose:
            print(f"\n⚠️ Stderr:\n{result.stderr[:500]}")

        # List any files created
        ls_result = await workspace.execute("ls -la")
        if ls_result.exit_code == 0:
            print(f"\n📁 Workspace files:\n{ls_result.stdout}")

        return result.exit_code


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run Claude CLI agent in an isolated container",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run in Docker container (default)
    %(prog)s "Create a Python script that prints hello world"

    # Run locally (no container)
    %(prog)s "List current directory" --local

    # Verbose mode
    %(prog)s "Explain this codebase" -v
        """,
    )

    parser.add_argument(
        "task",
        help="The task to give the agent",
    )

    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local provider instead of Docker",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    provider = "local" if args.local else "docker"

    exit_code = asyncio.run(
        run_isolated_agent(args.task, provider, args.verbose)
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
