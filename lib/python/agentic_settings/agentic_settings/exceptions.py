"""Custom exceptions for agentic_settings."""

from __future__ import annotations


class ConfigurationError(Exception):
    """Base exception for configuration errors."""

    pass


class MissingProviderError(ConfigurationError):
    """Raised when a required provider API key is missing.

    Provides helpful URLs for obtaining API keys.
    """

    PROVIDER_URLS: dict[str, str] = {
        "anthropic": "https://console.anthropic.com/settings/keys",
        "openai": "https://platform.openai.com/api-keys",
        "google": "https://makersuite.google.com/app/apikey",
        "firecrawl": "https://firecrawl.dev/app/api-keys",
    }

    def __init__(self, provider: str, env_var: str) -> None:
        """Initialize with provider name and expected env var.

        Args:
            provider: The provider name (e.g., 'anthropic', 'openai')
            env_var: The environment variable name expected
        """
        self.provider = provider.lower()
        self.env_var = env_var

        url = self.PROVIDER_URLS.get(self.provider, "the provider's website")
        message = (
            f"Missing {provider} API key.\n"
            f"Please set {env_var} in your environment or .env file.\n"
            f"Get your API key at: {url}"
        )
        super().__init__(message)


class InvalidConfigurationError(ConfigurationError):
    """Raised when configuration values are invalid."""

    def __init__(self, field: str, value: str, reason: str) -> None:
        """Initialize with field details.

        Args:
            field: The configuration field name
            value: The invalid value (masked if sensitive)
            reason: Why the value is invalid
        """
        self.field = field
        self.value = value
        self.reason = reason

        message = f"Invalid configuration for '{field}': {reason}"
        super().__init__(message)


class EnvFileNotFoundError(ConfigurationError):
    """Raised when .env file is required but not found."""

    def __init__(self, searched_paths: list[str]) -> None:
        """Initialize with searched paths.

        Args:
            searched_paths: List of paths that were searched
        """
        self.searched_paths = searched_paths

        paths_str = "\n  - ".join(searched_paths)
        message = (
            f"Could not find .env file. Searched:\n  - {paths_str}\n\n"
            "Create a .env file with your configuration, or set environment variables directly."
        )
        super().__init__(message)
