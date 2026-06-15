"""Tests for InteractiveTmuxProvider's WorkspaceConfig handling.

The adapter cannot honor most WorkspaceConfig fields (the driver does its
own bind-mount layout and runs a fixed entrypoint), so it must reject
non-default unsupported fields loudly instead of silently dropping them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_isolation.config import (
    MountConfig,
    ResourceLimits,
    SecurityConfig,
    WorkspaceConfig,
)
from agentic_isolation.providers.interactive_tmux import (
    InteractiveTmuxProvider,
    _unsupported_config_fields,
)


def _provider() -> InteractiveTmuxProvider:
    # Explicit kwargs so construction never probes $HOME or ITMUX_* env.
    return InteractiveTmuxProvider(
        default_host_auth={"claude": Path("/tmp/nowhere/.claude")},
        default_host_claude_dotjson=Path("/tmp/nowhere/.claude.json"),
        default_claude_plugin_dirs=[],
    )


class TestUnsupportedConfigFields:
    def test_default_config_is_clean(self) -> None:
        assert _unsupported_config_fields(WorkspaceConfig()) == []

    def test_honored_fields_are_clean(self) -> None:
        config = WorkspaceConfig(
            provider="interactive-tmux",
            working_dir="/custom",
            labels={"agents": "claude", "team": "x"},
            auto_cleanup=False,
            keep_on_error=True,
        )
        assert _unsupported_config_fields(config) == []

    @pytest.mark.parametrize(
        ("kwargs", "expected"),
        [
            ({"image": "ubuntu:24.04"}, ["image"]),
            ({"dockerfile": "Dockerfile"}, ["dockerfile"]),
            ({"mounts": [MountConfig("/h", "/c")]}, ["mounts"]),
            ({"secrets": {"API_KEY": "x"}}, ["secrets"]),
            ({"environment": {"FOO": "bar"}}, ["environment"]),
            ({"security": SecurityConfig.development()}, ["security"]),
            ({"limits": ResourceLimits(cpu="8")}, ["limits"]),
            ({"plugins": ["/opt/plugin"]}, ["plugins"]),
        ],
    )
    def test_each_unsupported_field_detected(self, kwargs: dict, expected: list[str]) -> None:
        config = WorkspaceConfig(**kwargs)
        assert _unsupported_config_fields(config) == expected

    async def test_create_rejects_unsupported_config(self) -> None:
        """create() must fail loudly BEFORE touching docker."""
        provider = _provider()
        config = WorkspaceConfig(
            provider="interactive-tmux",
            secrets={"API_KEY": "x"},
            plugins=["/opt/plugin"],
        )
        with pytest.raises(ValueError, match="secrets, plugins"):
            await provider.create(config)
