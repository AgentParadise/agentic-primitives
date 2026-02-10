"""Tests for workspace prompt loading."""

from __future__ import annotations

from agentic_workspace import AEF_WORKSPACE_PROMPT, Prompt, load_prompt


class TestPromptEnum:
    """Tests for the Prompt enum."""

    def test_prompt_enum_has_aef_workspace(self) -> None:
        """AEF_WORKSPACE prompt is defined."""
        assert Prompt.AEF_WORKSPACE.value == "aef-workspace"

    def test_prompt_enum_is_str(self) -> None:
        """Prompt enum members have string values for easy use."""
        assert isinstance(Prompt.AEF_WORKSPACE.value, str)
        assert Prompt.AEF_WORKSPACE.value == "aef-workspace"


class TestLoadPrompt:
    """Tests for the load_prompt function."""

    def test_load_aef_workspace_prompt(self) -> None:
        """Can load the AEF workspace prompt."""
        prompt = load_prompt(Prompt.AEF_WORKSPACE)
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # Should be substantial

    def test_aef_workspace_prompt_contains_artifacts_output(self) -> None:
        """AEF workspace prompt mentions artifacts/output directory."""
        prompt = load_prompt(Prompt.AEF_WORKSPACE)
        assert "artifacts/output/" in prompt
        assert "/workspace" in prompt

    def test_aef_workspace_prompt_mentions_artifacts_input(self) -> None:
        """AEF workspace prompt mentions artifacts/input directory."""
        prompt = load_prompt(Prompt.AEF_WORKSPACE)
        assert "artifacts/input/" in prompt

    def test_aef_workspace_prompt_mentions_repos(self) -> None:
        """AEF workspace prompt mentions repos directory."""
        prompt = load_prompt(Prompt.AEF_WORKSPACE)
        assert "repos/" in prompt

    def test_aef_workspace_prompt_mentions_ephemeral(self) -> None:
        """AEF workspace prompt mentions ephemeral nature."""
        prompt = load_prompt(Prompt.AEF_WORKSPACE)
        assert "ephemeral" in prompt.lower()


class TestPreloadedConstants:
    """Tests for pre-loaded prompt constants."""

    def test_aef_workspace_prompt_is_loaded(self) -> None:
        """AEF_WORKSPACE_PROMPT constant is available at import."""
        assert isinstance(AEF_WORKSPACE_PROMPT, str)
        assert len(AEF_WORKSPACE_PROMPT) > 100

    def test_preloaded_matches_loaded(self) -> None:
        """Pre-loaded constant matches load_prompt() result."""
        loaded = load_prompt(Prompt.AEF_WORKSPACE)
        assert loaded == AEF_WORKSPACE_PROMPT


class TestTypeChecking:
    """Tests that verify type safety (these also serve as documentation)."""

    def test_load_prompt_requires_enum(self) -> None:
        """load_prompt() requires Prompt enum, not arbitrary string.

        Note: This is enforced by mypy at type-check time, not runtime.
        At runtime, passing a string would work but is not type-safe.
        """
        # This is the correct, type-safe usage
        prompt = load_prompt(Prompt.AEF_WORKSPACE)
        assert prompt is not None

        # The following would cause a mypy error:
        # load_prompt("aef-workspace")  # type: ignore[arg-type]
