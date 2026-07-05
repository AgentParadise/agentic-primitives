"""Tests for the typed InteractiveSession port (Phase 1 of ADR/issue #225).

Covers:
  * AwaitResult is now a structural Protocol (not a duplicate dataclass);
    a driver-shaped dataclass satisfies isinstance() against it, so the
    two definitions can never drift.
  * InteractiveSession protocol -- structural isinstance() checks against
    a stub object, without needing the interactive-tmux driver.
  * BaseProvider.interactive_session() default returns None.
  * InteractiveTmuxProvider.interactive_session() returns workspace._handle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.base import (
    AwaitResult,
    BaseProvider,
    ExecuteResult,
    InteractiveSession,
    Workspace,
)


@dataclass
class _DriverShapedAwaitResult:
    """Field-for-field copy of the interactive-tmux driver's own
    `AwaitResult` dataclass -- used to prove the real driver result
    satisfies the base `AwaitResult` Protocol structurally, without
    importing the driver."""

    ready: bool
    timed_out: bool
    reason: str
    duration_ms: float
    stable_polls_observed: int
    pane: str = ""
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.ready

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "timed_out": self.timed_out,
            "reason": self.reason,
            "duration_ms": self.duration_ms,
            "stable_polls_observed": self.stable_polls_observed,
            "pane": self.pane,
            "error": self.error,
        }


class TestAwaitResultProtocol:
    def test_driver_shaped_result_satisfies_protocol(self) -> None:
        """A driver-shaped dataclass satisfies the base `AwaitResult`
        Protocol structurally -- so the isinstance() check that used to
        always be False (two drifting dataclasses) now holds."""
        result = _DriverShapedAwaitResult(
            ready=True,
            timed_out=False,
            reason="ready",
            duration_ms=123.4,
            stable_polls_observed=4,
        )
        assert isinstance(result, AwaitResult)

    def test_read_surface_is_accessible(self) -> None:
        result = _DriverShapedAwaitResult(
            ready=False,
            timed_out=True,
            reason="timeout_never_ready",
            duration_ms=60000.0,
            stable_polls_observed=0,
            pane="last frame",
            error="boom",
        )
        # Every member the port promises is readable off the concrete result.
        assert result.ready is False
        assert result.timed_out is True
        assert result.reason == "timeout_never_ready"
        assert result.duration_ms == 60000.0
        assert result.stable_polls_observed == 0
        assert result.pane == "last frame"
        assert result.error == "boom"
        assert result.success is False

    def test_plain_object_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(object(), AwaitResult)


class _StubInteractiveSession:
    """Minimal object with the right method shapes but no relation to the
    driver -- exercises the protocol structurally."""

    def send_message(self, agent: str, text: str) -> None:
        return None

    def await_completion(
        self,
        agent: str,
        *,
        timeout: float = 60.0,
        stable_polls: int = 4,
        poll_interval: float = 0.5,
    ) -> AwaitResult:
        return _DriverShapedAwaitResult(
            ready=True,
            timed_out=False,
            reason="ready",
            duration_ms=0.0,
            stable_polls_observed=stable_polls,
        )

    def capture_response(self, agent: str) -> str:
        return ""


class TestInteractiveSessionProtocol:
    def test_stub_satisfies_protocol_structurally(self) -> None:
        stub = _StubInteractiveSession()
        assert isinstance(stub, InteractiveSession)

    def test_object_missing_methods_does_not_satisfy_protocol(self) -> None:
        class NotASession:
            def send_message(self, agent: str, text: str) -> None:
                return None

        assert not isinstance(NotASession(), InteractiveSession)

    def test_plain_object_does_not_satisfy_protocol(self) -> None:
        assert not isinstance(object(), InteractiveSession)


class _MinimalProvider(BaseProvider):
    """Smallest possible BaseProvider subclass, to exercise the default
    `interactive_session()` implementation without touching docker/local
    providers."""

    @property
    def name(self) -> str:
        return "minimal"

    async def create(self, config: WorkspaceConfig) -> Workspace:  # pragma: no cover
        raise NotImplementedError

    async def destroy(self, workspace: Workspace) -> None:  # pragma: no cover
        raise NotImplementedError

    async def execute(
        self,
        workspace: Workspace,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:  # pragma: no cover
        raise NotImplementedError

    async def write_file(
        self, workspace: Workspace, path: str, content: str | bytes
    ) -> None:  # pragma: no cover
        raise NotImplementedError

    async def read_file(self, workspace: Workspace, path: str) -> str:  # pragma: no cover
        raise NotImplementedError

    async def file_exists(self, workspace: Workspace, path: str) -> bool:  # pragma: no cover
        raise NotImplementedError


class TestBaseProviderDefault:
    def test_interactive_session_defaults_to_none(self) -> None:
        provider = _MinimalProvider()
        config = WorkspaceConfig()
        workspace = Workspace(
            id="ws-1",
            provider="minimal",
            path=Path("/workspace"),
            config=config,
        )
        assert provider.interactive_session(workspace) is None


class TestInteractiveTmuxProviderOverride:
    def test_interactive_session_returns_handle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without importing the real driver, verify the adapter's
        `interactive_session()` returns `workspace._handle` when present."""
        from agentic_isolation.providers import interactive_tmux as adapter_module

        # Avoid constructing via __init__ (which loads the driver); use
        # object.__new__ since interactive_session() only reads
        # workspace._handle and doesn't touch provider state.
        provider = object.__new__(adapter_module.InteractiveTmuxProvider)

        stub_handle = _StubInteractiveSession()
        config = WorkspaceConfig()
        workspace = Workspace(
            id="ws-1",
            provider="interactive-tmux",
            path=Path("/workspace"),
            config=config,
            _handle=stub_handle,
        )

        session = provider.interactive_session(workspace)
        assert session is stub_handle
        assert isinstance(session, InteractiveSession)

    def test_interactive_session_none_when_no_handle(self) -> None:
        from agentic_isolation.providers import interactive_tmux as adapter_module

        provider = object.__new__(adapter_module.InteractiveTmuxProvider)
        config = WorkspaceConfig()
        workspace = Workspace(
            id="ws-1",
            provider="interactive-tmux",
            path=Path("/workspace"),
            config=config,
            _handle=None,
        )

        assert provider.interactive_session(workspace) is None
