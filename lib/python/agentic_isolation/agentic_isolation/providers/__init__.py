"""Workspace providers for isolated execution.

Available providers:
- WorkspaceLocalProvider: Local filesystem (development/testing)
- WorkspaceDockerProvider: Docker containers (production)
- InteractiveTmuxProvider: Docker containers running interactive claude/codex/
  gemini CLIs in tmux panes (productionized from EXP-01..EXP-04; adapter
  added per the EXP-05 codex cross-review M2 finding)
- WorkspaceE2BProvider: E2B cloud sandboxes (future)
"""

from agentic_isolation.providers.base import (
    ExecuteResult,
    Workspace,
    WorkspaceProvider,
)
from agentic_isolation.providers.docker import WorkspaceDockerProvider
from agentic_isolation.providers.interactive_tmux import InteractiveTmuxProvider
from agentic_isolation.providers.local import WorkspaceLocalProvider

__all__ = [
    # Base types
    "WorkspaceProvider",
    "Workspace",
    "ExecuteResult",
    # Providers
    "WorkspaceLocalProvider",
    "WorkspaceDockerProvider",
    "InteractiveTmuxProvider",
]
