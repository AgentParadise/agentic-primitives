"""Configuration types for workspace isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ResourceLimits:
    """Resource limits for isolated workspaces."""

    cpu: str = "2"  # Number of CPUs or CPU shares
    memory: str = "4G"  # Memory limit (e.g., "4G", "512M")
    disk: str | None = None  # Disk space limit
    network: bool = True  # Allow network access
    timeout_seconds: int = 3600  # Max execution time (1 hour default)

    def to_docker_args(self) -> dict[str, Any]:
        """Convert to Docker run arguments."""
        args: dict[str, Any] = {
            "cpu_count": int(self.cpu) if self.cpu.isdigit() else 2,
            "mem_limit": self.memory,
        }
        if not self.network:
            args["network_mode"] = "none"
        return args


@dataclass
class MountConfig:
    """Configuration for a volume mount."""

    host_path: str | Path
    container_path: str
    read_only: bool = False

    def to_docker_mount(self) -> dict[str, Any]:
        """Convert to Docker mount specification."""
        return {
            "type": "bind",
            "source": str(Path(self.host_path).resolve()),
            "target": self.container_path,
            "read_only": self.read_only,
        }


@dataclass
class WorkspaceConfig:
    """Configuration for creating an isolated workspace."""

    # Provider selection
    provider: str = "local"  # "local", "docker", "e2b"

    # Docker-specific
    image: str = "python:3.12-slim"
    dockerfile: str | Path | None = None

    # Working directory inside workspace
    working_dir: str = "/workspace"

    # Mounts
    mounts: list[MountConfig] = field(default_factory=list)

    # Secrets (injected as environment variables)
    secrets: dict[str, str] = field(default_factory=dict)

    # Environment variables (non-secret)
    environment: dict[str, str] = field(default_factory=dict)

    # Resource limits
    limits: ResourceLimits = field(default_factory=ResourceLimits)

    # Cleanup behavior
    auto_cleanup: bool = True  # Remove workspace on exit
    keep_on_error: bool = False  # Keep workspace if error occurs

    # Labels for identification
    labels: dict[str, str] = field(default_factory=dict)

    def with_mount(
        self,
        host_path: str | Path,
        container_path: str,
        read_only: bool = False,
    ) -> WorkspaceConfig:
        """Add a mount and return self for chaining."""
        self.mounts.append(MountConfig(host_path, container_path, read_only))
        return self

    def with_secret(self, name: str, value: str) -> WorkspaceConfig:
        """Add a secret and return self for chaining."""
        self.secrets[name] = value
        return self

    def with_env(self, name: str, value: str) -> WorkspaceConfig:
        """Add an environment variable and return self for chaining."""
        self.environment[name] = value
        return self
