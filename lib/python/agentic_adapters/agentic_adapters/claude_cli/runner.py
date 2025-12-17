"""Claude CLI Runner - Execute Claude CLI with OTel configuration.

This module provides a high-level interface for running Claude CLI
with proper OTel telemetry configuration.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agentic_otel import OTelConfig


@dataclass
class CLIResult:
    """Result from Claude CLI execution."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


@dataclass
class ClaudeCLIRunner:
    """Run Claude CLI with OTel configuration.

    This runner executes the Claude CLI command with proper environment
    variables for OTel telemetry. The CLI's native OTel support will
    automatically emit metrics for token usage, costs, etc.

    Example:
        >>> from agentic_otel import OTelConfig
        >>> from agentic_adapters.claude_cli import ClaudeCLIRunner
        >>>
        >>> config = OTelConfig(
        ...     endpoint="http://collector:4317",
        ...     resource_attributes={"aef.execution_id": "exec-123"}
        ... )
        >>> runner = ClaudeCLIRunner(otel_config=config)
        >>> result = await runner.run("Create a hello world file")
    """

    otel_config: OTelConfig
    cwd: str = "/workspace"
    permission_mode: str = "bypassPermissions"
    claude_command: str = "claude"
    extra_env: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.permission_mode not in ("default", "plan", "bypassPermissions"):
            raise ValueError(
                f"Invalid permission_mode: {self.permission_mode}. "
                "Must be 'default', 'plan', or 'bypassPermissions'"
            )

    def get_env(self) -> dict[str, str]:
        """Get environment variables for CLI execution.

        Combines:
        - Current environment
        - OTel configuration
        - Extra env vars

        Returns:
            Dict of environment variables
        """
        env = os.environ.copy()

        # Add OTel config
        env.update(self.otel_config.to_env())

        # Add extra env vars (can override OTel)
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
            "--print",  # Non-interactive mode
        ]

        # Add permission mode if not default
        if self.permission_mode != "default":
            if self.permission_mode == "bypassPermissions":
                cmd.append("--dangerously-skip-permissions")
            elif self.permission_mode == "plan":
                cmd.extend(["--allowedTools", ""])  # Plan mode - no tools

        # Add prompt
        cmd.append(prompt)

        return cmd

    async def run(
        self,
        prompt: str,
        timeout: int = 3600,
        capture_output: bool = True,
    ) -> CLIResult:
        """Run Claude CLI with the given prompt.

        Args:
            prompt: The prompt to send to Claude
            timeout: Maximum execution time in seconds
            capture_output: Whether to capture stdout/stderr

        Returns:
            CLIResult with exit code and output

        Raises:
            asyncio.TimeoutError: If execution exceeds timeout
            FileNotFoundError: If claude command not found
        """
        import time

        # Validate claude is available
        if not self._find_claude():
            raise FileNotFoundError(
                f"Claude CLI not found. Ensure '{self.claude_command}' is in PATH."
            )

        cmd = self.get_command(prompt)
        env = self.get_env()

        start_time = time.monotonic()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
                cwd=self.cwd,
                env=env,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            duration = time.monotonic() - start_time

            return CLIResult(
                success=process.returncode == 0,
                exit_code=process.returncode or 0,
                stdout=stdout_bytes.decode() if stdout_bytes else "",
                stderr=stderr_bytes.decode() if stderr_bytes else "",
                duration_seconds=duration,
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
