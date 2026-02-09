"""Main application settings with validation and documentation.

This is the central configuration class. All settings are loaded from
environment variables and validated on startup.

Usage:
    from config import get_settings

    settings = get_settings()
    print(settings.app_name)

    # Access nested settings
    if settings.github.is_configured:
        print(settings.github.bot_username)

Dependencies:
    pip install pydantic pydantic-settings
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from config.github import GitHubSettings


class Environment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class Settings(BaseSettings):
    """Application settings with validation and documentation.

    All settings are loaded from environment variables.
    Required variables will fail fast on startup with clear error messages.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # =========================================================================
    # APPLICATION
    # =========================================================================

    app_name: str = Field(
        default="my-app",
        description="Application name for logging and identification",
    )

    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Current environment: development, staging, production, test",
    )

    debug: bool = Field(
        default=False,
        description=(
            "Enable debug mode. Shows detailed errors and enables debug logging. "
            "Never enable in production."
        ),
    )

    # =========================================================================
    # DATABASE
    # =========================================================================

    database_url: str | None = Field(
        default=None,
        description=(
            "PostgreSQL connection URL. "
            "Format: postgresql://user:password@host:port/database "
            "Required for production. Optional in development."
        ),
    )

    database_pool_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Database connection pool size",
    )

    # =========================================================================
    # SECRETS
    # =========================================================================

    api_key: SecretStr | None = Field(
        default=None,
        description=("API key for external service. Get from: https://example.com/keys"),
    )

    # =========================================================================
    # NESTED SETTINGS
    # =========================================================================

    @property
    def github(self) -> GitHubSettings:
        """Get GitHub settings (GITHUB_* prefix)."""
        from config.github import GitHubSettings

        return GitHubSettings()

    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == Environment.PRODUCTION

    @property
    def is_test(self) -> bool:
        """Check if running in test mode."""
        return self.environment == Environment.TEST


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.

    Settings are loaded once on first call and cached.
    Validates all environment variables immediately.

    Returns:
        Validated Settings instance.

    Raises:
        pydantic.ValidationError: If required env vars are missing or invalid.
    """
    return Settings()


def reset_settings() -> None:
    """Clear settings cache (for testing).

    Call this to force reload settings from environment.
    """
    get_settings.cache_clear()
