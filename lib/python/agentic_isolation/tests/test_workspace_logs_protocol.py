"""`SupportsWorkspaceLogs` is an OPTIONAL capability, and the tests say why.

The motivating consumer is session capture: a workspace finalizer prints
whether the transcript reached the store, and that verdict lives only in the
container's own output. Without a way to read it back, the capture outcome is
unobservable to the orchestrator - it fails open and fails silent.

Two properties matter more than the happy path and are what these tests pin:

1. The capability is genuinely optional. Adding `logs` to `WorkspaceProvider`
   would force every backend to grow a method most can only raise from.
2. `logs` never raises. It is called during teardown, where the container may
   already be gone. A caller reading a capture verdict must not be able to
   fail the teardown that produced it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentic_isolation import SupportsWorkspaceLogs
from agentic_isolation.providers.docker import WorkspaceDockerProvider
from agentic_isolation.providers.local import WorkspaceLocalProvider


def _unconstructed(cls: type) -> Any:
    """Instantiate without __init__ - these tests probe shape, not behaviour."""
    return cls.__new__(cls)


class TestCapabilityIsOptional:
    def test_docker_advertises_the_capability(self) -> None:
        assert isinstance(_unconstructed(WorkspaceDockerProvider), SupportsWorkspaceLogs)

    def test_local_does_not(self) -> None:
        # Not a gap. A local workspace runs in the caller's own stdio, so there
        # is no separate stream to read back. If this ever flips to True it
        # should be because `logs` was implemented, never because the protocol
        # was widened until everything trivially satisfied it.
        assert not isinstance(_unconstructed(WorkspaceLocalProvider), SupportsWorkspaceLogs)


class TestLogsNeverRaises:
    """Every failure path must yield "" rather than propagate."""

    def test_missing_container_returns_empty(self) -> None:
        provider = _unconstructed(WorkspaceDockerProvider)

        class _Workspace:
            _handle = "definitely-not-a-real-container-6f1a2b3c"

        result = asyncio.run(provider.logs(_Workspace(), tail=5))  # type: ignore[arg-type]
        assert result == ""

    def test_absent_docker_binary_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider = _unconstructed(WorkspaceDockerProvider)

        async def _boom(*_a: object, **_k: object) -> None:
            raise OSError("docker not installed")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _boom)

        class _Workspace:
            _handle = "any"

        assert asyncio.run(provider.logs(_Workspace(), tail=5)) == ""  # type: ignore[arg-type]
