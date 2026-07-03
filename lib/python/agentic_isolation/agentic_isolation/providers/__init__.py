"""Workspace providers for isolated execution.

Available providers:
- WorkspaceLocalProvider: Local filesystem (development/testing)
- WorkspaceDockerProvider: Docker containers (production)
- InteractiveTmuxProvider: Docker containers running interactive claude/codex/
  gemini CLIs in tmux panes (productionized from EXP-01..EXP-04; adapter
  added per the EXP-05 codex cross-review M2 finding)
- WorkspaceE2BProvider: E2B cloud sandboxes (future)
"""

from typing import TYPE_CHECKING, Any

from agentic_isolation.providers.base import (
    AwaitResult,
    ExecuteResult,
    InteractiveSession,
    Workspace,
    WorkspaceProvider,
)
from agentic_isolation.providers.docker import WorkspaceDockerProvider
from agentic_isolation.providers.local import WorkspaceLocalProvider

if TYPE_CHECKING:
    from agentic_isolation.providers.interactive_tmux import InteractiveTmuxProvider


def __getattr__(name: str) -> Any:
    """Lazy export for providers with optional external dependencies.

    `InteractiveTmuxProvider` depends on the repo-root single-file driver
    (providers/workspaces/interactive-tmux/driver/interactive_tmux.py),
    which is NOT shipped inside the agentic-isolation wheel. Importing it
    eagerly would break `import agentic_isolation` for every installed
    consumer, so it is resolved on first attribute access instead.
    """
    if name == "InteractiveTmuxProvider":
        from agentic_isolation.providers.interactive_tmux import (
            InteractiveTmuxProvider,
        )

        return InteractiveTmuxProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Base types
    "WorkspaceProvider",
    "Workspace",
    "ExecuteResult",
    "InteractiveSession",
    "AwaitResult",
    # Providers
    "WorkspaceLocalProvider",
    "WorkspaceDockerProvider",
    "InteractiveTmuxProvider",
]
