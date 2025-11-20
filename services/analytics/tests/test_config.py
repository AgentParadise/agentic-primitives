"""Tests for analytics configuration

Test configuration loading, validation, and environment variable handling
"""

from pathlib import Path

import pytest

from analytics.models.config import AnalyticsConfig


@pytest.mark.unit
class TestAnalyticsConfigBasics:
    """Test basic configuration functionality"""

    def test_config_imports(self) -> None:
        """Test that AnalyticsConfig can be imported"""
        from analytics.models.config import AnalyticsConfig  # noqa: F401

    def test_config_instantiation(self) -> None:
        """Test that AnalyticsConfig can be instantiated"""
        config = AnalyticsConfig()
        assert config is not None

    def test_config_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test configuration with defaults"""
        monkeypatch.delenv("ANALYTICS_PROVIDER", raising=False)
        monkeypatch.delenv("ANALYTICS_OUTPUT_PATH", raising=False)
        config = AnalyticsConfig()
        assert config.provider == "unknown"
        assert config.publisher_backend == "file"
        assert config.api_timeout == 30
        assert config.retry_attempts == 3
        assert config.debug is False


@pytest.mark.unit
class TestAnalyticsConfigEnvironmentVariables:
    """Test configuration loading from environment variables"""

    def test_config_from_env_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading provider from environment"""
        monkeypatch.setenv("ANALYTICS_PROVIDER", "openai")
        config = AnalyticsConfig()
        assert config.provider == "openai"

    def test_config_from_env_publisher_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading publisher backend from environment"""
        monkeypatch.setenv("ANALYTICS_PUBLISHER_BACKEND", "api")
        config = AnalyticsConfig()
        assert config.publisher_backend == "api"

    def test_config_from_env_output_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test loading output path from environment"""
        output_path = tmp_path / "events.jsonl"
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))
        config = AnalyticsConfig()
        assert config.output_path == output_path

    def test_config_from_env_api_endpoint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading API endpoint from environment"""
        monkeypatch.setenv("ANALYTICS_API_ENDPOINT", "https://api.example.com")
        config = AnalyticsConfig()
        assert config.api_endpoint == "https://api.example.com"

    def test_config_from_env_api_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading API timeout from environment"""
        monkeypatch.setenv("ANALYTICS_API_TIMEOUT", "60")
        config = AnalyticsConfig()
        assert config.api_timeout == 60

    def test_config_from_env_retry_attempts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading retry attempts from environment"""
        monkeypatch.setenv("ANALYTICS_RETRY_ATTEMPTS", "5")
        config = AnalyticsConfig()
        assert config.retry_attempts == 5

    def test_config_from_env_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading debug flag from environment"""
        monkeypatch.setenv("ANALYTICS_DEBUG", "true")
        config = AnalyticsConfig()
        assert config.debug is True

    def test_config_from_env_debug_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading debug flag from environment (false)"""
        monkeypatch.setenv("ANALYTICS_DEBUG", "false")
        config = AnalyticsConfig()
        assert config.debug is False


@pytest.mark.unit
class TestAnalyticsConfigValidation:
    """Test configuration validation"""

    def test_validate_backend_config_file_valid(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test backend validation for file backend with valid config"""
        output_path = tmp_path / "analytics.jsonl"
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))

        config = AnalyticsConfig()
        config.validate_backend_config()  # Should not raise

    def test_validate_backend_config_file_missing_output_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test backend validation fails when file backend missing output_path"""
        monkeypatch.delenv("ANALYTICS_OUTPUT_PATH", raising=False)
        config = AnalyticsConfig(publisher_backend="file")

        with pytest.raises(ValueError, match="output_path is required"):
            config.validate_backend_config()

    def test_validate_backend_config_api_valid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test backend validation for API backend with valid config"""
        monkeypatch.setenv("ANALYTICS_API_ENDPOINT", "https://api.example.com")
        config = AnalyticsConfig(publisher_backend="api")
        config.validate_backend_config()  # Should not raise

    def test_validate_backend_config_api_missing_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test backend validation fails when API backend missing endpoint"""
        monkeypatch.delenv("ANALYTICS_API_ENDPOINT", raising=False)
        config = AnalyticsConfig(publisher_backend="api")

        with pytest.raises(ValueError, match="api_endpoint is required"):
            config.validate_backend_config()

    def test_validate_backend_config_file_backend(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test backend validation with file backend"""
        output_path = tmp_path / "events.jsonl"
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))
        config = AnalyticsConfig(publisher_backend="file")
        config.validate_backend_config()  # Should not raise


