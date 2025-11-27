"""Tests for configuration management."""

import os
from pathlib import Path

import pytest

from agentic_logging.config import LogConfig


class TestLogConfig:
    """Tests for LogConfig class."""

    def test_from_env_with_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that default values are used when no env vars are set."""
        # Clear all logging-related env vars
        for key in list(os.environ.keys()):
            if key.startswith("LOG_"):
                monkeypatch.delenv(key, raising=False)

        config = LogConfig.from_env()

        assert config.level == "WARNING"
        assert config.log_file == Path("./logs/agentic.jsonl")
        assert config.console_format == "human"
        assert config.max_bytes == 10485760  # 10MB
        assert config.backup_count == 5

    def test_from_env_with_custom_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that custom env vars override defaults."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_FILE", "/var/log/test.jsonl")
        monkeypatch.setenv("LOG_CONSOLE_FORMAT", "json")
        monkeypatch.setenv("LOG_MAX_BYTES", "5242880")
        monkeypatch.setenv("LOG_BACKUP_COUNT", "3")

        config = LogConfig.from_env()

        assert config.level == "DEBUG"
        assert config.log_file == Path("/var/log/test.jsonl")
        assert config.console_format == "json"
        assert config.max_bytes == 5242880
        assert config.backup_count == 3

    def test_from_env_normalizes_log_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that log level is normalized to uppercase."""
        monkeypatch.setenv("LOG_LEVEL", "debug")

        config = LogConfig.from_env()

        assert config.level == "DEBUG"

    def test_from_env_invalid_log_level_uses_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that invalid log level falls back to WARNING."""
        monkeypatch.setenv("LOG_LEVEL", "INVALID")

        config = LogConfig.from_env()

        assert config.level == "WARNING"

    def test_from_env_invalid_console_format_uses_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid console format falls back to human."""
        monkeypatch.setenv("LOG_CONSOLE_FORMAT", "xml")

        config = LogConfig.from_env()

        assert config.console_format == "human"

    def test_get_component_level_returns_none_when_not_set(self) -> None:
        """Test that get_component_level returns None when not configured."""
        level = LogConfig.get_component_level("hooks.core.hooks_collector")

        assert level is None

    def test_get_component_level_returns_configured_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that get_component_level returns the configured level."""
        monkeypatch.setenv("LOG_LEVEL_HOOKS_CORE_HOOKS_COLLECTOR", "DEBUG")

        level = LogConfig.get_component_level("hooks.core.hooks_collector")

        assert level == "DEBUG"

    def test_get_component_level_normalizes_component_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that component name normalization works correctly."""
        # Set the env var with normalized name
        monkeypatch.setenv("LOG_LEVEL_ANALYTICS_PUBLISHERS_FILE", "INFO")

        # Request with dotted name
        level = LogConfig.get_component_level("analytics.publishers.file")

        assert level == "INFO"

    def test_get_component_level_normalizes_log_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that log level from env var is normalized to uppercase."""
        monkeypatch.setenv("LOG_LEVEL_TEST_MODULE", "debug")

        level = LogConfig.get_component_level("test.module")

        assert level == "DEBUG"

    def test_get_component_level_rejects_invalid_level(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that invalid log levels are rejected."""
        monkeypatch.setenv("LOG_LEVEL_TEST_MODULE", "INVALID")

        level = LogConfig.get_component_level("test.module")

        assert level is None

    def test_ensure_log_directory_creates_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that ensure_log_directory creates the log directory."""
        log_file = tmp_path / "logs" / "test.jsonl"
        monkeypatch.setenv("LOG_FILE", str(log_file))

        config = LogConfig.from_env()
        config.ensure_log_directory()

        assert log_file.parent.exists()
        assert log_file.parent.is_dir()

    def test_ensure_log_directory_handles_existing_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that ensure_log_directory handles existing directories gracefully."""
        log_file = tmp_path / "logs" / "test.jsonl"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("LOG_FILE", str(log_file))

        config = LogConfig.from_env()
        config.ensure_log_directory()  # Should not raise

        assert log_file.parent.exists()

    def test_ensure_log_directory_fails_silently_on_permission_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that ensure_log_directory fails silently on errors."""
        # Use a path that's likely to fail (root-level directory)
        monkeypatch.setenv("LOG_FILE", "/root/logs/test.jsonl")

        config = LogConfig.from_env()
        # Should not raise even if directory creation fails
        config.ensure_log_directory()

        # Test passes if no exception is raised
