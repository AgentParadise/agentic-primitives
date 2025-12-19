"""Scenario configuration loading and validation.

This module provides configuration dataclasses for playground scenarios
and YAML loading utilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


@dataclass
class HeadlessConfig:
    """Claude CLI headless mode configuration.

    Maps to Claude CLI's headless options:
    https://docs.anthropic.com/en/docs/claude-code/headless
    """

    # Tool control
    allowed_tools: list[str] = field(
        default_factory=lambda: ["Bash", "Read", "Write", "Glob", "Grep"]
    )
    disallowed_tools: list[str] = field(default_factory=list)

    # Output format
    output_format: Literal["text", "json", "stream-json"] = "stream-json"

    # Behavior
    system_prompt: str | None = None
    permission_mode: Literal["default", "plan", "bypassPermissions"] = "bypassPermissions"
    max_turns: int | None = None

    # MCP configuration (optional)
    mcp_servers: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_cli_args(self) -> list[str]:
        """Convert to Claude CLI command line arguments.

        Returns:
            List of CLI arguments
        """
        args: list[str] = []

        # Tool control
        if self.allowed_tools:
            args.extend(["--allowedTools", ",".join(self.allowed_tools)])
        if self.disallowed_tools:
            args.extend(["--disallowedTools", ",".join(self.disallowed_tools)])

        # Output format
        if self.output_format == "json":
            args.append("--output-format=json")
        elif self.output_format == "stream-json":
            args.append("--output-format=stream-json")

        # Permission mode
        if self.permission_mode == "bypassPermissions":
            args.append("--dangerously-skip-permissions")

        # Max turns
        if self.max_turns is not None:
            args.extend(["--max-turns", str(self.max_turns)])

        return args


@dataclass
class IsolationConfig:
    """Isolation configuration for agent execution."""

    # Provider
    provider: Literal["docker", "local"] = "docker"

    # Docker-specific
    image: str = "agentic-workspace:latest"

    # Resource limits
    timeout: int = 300  # seconds
    memory_mb: int = 2048
    cpu_cores: float = 2.0

    # Working directory inside container
    working_dir: str = "/workspace"


@dataclass
class ScenarioConfig:
    """Complete scenario configuration.

    Combines headless and isolation configs into a single scenario
    that can be loaded from YAML.
    """

    name: str
    description: str = ""
    headless: HeadlessConfig = field(default_factory=HeadlessConfig)
    isolation: IsolationConfig = field(default_factory=IsolationConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> ScenarioConfig:
        """Load scenario from YAML file.

        Args:
            path: Path to YAML file

        Returns:
            ScenarioConfig instance

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If YAML is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {path}")

        with path.open() as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid scenario file: {path}")

        # Parse nested configs
        headless_data = data.get("headless", {})
        isolation_data = data.get("isolation", {})

        # Default values for headless config
        default_tools = ["Bash", "Read", "Write", "Glob", "Grep"]
        # Use environment variable or fallback to agentic-primitives default
        import os
        default_image = os.environ.get(
            "PLAYGROUND_WORKSPACE_IMAGE",
            "agentic-workspace:latest"
        )

        headless = HeadlessConfig(
            allowed_tools=headless_data.get("allowed_tools", default_tools),
            disallowed_tools=headless_data.get("disallowed_tools", []),
            output_format=headless_data.get("output_format", "stream-json"),
            system_prompt=headless_data.get("system_prompt"),
            permission_mode=headless_data.get("permission_mode", "bypassPermissions"),
            max_turns=headless_data.get("max_turns"),
            mcp_servers=headless_data.get("mcp_servers", {}),
        )

        isolation = IsolationConfig(
            provider=isolation_data.get("provider", "docker"),
            image=isolation_data.get("image", default_image),
            timeout=isolation_data.get("timeout", 300),
            memory_mb=isolation_data.get("memory_mb", 2048),
            cpu_cores=isolation_data.get("cpu_cores", 2.0),
            working_dir=isolation_data.get("working_dir", "/workspace"),
        )

        return cls(
            name=data.get("name", path.stem),
            description=data.get("description", ""),
            headless=headless,
            isolation=isolation,
        )

    @classmethod
    def default(cls) -> ScenarioConfig:
        """Create default scenario configuration.

        Returns:
            Default ScenarioConfig
        """
        return cls(
            name="default",
            description="Default scenario with standard tools",
        )


def load_scenario(name: str, scenarios_dir: Path | None = None) -> ScenarioConfig:
    """Load a scenario by name.

    Args:
        name: Scenario name (without .yaml extension)
        scenarios_dir: Directory containing scenarios (default: ./scenarios)

    Returns:
        ScenarioConfig instance

    Raises:
        FileNotFoundError: If scenario doesn't exist
    """
    if scenarios_dir is None:
        scenarios_dir = Path(__file__).parent.parent / "scenarios"

    path = scenarios_dir / f"{name}.yaml"
    return ScenarioConfig.from_yaml(path)


def list_scenarios(scenarios_dir: Path | None = None) -> list[str]:
    """List available scenario names.

    Args:
        scenarios_dir: Directory containing scenarios (default: ./scenarios)

    Returns:
        List of scenario names (without .yaml extension)
    """
    if scenarios_dir is None:
        scenarios_dir = Path(__file__).parent.parent / "scenarios"

    if not scenarios_dir.exists():
        return []

    return [p.stem for p in scenarios_dir.glob("*.yaml")]