@pytest.mark.unit
class TestAnalyticsConfigOutputPath:
    """Test output path resolution and directory creation"""

    def test_get_output_path_resolved(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test output path resolution"""
        output_path = tmp_path / "analytics.jsonl"
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))

        config = AnalyticsConfig()
        resolved = config.get_output_path_resolved()

        assert resolved == output_path

    def test_get_output_path_creates_parent_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test output path resolution creates parent directory"""
        output_path = tmp_path / "subdir" / "analytics.jsonl"
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))

        config = AnalyticsConfig()
        resolved = config.get_output_path_resolved()

        assert resolved.parent.exists()
        assert str(resolved) == str(output_path)

    def test_get_output_path_not_set(self) -> None:
        """Test get_output_path_resolved fails when output_path not set"""
        config = AnalyticsConfig()
        config.output_path = None

        with pytest.raises(ValueError, match="output_path is not configured"):
            config.get_output_path_resolved()

    def test_get_output_path_nested_directories(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test output path resolution with deeply nested directories"""
        output_path = tmp_path / "a" / "b" / "c" / "d" / "analytics.jsonl"
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))

        config = AnalyticsConfig()
        resolved = config.get_output_path_resolved()

        assert resolved.parent.exists()
        assert str(resolved) == str(output_path)


@pytest.mark.unit
class TestAnalyticsConfigProviderAgnostic:
    """Test provider-agnostic configuration"""

    def test_config_accepts_any_provider_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that config accepts any provider string (not limited to enum)"""
        # Test various provider names
        providers = ["claude", "openai", "cursor", "gemini", "custom-provider"]

        for provider in providers:
            monkeypatch.setenv("ANALYTICS_PROVIDER", provider)
            config = AnalyticsConfig()
            assert config.provider == provider

    def test_config_provider_case_sensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that provider names are case-sensitive"""
        monkeypatch.setenv("ANALYTICS_PROVIDER", "Claude")
        config = AnalyticsConfig()
        assert config.provider == "Claude"  # Preserves case

    def test_config_provider_with_special_characters(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that provider names can contain special characters"""
        monkeypatch.setenv("ANALYTICS_PROVIDER", "my-custom-provider-v2")
        config = AnalyticsConfig()
        assert config.provider == "my-custom-provider-v2"


@pytest.mark.unit
class TestAnalyticsConfigSerialization:
    """Test configuration serialization"""

    def test_config_to_dict(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test configuration serialization to dict"""
        output_path = tmp_path / "events.jsonl"
        monkeypatch.setenv("ANALYTICS_PROVIDER", "claude")
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))
        monkeypatch.setenv("ANALYTICS_PUBLISHER_BACKEND", "file")

        config = AnalyticsConfig()
        config_dict = config.model_dump()

        assert config_dict["provider"] == "claude"
        assert config_dict["publisher_backend"] == "file"
        assert config_dict["output_path"] == output_path

    def test_config_to_json(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Test configuration serialization to JSON"""
        import json

        output_path = tmp_path / "events.jsonl"
        monkeypatch.setenv("ANALYTICS_PROVIDER", "claude")
        monkeypatch.setenv("ANALYTICS_OUTPUT_PATH", str(output_path))

        config = AnalyticsConfig()
        config_json = config.model_dump_json()

        assert isinstance(config_json, str)
        config_data = json.loads(config_json)
        assert config_data["provider"] == "claude"


@pytest.mark.unit
class TestAnalyticsConfigEdgeCases:
    """Test edge cases and error handling"""

    def test_config_with_empty_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test configuration with empty provider string"""
        monkeypatch.setenv("ANALYTICS_PROVIDER", "")
        config = AnalyticsConfig()
        assert config.provider == ""

    def test_config_with_invalid_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test configuration with invalid timeout value"""
        from pydantic import ValidationError

        monkeypatch.setenv("ANALYTICS_API_TIMEOUT", "invalid")
        with pytest.raises(ValidationError):
            AnalyticsConfig()

    def test_config_with_invalid_retry_attempts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test configuration with invalid retry attempts value"""
        from pydantic import ValidationError

        monkeypatch.setenv("ANALYTICS_RETRY_ATTEMPTS", "invalid")
        with pytest.raises(ValidationError):
            AnalyticsConfig()

    def test_config_with_negative_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test configuration with negative timeout value raises validation error"""
        from pydantic import ValidationError

        monkeypatch.setenv("ANALYTICS_API_TIMEOUT", "-1")
        with pytest.raises(ValidationError):
            AnalyticsConfig()

    def test_config_with_zero_retry_attempts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test configuration with zero retry attempts"""
        monkeypatch.setenv("ANALYTICS_RETRY_ATTEMPTS", "0")
        config = AnalyticsConfig()
        assert config.retry_attempts == 0
