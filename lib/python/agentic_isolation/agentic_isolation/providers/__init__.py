"""Workspace providers for isolated execution.

Available providers:
- WorkspaceLocalProvider: Local filesystem (development/testing)
- WorkspaceDockerProvider: Docker containers (production)
- WorkspaceE2BProvider: E2B cloud sandboxes (future)

Backward compatibility aliases are provided:
- LocalProvider -> WorkspaceLocalProvider
- DockerProvider -> WorkspaceDockerProvider
"""

from agentic_isolation.providers.base import (
    WorkspaceProvider,
    Workspace,
    ExecuteResult,
)
from agentic_isolation.providers.local import (
    WorkspaceLocalProvider,
    LocalProvider,  # Backward compat
)
from agentic_isolation.providers.docker import (
    WorkspaceDockerProvider,
    DockerProvider,  # Backward compat
)

__all__ = [
    # Base types
    "WorkspaceProvider",
    "Workspace",
    "ExecuteResult",
    # New explicit names (preferred)
    "WorkspaceLocalProvider",
    "WorkspaceDockerProvider",
    # Backward compatibility
    "LocalProvider",
    "DockerProvider",
]
