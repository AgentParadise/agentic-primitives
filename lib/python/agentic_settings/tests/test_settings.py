"""Tests for settings module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from agentic_settings import (
    AgenticSettings,
    MissingProviderError,
    get_settings,
    reset_settings,
)


class TestAgenticSettings:
    """Tests for AgenticSettings class."""

    def setup_method(self) -> None:
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self) -> None:
        """Clean up after each test."""
        reset_settings()

    def test_default_values(self) -> None:
        """Test that defaults are set correctly."""
        settings = AgenticSettings()

        assert settings.log_level == "INFO"
        assert settings.log_console_format == "human"
        assert settings.debug_mode is False
        assert settings.analytics_enabled is True
        assert settings.primitives_dir == Path("primitives/v1")
        assert settings.build_dir == Path("build")

    def test_load_from_env_vars(self) -> None:
        """Test loading settings from environment variables."""
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_API_KEY": "sk-ant-test123",
                "LOG_LEVEL": "DEBUG",
                "DEBUG_MODE": "true",
            },
        ):
            settings = AgenticSettings()

            assert settings.anthropic_api_key is not None
            assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test123"
            assert settings.log_level == "DEBUG"
            assert settings.debug_mode is True

    def test_log_level_case_insensitive(self) -> None:
        """Test that log level is case-insensitive."""
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            settings = AgenticSettings()
            assert settings.log_level == "DEBUG"

    def test_secret_str_masking(self) -> None:
        """Test that API keys are masked in repr."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-secret-key-12345"}):
            settings = AgenticSettings()

            # Repr should not contain the full key
            repr_str = repr(settings)
            assert "sk-ant-secret-key-12345" not in repr_str

    def test_model_dump_safe_masks_secrets(self) -> None:
        """Test that model_dump_safe masks API keys."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-secret-key-12345"}):
            settings = AgenticSettings()
            safe_data = settings.model_dump_safe()

            # Key should be partially masked
            assert safe_data["anthropic_api_key"] is not None
            assert "sk-a" in safe_data["anthropic_api_key"]  # First 4 chars
            assert "2345" in safe_data["anthropic_api_key"]  # Last 4 chars
            assert "secret" not in safe_data["anthropic_api_key"]  # Middle hidden


class TestRequireProvider:
    """Tests for require_provider method."""

    def setup_method(self) -> None:
        """Reset settings before each test."""
        reset_settings()

    def test_require_provider_success(self) -> None:
        """Test require_provider returns key when set."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            settings = AgenticSettings()
            api_key = settings.require_provider("anthropic")

            assert isinstance(api_key, SecretStr)
            assert api_key.get_secret_value() == "sk-ant-test"

    def test_require_provider_missing(self) -> None:
        """Test require_provider raises when key missing."""
        with patch.dict(os.environ, {}, clear=True):
            settings = AgenticSettings()

            with pytest.raises(MissingProviderError) as exc_info:
                settings.require_provider("anthropic")

            error = exc_info.value
            assert error.provider == "anthropic"
            assert error.env_var == "ANTHROPIC_API_KEY"
            assert "ANTHROPIC_API_KEY" in str(error)
            assert "https://console.anthropic.com" in str(error)

    def test_require_provider_unknown(self) -> None:
        """Test require_provider raises ValueError for unknown provider."""
        settings = AgenticSettings()

        with pytest.raises(ValueError) as exc_info:
            settings.require_provider("unknown_provider")

        assert "Unknown provider" in str(exc_info.value)

    def test_has_provider_true(self) -> None:
        """Test has_provider returns True when set."""
        with patch.dict(os.environ, {"FIRECRAWL_API_KEY": "fc-test"}):
            settings = AgenticSettings()
            assert settings.has_provider("firecrawl") is True

    def test_has_provider_false(self) -> None:
        """Test has_provider returns False when not set."""
        with patch.dict(os.environ, {}, clear=True):
            settings = AgenticSettings()
            assert settings.has_provider("anthropic") is False


class TestGetSettings:
    """Tests for get_settings singleton function."""

    def setup_method(self) -> None:
        """Reset settings before each test."""
        reset_settings()

    def teardown_method(self) -> None:
        """Clean up after each test."""
        reset_settings()

    def test_singleton_pattern(self) -> None:
        """Test that get_settings returns same instance."""
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_reload_creates_new_instance(self) -> None:
        """Test that reload=True creates new instance."""
        settings1 = get_settings()
        settings2 = get_settings(reload=True)

        assert settings1 is not settings2

    def test_reset_settings_clears_cache(self) -> None:
        """Test that reset_settings clears the singleton."""
        settings1 = get_settings()
        reset_settings()
        settings2 = get_settings()

        assert settings1 is not settings2


class TestPathHelpers:
    """Tests for path helper methods."""

    def setup_method(self) -> None:
        """Reset settings before each test."""
        reset_settings()

    def test_get_absolute_path_relative(self) -> None:
        """Test converting relative path to absolute."""
        with patch.dict(os.environ, {"PROJECT_ROOT": "/test/project"}):
            settings = AgenticSettings()
            abs_path = settings.get_absolute_path(Path("src/main.py"))

            assert abs_path.is_absolute()
            assert str(abs_path).endswith("src/main.py")

    def test_get_absolute_path_already_absolute(self) -> None:
        """Test that absolute paths are returned unchanged."""
        settings = AgenticSettings()
        abs_path = settings.get_absolute_path(Path("/absolute/path"))

        assert abs_path == Path("/absolute/path")
