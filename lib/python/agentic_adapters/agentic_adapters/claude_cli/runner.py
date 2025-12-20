"""Claude CLI Runner - Execute Claude CLI and capture events.

This module provides a high-level interface for running Claude CLI
and capturing JSONL events from stdout.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CLIResult:
    """Result from Claude CLI execution."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ClaudeCLIRunner:
    """Run Claude CLI and capture events.

    This runner executes the Claude CLI command and captures JSONL events
    from stdout. Events are parsed and returned with the result.

    Example:
        >>> from agentic_adapters.claude_cli import ClaudeCLIRunner
        >>>
        >>> runner = ClaudeCLIRunner(cwd="/workspace")
        >>> result = await runner.run("Create a hello world file")
        >>> for event in result.events:
        ...     print(event["event_type"])
    """

    cwd: str = "/workspace"
    permission_mode: str = "bypassPermissions"
    claude_command: str = "claude"
    extra_env: dict[str, str] = field(default_factory=dict)
    allowed_tools: list[str] | None = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.permission_mode not in ("default", "plan", "bypassPermissions"):
            raise ValueError(
                f"Invalid permission_mode: {self.permission_mode}. "
                "Must be 'default', 'plan', or 'bypassPermissions'"
            )

    def get_env(self) -> dict[str, str]:
        """Get environment variables for CLI execution.

        Returns:
            Dict of environment variables
        """
        env = os.environ.copy()

        # Add extra env vars
        env.update(self.extra_env)

        return env

    def get_command(self, prompt: str) -> list[str]:
        """Build the CLI command.

        Args:
            prompt: The prompt to send to Claude

        Returns:
            List of command arguments
        """
        cmd = [
            self.claude_command,
            "-p",  # Prompt mode (non-interactive)
            prompt,
            "--output-format",
            "json",  # JSON output for structured data
        ]

        # Add permission mode if not default
        if self.permission_mode == "bypassPermissions":
            cmd.append("--dangerously-skip-permissions")

        # Add allowed tools
        if self.allowed_tools is not None:
            cmd.extend(["--allowedTools", ",".join(self.allowed_tools)])

        return cmd

    async def run(
        self,
        prompt: str,
        timeout: int = 3600,
    ) -> CLIResult:
        """Run Claude CLI with the given prompt.

        Args:
            prompt: The prompt to send to Claude
            timeout: Maximum execution time in seconds

        Returns:
            CLIResult with exit code, output, and parsed events

        Raises:
            asyncio.TimeoutError: If execution exceeds timeout
            FileNotFoundError: If claude command not found
        """
        import json
        import time

        # Validate claude is available
        if not self._find_claude():
            raise FileNotFoundError(
                f"Claude CLI not found. Ensure '{self.claude_command}' is in PATH."
            )

        cmd = self.get_command(prompt)
        env = self.get_env()

        start_time = time.monotonic()
        events: list[dict[str, Any]] = []
        stdout_lines: list[str] = []
        process = None

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
                env=env,
            )

            # Read stdout and parse events
            async def read_stdout():
                assert process.stdout is not None
                async for line in process.stdout:
                    line_str = line.decode().strip()
                    if line_str:
                        stdout_lines.append(line_str)
                        # Try to parse as JSON event
                        try:
                            data = json.loads(line_str)
                            if isinstance(data, dict) and "event_type" in data:
                                events.append(data)
                        except json.JSONDecodeError:
                            pass  # Not all stdout lines are JSON events

            async def read_stderr():
                assert process.stderr is not None
                stderr_data = await process.stderr.read()
                return stderr_data.decode() if stderr_data else ""

            # Run both readers with timeout
            stderr_task = asyncio.create_task(read_stderr())
            stdout_task = asyncio.create_task(read_stdout())

            await asyncio.wait_for(
                asyncio.gather(stdout_task, process.wait()),
                timeout=timeout,
            )

            stderr = await stderr_task
            duration = time.monotonic() - start_time

            return CLIResult(
                success=process.returncode == 0,
                exit_code=process.returncode or 0,
                stdout="\n".join(stdout_lines),
                stderr=stderr,
                duration_seconds=duration,
                events=events,
            )

        except asyncio.TimeoutError:
            # Try to kill the process
            if process:
                process.kill()
                await process.wait()
            raise

    def _find_claude(self) -> bool:
        """Check if claude command is available."""
        return shutil.which(self.claude_command) is not None

    async def run_with_hooks(
        self,
        prompt: str,
        hooks_dir: str | Path | None = None,
        timeout: int = 3600,
    ) -> CLIResult:
        """Run Claude CLI with custom hooks directory.

        Args:
            prompt: The prompt to send to Claude
            hooks_dir: Directory containing hook scripts
            timeout: Maximum execution time in seconds

        Returns:
            CLIResult with exit code and output
        """
        if hooks_dir:
            hooks_path = Path(hooks_dir).resolve()
            if not hooks_path.exists():
                raise FileNotFoundError(f"Hooks directory not found: {hooks_path}")

            # Set hooks directory via env var
            self.extra_env["CLAUDE_HOOKS_DIR"] = str(hooks_path)

        return await self.run(prompt, timeout)
