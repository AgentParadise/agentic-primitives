"""Centralized settings for agentic-primitives tools and components."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .discovery import find_env_file, find_project_root
from .exceptions import MissingProviderError


class AgenticSettings(BaseSettings):
    """Centralized settings for all agentic-primitives tools.

    Settings are loaded from (in priority order):
    1. Environment variables
    2. .env file (searched upward from cwd)
    3. Default values

    Example:
        ```python
        from agentic_settings import get_settings

        settings = get_settings()
        print(settings.log_level)
        settings.require_provider("anthropic")  # Raises if not set
        ```
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars
        case_sensitive=False,
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # AI Provider API Keys
    # ═══════════════════════════════════════════════════════════════════════════

    anthropic_api_key: SecretStr | None = Field(
        default=None,
        description="Anthropic API key for Claude models",
    )

    openai_api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key for GPT models",
    )

    google_api_key: SecretStr | None = Field(
        default=None,
        description="Google AI API key for Gemini models",
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # Tool Provider API Keys
    # ═══════════════════════════════════════════════════════════════════════════

    firecrawl_api_key: SecretStr | None = Field(
        default=None,
        description="Firecrawl API key for web scraping",
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # Logging Configuration
    # ═══════════════════════════════════════════════════════════════════════════

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Default log level for agentic components",
    )

    log_file: Path | None = Field(
        default=None,
        description="Path to log file. If None, logs only to console.",
    )

    log_console_format: Literal["human", "json"] = Field(
        default="human",
        description="Console log format: 'human' for readable, 'json' for structured",
    )

    log_session_id: str | None = Field(
        default=None,
        description="Session ID for correlating logs across components",
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # Project Paths
    # ═══════════════════════════════════════════════════════════════════════════

    project_root: Path | None = Field(
        default=None,
        description="Project root directory. Auto-detected if not set.",
    )

    primitives_dir: Path = Field(
        default=Path("primitives/v1"),
        description="Directory containing primitive definitions",
    )

    build_dir: Path = Field(
        default=Path("build"),
        description="Directory for build output",
    )

    docs_dir: Path = Field(
        default=Path("docs"),
        description="Directory for documentation",
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # Feature Flags
    # ═══════════════════════════════════════════════════════════════════════════

    debug_mode: bool = Field(
        default=False,
        description="Enable debug mode with verbose output",
    )

    analytics_enabled: bool = Field(
        default=True,
        description="Enable analytics event logging",
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # Validators
    # ═══════════════════════════════════════════════════════════════════════════

    @model_validator(mode="after")
    def set_project_root(self) -> "AgenticSettings":
        """Auto-detect project root if not explicitly set."""
        if self.project_root is None:
            detected = find_project_root()
            if detected:
                object.__setattr__(self, "project_root", detected)
        return self

    @field_validator("log_level", mode="before")
    @classmethod
    def uppercase_log_level(cls, v: str) -> str:
        """Ensure log level is uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v

    # ═══════════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════════

    def require_provider(self, provider: str) -> SecretStr:
        """Validate that a provider's API key is configured.

        Args:
            provider: Provider name ('anthropic', 'openai', 'google', 'firecrawl')

        Returns:
            The API key as SecretStr

        Raises:
            MissingProviderError: If the API key is not configured
        """
        provider_map = {
            "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
            "openai": ("openai_api_key", "OPENAI_API_KEY"),
            "google": ("google_api_key", "GOOGLE_API_KEY"),
            "firecrawl": ("firecrawl_api_key", "FIRECRAWL_API_KEY"),
        }

        provider_lower = provider.lower()
        if provider_lower not in provider_map:
            raise ValueError(
                f"Unknown provider: {provider}. "
                f"Valid providers: {list(provider_map.keys())}"
            )

        attr_name, env_var = provider_map[provider_lower]
        api_key = getattr(self, attr_name)

        if api_key is None:
            raise MissingProviderError(provider, env_var)

        return api_key

    def has_provider(self, provider: str) -> bool:
        """Check if a provider's API key is configured.

        Args:
            provider: Provider name

        Returns:
            True if API key is set, False otherwise
        """
        try:
            self.require_provider(provider)
            return True
        except (MissingProviderError, ValueError):
            return False

    def get_absolute_path(self, relative_path: Path) -> Path:
        """Convert a relative path to absolute using project_root.

        Args:
            relative_path: Path relative to project root

        Returns:
            Absolute path
        """
        if relative_path.is_absolute():
            return relative_path

        root = self.project_root or Path.cwd()
        return (root / relative_path).resolve()

    def model_dump_safe(self, **kwargs: Any) -> dict[str, Any]:
        """Dump model as dict with API keys masked.

        This is safe for logging and debugging without exposing secrets.

        Returns:
            Dict representation with masked secrets
        """
        data = self.model_dump(**kwargs)

        # Mask all SecretStr fields
        secret_fields = [
            "anthropic_api_key",
            "openai_api_key",
            "google_api_key",
            "firecrawl_api_key",
        ]

        for field in secret_fields:
            if field in data and data[field] is not None:
                # Show first 4 chars for identification, mask rest
                original = data[field]
                if hasattr(original, "get_secret_value"):
                    value = original.get_secret_value()
                else:
                    value = str(original)
                if len(value) > 8:
                    data[field] = f"{value[:4]}...{value[-4:]}"
                else:
                    data[field] = "***"

        # Convert Path objects to strings
        path_fields = ["project_root", "log_file", "primitives_dir", "build_dir", "docs_dir"]
        for field in path_fields:
            if field in data and data[field] is not None:
                data[field] = str(data[field])

        return data

    def __repr__(self) -> str:
        """Safe repr that masks secrets."""
        safe_data = self.model_dump_safe()
        items = [f"{k}={v!r}" for k, v in safe_data.items() if v is not None]
        return f"AgenticSettings({', '.join(items)})"


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton Pattern
# ═══════════════════════════════════════════════════════════════════════════════

_settings_instance: AgenticSettings | None = None


def get_settings(reload: bool = False) -> AgenticSettings:
    """Get the global settings instance.

    Uses singleton pattern with lazy initialization. Thread-safe for reading
    but not for first initialization (which is typically done at import time).

    Args:
        reload: If True, force reload settings from environment

    Returns:
        The global AgenticSettings instance

    Example:
        ```python
        from agentic_settings import get_settings

        settings = get_settings()
        if settings.has_provider("anthropic"):
            api_key = settings.anthropic_api_key.get_secret_value()
        ```
    """
    global _settings_instance

    if _settings_instance is None or reload:
        # Find and load .env file
        env_file = find_env_file()
        if env_file:
            # Load the env file before creating settings
            from dotenv import load_dotenv

            load_dotenv(env_file, override=True)

        _settings_instance = AgenticSettings()

    return _settings_instance


def reset_settings() -> None:
    """Reset the global settings instance.

    Useful for testing or when environment changes.
    """
    global _settings_instance
    _settings_instance = None

