"""Tests for model alias resolution."""

import pytest

from src.models import get_available_aliases, resolve_model


class TestResolveModel:
    """Test model alias resolution."""

    def test_simple_alias_claude_haiku(self) -> None:
        """claude-haiku resolves to full API name."""
        result = resolve_model("claude-haiku")
        assert result == "claude-haiku-4-5-20251001"

    def test_simple_alias_claude_sonnet(self) -> None:
        """claude-sonnet resolves to full API name."""
        result = resolve_model("claude-sonnet")
        assert result == "claude-sonnet-4-5-20250929"

    def test_simple_alias_claude_opus(self) -> None:
        """claude-opus resolves to full API name."""
        result = resolve_model("claude-opus")
        assert result == "claude-opus-4-5-20251101"

    def test_legacy_alias_haiku(self) -> None:
        """Legacy 'haiku' alias still works."""
        result = resolve_model("haiku")
        assert result == "claude-haiku-4-5-20251001"

    def test_model_id_resolves(self) -> None:
        """Model ID like claude-4-5-haiku resolves to API name."""
        result = resolve_model("claude-4-5-haiku")
        assert result == "claude-haiku-4-5-20251001"

    def test_full_api_name_passthrough(self) -> None:
        """Full API name is returned unchanged."""
        api_name = "claude-haiku-4-5-20251001"
        result = resolve_model(api_name)
        assert result == api_name

    def test_unknown_model_raises(self) -> None:
        """Unknown model raises ValueError with helpful message."""
        with pytest.raises(ValueError, match="Unknown model"):
            resolve_model("not-a-real-model")

    def test_empty_model_raises(self) -> None:
        """Empty model raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            resolve_model("")


class TestGetAvailableAliases:
    """Test available aliases listing."""

    def test_returns_list(self) -> None:
        """Returns a list of available aliases."""
        aliases = get_available_aliases()
        assert isinstance(aliases, list)
        assert len(aliases) > 0

    def test_includes_claude_haiku(self) -> None:
        """Includes claude-haiku alias."""
        aliases = get_available_aliases()
        assert "claude-haiku" in aliases

    def test_includes_claude_sonnet(self) -> None:
        """Includes claude-sonnet alias."""
        aliases = get_available_aliases()
        assert "claude-sonnet" in aliases

    def test_includes_claude_opus(self) -> None:
        """Includes claude-opus alias."""
        aliases = get_available_aliases()
        assert "claude-opus" in aliases
