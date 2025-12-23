"""agentic-isolation: Workspace isolation for AI agent execution.

Provides secure, isolated execution environments for AI agents
using pluggable providers (Local, Docker, E2B, etc.).

Quick Start:
    from agentic_isolation import AgenticWorkspace

    async with AgenticWorkspace.create(
        provider="local",  # or "docker"
        secrets={"API_KEY": "secret"},
    ) as workspace:
        result = await workspace.execute("echo hello")
        print(result.stdout)

With Docker (production):
    from agentic_isolation import AgenticWorkspace, SecurityConfig

    async with AgenticWorkspace.create(
        provider="docker",
        image="agentic-workspace-claude-cli:latest",
        security=SecurityConfig.production(),
    ) as workspace:
        # Stream output in real-time
        async for line in workspace.stream(["claude", "-p", "Hello"]):
            print(line)

Features:
    - Multiple providers: Local, Docker, E2B (future)
    - Security hardening (cap-drop, read-only root, gVisor)
    - Real-time stdout streaming
    - Secure secret injection
    - Resource limits (CPU, memory, timeout)
    - Volume mounts
    - Automatic cleanup
"""

from agentic_isolation.config import (
    MountConfig,
    ResourceLimits,
    SecurityConfig,
    WorkspaceConfig,
)
from agentic_isolation.providers import (
    ExecuteResult,
    Workspace,
    WorkspaceDockerProvider,
    WorkspaceLocalProvider,
    WorkspaceProvider,
)

# Claude CLI specific components
from agentic_isolation.providers.claude_cli import (
    EventParser,
    ObservabilityEvent,
    SessionOutputStream,
    SessionSummary,
    TokenUsage,
)
from agentic_isolation.workspace import AgenticWorkspace, register_provider

__all__ = [
    # Main API
    "AgenticWorkspace",
    "register_provider",
    # Configuration
    "WorkspaceConfig",
    "ResourceLimits",
    "MountConfig",
    "SecurityConfig",
    # Providers
    "WorkspaceProvider",
    "Workspace",
    "ExecuteResult",
    "WorkspaceLocalProvider",
    "WorkspaceDockerProvider",
    # Claude CLI (session output)
    "SessionOutputStream",
    "EventParser",
    "ObservabilityEvent",
    "SessionSummary",
    "TokenUsage",
]

__version__ = "0.2.0"
