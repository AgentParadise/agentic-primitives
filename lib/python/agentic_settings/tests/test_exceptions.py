"""Tests for exceptions module."""

from __future__ import annotations

from agentic_settings import (
    ConfigurationError,
    EnvFileNotFoundError,
    InvalidConfigurationError,
    MissingProviderError,
)


class TestMissingProviderError:
    """Tests for MissingProviderError exception."""

    def test_anthropic_provider(self) -> None:
        """Test error message for Anthropic provider."""
        error = MissingProviderError("anthropic", "ANTHROPIC_API_KEY")

        assert error.provider == "anthropic"
        assert error.env_var == "ANTHROPIC_API_KEY"
        assert "ANTHROPIC_API_KEY" in str(error)
        assert "https://console.anthropic.com" in str(error)

    def test_openai_provider(self) -> None:
        """Test error message for OpenAI provider."""
        error = MissingProviderError("openai", "OPENAI_API_KEY")

        assert error.provider == "openai"
        assert "OPENAI_API_KEY" in str(error)
        assert "https://platform.openai.com" in str(error)

    def test_firecrawl_provider(self) -> None:
        """Test error message for Firecrawl provider."""
        error = MissingProviderError("firecrawl", "FIRECRAWL_API_KEY")

        assert "FIRECRAWL_API_KEY" in str(error)
        assert "https://firecrawl.dev" in str(error)

    def test_unknown_provider(self) -> None:
        """Test error message for unknown provider."""
        error = MissingProviderError("custom", "CUSTOM_API_KEY")

        assert error.provider == "custom"
        assert "CUSTOM_API_KEY" in str(error)
        # Should have generic URL guidance
        assert "provider's website" in str(error)

    def test_is_configuration_error(self) -> None:
        """Test that MissingProviderError is a ConfigurationError."""
        error = MissingProviderError("test", "TEST_KEY")
        assert isinstance(error, ConfigurationError)


class TestInvalidConfigurationError:
    """Tests for InvalidConfigurationError exception."""

    def test_error_message(self) -> None:
        """Test error message format."""
        error = InvalidConfigurationError(
            field="log_level",
            value="INVALID",
            reason="Must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL",
        )

        assert error.field == "log_level"
        assert error.value == "INVALID"
        assert error.reason == "Must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
        assert "log_level" in str(error)
        assert "Must be one of" in str(error)

    def test_is_configuration_error(self) -> None:
        """Test that InvalidConfigurationError is a ConfigurationError."""
        error = InvalidConfigurationError("field", "value", "reason")
        assert isinstance(error, ConfigurationError)


class TestEnvFileNotFoundError:
    """Tests for EnvFileNotFoundError exception."""

    def test_error_message_with_paths(self) -> None:
        """Test error message includes searched paths."""
        searched = ["/path/to/.env", "/parent/.env", "/.env"]
        error = EnvFileNotFoundError(searched)

        assert error.searched_paths == searched
        assert "/path/to/.env" in str(error)
        assert "/parent/.env" in str(error)
        assert "Create a .env file" in str(error)

    def test_is_configuration_error(self) -> None:
        """Test that EnvFileNotFoundError is a ConfigurationError."""
        error = EnvFileNotFoundError(["/path/.env"])
        assert isinstance(error, ConfigurationError)
