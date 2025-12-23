"""Configuration types for workspace isolation."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SecurityConfig:
    """Security hardening configuration for isolated workspaces.

    Controls Linux security features applied at container runtime.
    These settings cannot be baked into a Docker image - they must
    be applied via `docker run` flags.

    Default values provide production-grade hardening:
    - All Linux capabilities dropped
    - Privilege escalation blocked
    - Read-only root filesystem
    - Writable tmpfs for /tmp and /home

    Usage:
        # Production (default - maximum security)
        config = SecurityConfig.production()

        # Development (relaxed for debugging)
        config = SecurityConfig.development()

        # Custom
        config = SecurityConfig(read_only_root=False)
    """

    # Capability dropping
    cap_drop_all: bool = True  # --cap-drop=ALL

    # Privilege escalation prevention
    no_new_privileges: bool = True  # --security-opt=no-new-privileges

    # Filesystem protection
    read_only_root: bool = True  # --read-only
    tmpfs_tmp: bool = True  # --tmpfs=/tmp:rw,noexec,nosuid,size=256m
    tmpfs_home: bool = True  # --tmpfs=/home/agent:rw,exec,nosuid,size=128m

    # Process limits
    pids_limit: int = 256  # --pids-limit=256

    # gVisor runtime (extra sandbox layer)
    use_gvisor: bool | None = None  # None = auto-detect, True/False = force

    @classmethod
    def production(cls) -> SecurityConfig:
        """Production-grade security configuration.

        All security features enabled. Use for untrusted workloads.
        """
        return cls()  # All defaults are production-safe

    @classmethod
    def development(cls) -> SecurityConfig:
        """Relaxed security for local development.

        Easier to debug but less secure. Never use in production.
        """
        return cls(
            read_only_root=False,
            use_gvisor=False,
        )

    @classmethod
    def detect_gvisor(cls) -> bool:
        """Detect if gVisor runtime is available."""
        if shutil.which("docker") is None:
            return False
        try:
            result = subprocess.run(
                ["docker", "info", "--format", "{{json .Runtimes}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return "runsc" in result.stdout or "gvisor" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    def to_docker_run_args(self) -> list[str]:
        """Convert to docker run command line arguments."""
        args: list[str] = []

        if self.cap_drop_all:
            args.append("--cap-drop=ALL")

        if self.no_new_privileges:
            args.append("--security-opt=no-new-privileges")

        if self.read_only_root:
            args.append("--read-only")

        if self.tmpfs_tmp:
            args.append("--tmpfs=/tmp:rw,noexec,nosuid,size=256m")

        if self.tmpfs_home:
            args.append("--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000")

        if self.pids_limit > 0:
            args.append(f"--pids-limit={self.pids_limit}")

        # gVisor runtime
        use_gvisor = self.use_gvisor
        if use_gvisor is None:
            use_gvisor = self.detect_gvisor()
        if use_gvisor:
            args.append("--runtime=runsc")

        return args


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

    # Security hardening (Docker provider only)
    security: SecurityConfig = field(default_factory=SecurityConfig)

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
