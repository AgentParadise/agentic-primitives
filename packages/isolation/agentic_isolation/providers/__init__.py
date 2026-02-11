"""Workspace providers for isolated execution.

Available providers:
- WorkspaceLocalProvider: Local filesystem (development/testing)
- WorkspaceDockerProvider: Docker containers (production)
- WorkspaceE2BProvider: E2B cloud sandboxes (future)
"""

from agentic_isolation.providers.base import (
    ExecuteResult,
    Workspace,
    WorkspaceProvider,
)
from agentic_isolation.providers.docker import WorkspaceDockerProvider
from agentic_isolation.providers.local import WorkspaceLocalProvider

__all__ = [
    # Base types
    "WorkspaceProvider",
    "Workspace",
    "ExecuteResult",
    # Providers
    "WorkspaceLocalProvider",
    "WorkspaceDockerProvider",
]
