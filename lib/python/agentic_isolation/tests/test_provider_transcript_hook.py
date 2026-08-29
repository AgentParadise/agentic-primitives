"""Tests for the provider `transcript_source()` optional-capability hook.

See issue #792. Covers: `BaseProvider` default returns `None`; the docker
provider returns a real `TranscriptSource` for registered harnesses and
`None` for an unknown agent name (no raise); the harness contract types
and bundled plugins are importable/registered from the `agentic_isolation`
package root without any extra import.
"""

from __future__ import annotations

from pathlib import Path

from agentic_isolation.config import WorkspaceConfig
from agentic_isolation.providers.base import Workspace
from agentic_isolation.providers.docker import WorkspaceDockerProvider
from agentic_isolation.providers.local import WorkspaceLocalProvider


def _make_workspace(provider_name: str) -> Workspace:
    return Workspace(
        id="ws-test",
        provider=provider_name,
        path=Path("/workspace"),
        config=WorkspaceConfig(),
        _handle="fake-container",
    )


class TestBaseProviderDefault:
    async def test_default_transcript_source_is_none(self) -> None:
        provider = WorkspaceLocalProvider()
        workspace = _make_workspace(provider.name)
        assert provider.transcript_source(workspace, "claude") is None


class TestDockerProviderTranscriptSource:
    def test_returns_source_for_claude(self) -> None:
        provider = WorkspaceDockerProvider()
        workspace = _make_workspace(provider.name)
        source = provider.transcript_source(workspace, "claude")
        assert source is not None
        assert source.agent == "claude"

    def test_returns_source_for_codex(self) -> None:
        provider = WorkspaceDockerProvider()
        workspace = _make_workspace(provider.name)
        source = provider.transcript_source(workspace, "codex")
        assert source is not None
        assert source.agent == "codex"

    def test_returns_none_for_unknown_agent(self) -> None:
        provider = WorkspaceDockerProvider()
        workspace = _make_workspace(provider.name)
        assert provider.transcript_source(workspace, "not-a-real-harness") is None


class TestPackageRootExports:
    def test_harness_types_importable_from_package_root(self) -> None:
        from agentic_isolation import (
            AgentName,
            HarnessPlugin,
            TranscriptSource,
        )

        assert AgentName.CLAUDE == "claude"
        assert HarnessPlugin is not None
        assert TranscriptSource is not None

    def test_get_harness_resolves_bundled_harnesses_on_bare_import(self) -> None:
        import agentic_isolation
        from agentic_isolation import get_harness

        assert agentic_isolation is not None
        assert get_harness("claude") is not None
        assert get_harness("codex") is not None
