"""Unit tests for ITMUX_*_HOME / ITMUX_CLAUDE_JSON env-var overrides.

Covers the docker-out-of-docker (DooD) bug surfaced by Syntropic137's
integration e2e on PR #202: when the driver runs inside another container,
`$HOME` does not point at the operator's credentials, so `start_workspace`
failed with `no enabled agents (host_auth empty)`. The env-var overrides
let the calling environment point at the real mounted credentials.

Tests exercise the override path WITHOUT spawning a real container — they
verify the credential discovery and adapter wiring, not the docker layer.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest


# The driver lives at providers/workspaces/interactive-tmux/driver/
# interactive_tmux.py — not a packaged module yet. Locate and import it
# the same way the InteractiveTmuxProvider adapter does (walking up from
# this test file, since the test sits inside the isolation package tree).
def _load_driver_module():
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = (
            ancestor
            / "providers"
            / "workspaces"
            / "interactive-tmux"
            / "driver"
            / "interactive_tmux.py"
        )
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("interactive_tmux", candidate)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules.setdefault("interactive_tmux", module)
            spec.loader.exec_module(module)
            return module
    pytest.skip("interactive_tmux driver not found in repo layout")


driver = _load_driver_module()


@pytest.fixture
def clean_env() -> Iterator[None]:
    """Drop ITMUX_* env vars for the duration of the test."""
    keys = [
        "ITMUX_CLAUDE_HOME",
        "ITMUX_CODEX_HOME",
        "ITMUX_GEMINI_HOME",
        "ITMUX_CLAUDE_JSON",
    ]
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestDefaultHostAuthFromEnv:
    """`_default_host_auth_from_env` resolves ITMUX_{AGENT}_HOME first."""

    def test_env_var_points_at_existing_dir_is_used(
        self,
        clean_env: None,
        tmp_path: Path,
    ) -> None:
        fake_claude = tmp_path / "vendored-claude"
        fake_claude.mkdir()
        os.environ["ITMUX_CLAUDE_HOME"] = str(fake_claude)

        result = driver._default_host_auth_from_env()

        assert result["claude"] == fake_claude

    def test_env_var_pointing_at_missing_dir_yields_none(
        self,
        clean_env: None,
        tmp_path: Path,
    ) -> None:
        os.environ["ITMUX_CLAUDE_HOME"] = str(tmp_path / "does-not-exist")

        result = driver._default_host_auth_from_env()

        # Override SET but path missing → None (caller opted in, we honor
        # the empty result rather than falling back to $HOME).
        assert result["claude"] is None

    def test_per_agent_env_vars_independent(
        self,
        clean_env: None,
        tmp_path: Path,
    ) -> None:
        claude = tmp_path / "c1"
        codex = tmp_path / "c2"
        gemini = tmp_path / "g1"
        for p in (claude, codex, gemini):
            p.mkdir()
        os.environ["ITMUX_CLAUDE_HOME"] = str(claude)
        os.environ["ITMUX_CODEX_HOME"] = str(codex)
        os.environ["ITMUX_GEMINI_HOME"] = str(gemini)

        result = driver._default_host_auth_from_env()

        assert result["claude"] == claude
        assert result["codex"] == codex
        assert result["gemini"] == gemini

    def test_partial_overrides_fall_back_to_home(
        self,
        clean_env: None,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Pretend $HOME has a real .codex but not .claude/.gemini.
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".codex").mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        # Override only claude.
        explicit_claude = tmp_path / "explicit-claude"
        explicit_claude.mkdir()
        os.environ["ITMUX_CLAUDE_HOME"] = str(explicit_claude)

        result = driver._default_host_auth_from_env()

        assert result["claude"] == explicit_claude  # from env var
        assert result["codex"] == fake_home / ".codex"  # from $HOME fallback
        assert result["gemini"] is None  # neither set, no $HOME/.gemini

    def test_expanduser_resolves_tilde(
        self,
        clean_env: None,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = tmp_path / "tilde-home"
        fake_home.mkdir()
        (fake_home / "vendored-claude").mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        os.environ["ITMUX_CLAUDE_HOME"] = "~/vendored-claude"

        result = driver._default_host_auth_from_env()

        assert result["claude"] == fake_home / "vendored-claude"


class TestDefaultClaudeDotjsonFromEnv:
    """`_default_claude_dotjson_from_env` resolves ITMUX_CLAUDE_JSON first."""

    def test_env_var_points_at_existing_file(
        self,
        clean_env: None,
        tmp_path: Path,
    ) -> None:
        json_path = tmp_path / "vendored-claude.json"
        json_path.write_text("{}")
        os.environ["ITMUX_CLAUDE_JSON"] = str(json_path)

        result = driver._default_claude_dotjson_from_env()

        assert result == json_path

    def test_env_var_pointing_at_missing_file_yields_none(
        self,
        clean_env: None,
        tmp_path: Path,
    ) -> None:
        os.environ["ITMUX_CLAUDE_JSON"] = str(tmp_path / "missing.json")

        result = driver._default_claude_dotjson_from_env()

        # Same opt-in semantics as the dir overrides: set but missing → None.
        assert result is None

    def test_falls_back_to_home_dotjson(
        self,
        clean_env: None,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / ".claude.json").write_text("{}")
        monkeypatch.setenv("HOME", str(fake_home))

        result = driver._default_claude_dotjson_from_env()

        assert result == fake_home / ".claude.json"


class TestClaudeAdapterDotjsonOverride:
    """`_ClaudeAdapter.prepare_host_auth` honors ctx.host_claude_dotjson."""

    def test_dotjson_override_replaces_sibling_fallback(
        self,
        tmp_path: Path,
    ) -> None:
        # DooD layout: .claude/ and .claude.json are NOT siblings on disk.
        claude_dir = tmp_path / "vendored-claude-dir"
        claude_dir.mkdir()
        (claude_dir / ".credentials.json").write_text("{}")

        dotjson_path = tmp_path / "elsewhere" / "mounted-claude.json"
        dotjson_path.parent.mkdir()
        dotjson_path.write_text(
            '{"oauthAccount":{"email":"dood@example.com","uuid":"d00d"},"theme":"dark"}'
        )

        throwaway = tmp_path / "throwaway"
        throwaway.mkdir()
        ctx = driver._AdapterContext(
            container="test-container",
            workdir="/workspace",
            host_throwaway_dir=throwaway,
            host_claude_dotjson=dotjson_path,
        )

        mounts = driver._ClaudeAdapter.prepare_host_auth(claude_dir, ctx)

        # Two mounts: ~/.claude (dir) and ~/.claude.json (file).
        assert set(mounts.keys()) == {"claude_dir", "claude_dotjson"}
        synthesized_dotjson = mounts["claude_dotjson"][0]

        import json

        body = json.loads(synthesized_dotjson.read_text())
        # The oauthAccount in the synthesized dotjson came from the EXPLICIT
        # override, not from a sibling-of-claude-dir lookup (the sibling
        # does NOT exist in this layout).
        assert body["oauthAccount"]["email"] == "dood@example.com"
        assert body["oauthAccount"]["uuid"] == "d00d"
        # Workspace trust still pre-seeded.
        assert body["projects"]["/workspace"]["hasTrustDialogAccepted"] is True

    def test_no_override_falls_back_to_sibling(
        self,
        tmp_path: Path,
    ) -> None:
        # Historical layout: .claude/ and .claude.json sit side by side.
        home = tmp_path / "home"
        home.mkdir()
        claude_dir = home / ".claude"
        claude_dir.mkdir()
        (claude_dir / ".credentials.json").write_text("{}")
        (home / ".claude.json").write_text(
            '{"oauthAccount":{"email":"sibling@example.com"},"theme":"light"}'
        )

        throwaway = tmp_path / "throwaway"
        throwaway.mkdir()
        ctx = driver._AdapterContext(
            container="test-container",
            workdir="/workspace",
            host_throwaway_dir=throwaway,
            host_claude_dotjson=None,  # no override
        )

        mounts = driver._ClaudeAdapter.prepare_host_auth(claude_dir, ctx)

        synthesized_dotjson = mounts["claude_dotjson"][0]
        import json

        body = json.loads(synthesized_dotjson.read_text())
        assert body["oauthAccount"]["email"] == "sibling@example.com"
        assert body["theme"] == "light"


class TestProviderAdapterPicksUpOverrides:
    """`InteractiveTmuxProvider` __init__ reads the env vars by default."""

    def test_constructor_picks_up_env_var_defaults(
        self,
        clean_env: None,
        tmp_path: Path,
    ) -> None:
        from agentic_isolation.providers.interactive_tmux import (
            InteractiveTmuxProvider,
        )

        explicit_claude = tmp_path / "explicit-claude"
        explicit_claude.mkdir()
        explicit_json = tmp_path / "explicit.json"
        explicit_json.write_text("{}")
        os.environ["ITMUX_CLAUDE_HOME"] = str(explicit_claude)
        os.environ["ITMUX_CLAUDE_JSON"] = str(explicit_json)

        provider = InteractiveTmuxProvider()

        assert provider._default_host_auth["claude"] == explicit_claude
        assert provider._default_host_claude_dotjson == explicit_json
