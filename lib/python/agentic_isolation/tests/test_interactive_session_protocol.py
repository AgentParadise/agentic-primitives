"""Tests for the typed InteractiveSession port (Phase 1 of ADR/issue #225).

Covers:
  * AwaitResult dataclass (fields mirror the driver's dataclass, success
    property, to_dict()).
  * InteractiveSession protocol -- structural isinstance() checks against
    a stub object, without needing the interactive-tmux driver.
  * BaseProvider.interactive_session() default returns None.
  * InteractiveTmuxProvider.interactive_session() returns workspace._handle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.base import (
    AwaitResult,
    BaseProvider,
    ExecuteResult,
    InteractiveSession,
    Workspace,
)


class TestAwaitResult:
    def test_success_true_when_ready(self) -> None:
        result = AwaitResult(
            ready=True,
            timed_out=False,
            reason="ready",
            duration_ms=123.4,
            stable_polls_observed=4,
        )
        assert result.success is True

    def test_success_false_when_not_ready(self) -> None:
        result = AwaitResult(
            ready=False,
            timed_out=True,
            reason="timeout_never_ready",
            duration_ms=60000.0,
            stable_polls_observed=0,
        )
        assert result.success is False

    def test_defaults(self) -> None:
        result = AwaitResult(
            ready=True,
            timed_out=False,
            reason="ready",
            duration_ms=1.0,
            stable_polls_observed=4,
        )
        assert result.pane == ""
        assert result.error is None

    def test_to_dict(self) -> None:
        result = AwaitResult(
            ready=False,
            timed_out=False,
            reason="error",
            duration_ms=5.0,
            stable_polls_observed=1,
            pane="some pane text",
            error="boom",
        )
        data = result.to_dict()
        assert data == {
            "ready": False,
            "timed_out": False,
            "reason": "error",
            "duration_ms": 5.0,
            "stable_polls_observed": 1,
            "pane": "some pane text",
            "error": "boom",
        }


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
        return AwaitResult(
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
