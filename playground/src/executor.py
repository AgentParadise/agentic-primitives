"""Agent Executor - Run Claude CLI in isolated workspaces.

This module provides the core execution logic for running agents
in isolated containers with event capture.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from agentic_isolation import AgenticWorkspace, ResourceLimits

from .config import ScenarioConfig


@dataclass
class ExecutionResult:
    """Result of agent execution."""

    # Identification
    session_id: str
    scenario_name: str

    # Execution status
    success: bool
    exit_code: int

    # Output
    stdout: str
    stderr: str

    # Timing
    started_at: datetime
    completed_at: datetime
    duration_seconds: float

    # Workspace info
    workspace_path: str
    provider: str

    # Files created (if any)
    created_files: list[str] = field(default_factory=list)

    # Events captured from stdout (JSONL)
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "scenario_name": self.scenario_name,
            "success": self.success,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:1000] if self.stdout else "",
            "stderr": self.stderr[:500] if self.stderr else "",
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "workspace_path": self.workspace_path,
            "provider": self.provider,
            "created_files": self.created_files,
            "events_count": len(self.events),
        }


class AgentExecutor:
    """Execute Claude CLI agents in isolated workspaces.

    This executor wraps the AgenticWorkspace to provide a simple
    interface for running agents with event capture.

    Example:
        >>> config = ScenarioConfig.default()
        >>> executor = AgentExecutor(config)
        >>> result = await executor.run("Create a hello world script")
        >>> for event in result.events:
        ...     print(event["event_type"])
    """

    def __init__(
        self,
        config: ScenarioConfig,
        on_output: Callable[[str], None] | None = None,
        otel_endpoint: str | None = None,
    ):
        """Initialize executor.

        Args:
            config: Scenario configuration
            on_output: Optional callback for streaming output
            otel_endpoint: Optional OTel collector endpoint for event export
        """
        self.config = config
        self.on_output = on_output
        self.otel_endpoint = otel_endpoint
        self._session_id = str(uuid.uuid4())

    @property
    def session_id(self) -> str:
        """Get current session ID."""
        return self._session_id

    def _get_environment(self) -> dict[str, str]:
        """Get environment variables for the workspace."""
        return {
            "CLAUDE_SESSION_ID": self._session_id,
            "AGENTIC_SCENARIO": self.config.name,
        }

    def _build_cli_command(self, task: str) -> str:
        """Build the Claude CLI command.

        Args:
            task: The task prompt

        Returns:
            Full command string
        """
        # Start with base command
        cmd_parts = ["claude", "-p"]

        # Add headless args
        cmd_parts.extend(self.config.headless.to_cli_args())

        # Add task (escaped for shell)
        escaped_task = task.replace('"', '\\"')
        cmd_parts.append(f'"{escaped_task}"')

        return " ".join(cmd_parts)

    def _parse_events(self, stdout: str) -> list[dict[str, Any]]:
        """Parse JSONL events from stdout.

        Args:
            stdout: Raw stdout from the agent

        Returns:
            List of parsed event dicts
        """
        import json

        events = []
        for line in stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict) and "event_type" in data:
                    events.append(data)
            except json.JSONDecodeError:
                pass  # Not all stdout lines are JSON events
        return events

    async def run(
        self,
        task: str,
        context_files: list[Path] | None = None,
        verbose: bool = False,
    ) -> ExecutionResult:
        """Run agent with the given task.

        Args:
            task: The task to give the agent
            context_files: Optional files to copy into workspace
            verbose: Enable verbose output

        Returns:
            ExecutionResult with output and status
        """
        started_at = datetime.now()
        iso_config = self.config.isolation

        # Resource limits
        limits = ResourceLimits(
            memory_mb=iso_config.memory_mb,
            cpu_cores=iso_config.cpu_cores,
            timeout_seconds=iso_config.timeout,
        )

        if verbose and self.on_output:
            self.on_output(f"🚀 Starting agent (session: {self._session_id[:8]}...)")
            self.on_output(f"📋 Scenario: {self.config.name}")
            self.on_output(f"🐳 Provider: {iso_config.provider}")

        async with AgenticWorkspace.create(
            provider=iso_config.provider,
            image=iso_config.image if iso_config.provider == "docker" else None,
            environment=self._get_environment(),
            limits=limits,
        ) as workspace:
            if verbose and self.on_output:
                self.on_output(f"✅ Workspace ready: {workspace.path}")

            # Write task file
            await workspace.write_file(
                "TASK.md",
                f"# Task\n\n{task}\n",
            )

            # Copy context files if provided
            if context_files:
                for file_path in context_files:
                    if file_path.exists():
                        content = file_path.read_text()
                        await workspace.write_file(file_path.name, content)
                        if verbose and self.on_output:
                            self.on_output(f"📄 Copied: {file_path.name}")

            # Build and run command
            command = self._build_cli_command(
                "Read TASK.md and complete the task described there"
            )

            if verbose and self.on_output:
                self.on_output(f"🤖 Running: {command[:80]}...")

            result = await workspace.execute(
                command,
                timeout=iso_config.timeout,
            )

            # Parse events from stdout
            events = self._parse_events(result.stdout)

            # List created files
            ls_result = await workspace.execute("ls -la")
            created_files = []
            if ls_result.exit_code == 0:
                for line in ls_result.stdout.strip().split("\n")[1:]:  # Skip total line
                    parts = line.split()
                    if len(parts) >= 9:
                        filename = parts[-1]
                        if filename not in [".", "..", "TASK.md"]:
                            created_files.append(filename)

            completed_at = datetime.now()

            return ExecutionResult(
                session_id=self._session_id,
                scenario_name=self.config.name,
                success=result.exit_code == 0,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=(completed_at - started_at).total_seconds(),
                workspace_path=str(workspace.path),
                provider=iso_config.provider,
                created_files=created_files,
                events=events,
            )


async def run_agent(
    task: str,
    scenario: ScenarioConfig | None = None,
    verbose: bool = False,
    on_output: Callable[[str], None] | None = None,
) -> ExecutionResult:
    """Convenience function to run an agent.

    Args:
        task: The task to give the agent
        scenario: Scenario configuration (default if None)
        verbose: Enable verbose output
        on_output: Optional callback for streaming output

    Returns:
        ExecutionResult
    """
    if scenario is None:
        scenario = ScenarioConfig.default()

    executor = AgentExecutor(
        config=scenario,
        on_output=on_output,
    )

    return await executor.run(task, verbose=verbose)
