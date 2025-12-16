"""Workspace providers for isolated execution.

Available providers:
- LocalProvider: Local filesystem (development/testing)
- DockerProvider: Docker containers (production)
- E2BProvider: E2B cloud sandboxes (future)
"""

from agentic_isolation.providers.base import (
    WorkspaceProvider,
    Workspace,
    ExecuteResult,
)
from agentic_isolation.providers.local import LocalProvider
from agentic_isolation.providers.docker import DockerProvider

__all__ = [
    "WorkspaceProvider",
    "Workspace",
    "ExecuteResult",
    "LocalProvider",
    "DockerProvider",
]
