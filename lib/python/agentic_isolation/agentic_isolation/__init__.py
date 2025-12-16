"""agentic-isolation: Workspace isolation for AI agent execution.

Provides secure, isolated execution environments for AI agents
using pluggable providers (Local, Docker, E2B, etc.).

Quick Start:
    from agentic_isolation import IsolatedWorkspace

    async with IsolatedWorkspace.create(
        provider="local",  # or "docker"
        secrets={"API_KEY": "secret"},
    ) as workspace:
        result = await workspace.execute("echo hello")
        print(result.stdout)

With Docker:
    async with IsolatedWorkspace.create(
        provider="docker",
        image="python:3.12-slim",
        mounts=[("/host/code", "/workspace/code", True)],
    ) as workspace:
        await workspace.write_file("test.py", "print('hi')")
        result = await workspace.execute("python test.py")

Features:
    - Multiple providers: Local, Docker, E2B (future)
    - Secure secret injection
    - Resource limits (CPU, memory, timeout)
    - Volume mounts
    - Automatic cleanup
"""

from agentic_isolation.workspace import IsolatedWorkspace, register_provider
from agentic_isolation.config import (
    WorkspaceConfig,
    ResourceLimits,
    MountConfig,
)
from agentic_isolation.providers import (
    WorkspaceProvider,
    Workspace,
    ExecuteResult,
    LocalProvider,
    DockerProvider,
)

__all__ = [
    # Main API
    "IsolatedWorkspace",
    "register_provider",
    # Configuration
    "WorkspaceConfig",
    "ResourceLimits",
    "MountConfig",
    # Providers
    "WorkspaceProvider",
    "Workspace",
    "ExecuteResult",
    "LocalProvider",
    "DockerProvider",
]

__version__ = "0.1.0"
