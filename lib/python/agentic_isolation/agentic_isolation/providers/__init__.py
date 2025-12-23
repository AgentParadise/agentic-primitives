"""Workspace providers for isolated execution.

Available providers:
- WorkspaceLocalProvider: Local filesystem (development/testing)
- WorkspaceDockerProvider: Docker containers (production)
- WorkspaceE2BProvider: E2B cloud sandboxes (future)
"""

from agentic_isolation.providers.base import (
    WorkspaceProvider,
    Workspace,
    ExecuteResult,
)
from agentic_isolation.providers.local import WorkspaceLocalProvider
from agentic_isolation.providers.docker import WorkspaceDockerProvider

__all__ = [
    # Base types
    "WorkspaceProvider",
    "Workspace",
    "ExecuteResult",
    # Providers
    "WorkspaceLocalProvider",
    "WorkspaceDockerProvider",
]
