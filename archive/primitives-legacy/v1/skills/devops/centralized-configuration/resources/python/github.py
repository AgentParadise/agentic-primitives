"""GitHub App settings with GITHUB_* prefix.

Example of modular settings using env_prefix for namespacing.
All variables automatically get the GITHUB_ prefix:
    app_id -> GITHUB_APP_ID
    installation_id -> GITHUB_INSTALLATION_ID

Usage:
    from config.github import GitHubSettings

    github = GitHubSettings()
    if github.is_configured:
        print(f"Bot: {github.bot_username}")
        print(f"Email: {github.bot_email}")
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# =============================================================================
# CONSTANTS - Single source of truth for env var names
# =============================================================================

ENV_PREFIX = "GITHUB_"

# Field names (without prefix)
FIELD_APP_ID = "app_id"
FIELD_APP_NAME = "app_name"
FIELD_INSTALLATION_ID = "installation_id"
FIELD_PRIVATE_KEY = "private_key"
FIELD_WEBHOOK_SECRET = "webhook_secret"

# Full env var names (with prefix)
ENV_APP_ID = f"{ENV_PREFIX}{FIELD_APP_ID.upper()}"
ENV_APP_NAME = f"{ENV_PREFIX}{FIELD_APP_NAME.upper()}"
ENV_INSTALLATION_ID = f"{ENV_PREFIX}{FIELD_INSTALLATION_ID.upper()}"
ENV_PRIVATE_KEY = f"{ENV_PREFIX}{FIELD_PRIVATE_KEY.upper()}"
ENV_WEBHOOK_SECRET = f"{ENV_PREFIX}{FIELD_WEBHOOK_SECRET.upper()}"


class GitHubSettings(BaseSettings):
    """GitHub App authentication settings.

    Uses GITHUB_* prefix for all variables.
    See: https://docs.github.com/en/apps/creating-github-apps
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # =========================================================================
    # APP IDENTITY
    # =========================================================================

    app_id: str | None = Field(
        default=None,
        description=(
            "GitHub App ID (numeric). "
            "Find at: https://github.com/settings/apps/<app-name> → General"
        ),
    )

    app_name: str | None = Field(
        default=None,
        description=(
            "GitHub App slug for commit attribution. "
            "Example: 'my-bot' → commits appear as 'my-bot[bot]'"
        ),
    )

    # =========================================================================
    # INSTALLATION
    # =========================================================================

    installation_id: str | None = Field(
        default=None,
        description=(
            "Installation ID for the organization/account. "
            "Find at: GitHub Settings → Installations → Configure URL"
        ),
    )

    # =========================================================================
    # AUTHENTICATION
    # =========================================================================

    private_key: SecretStr | None = Field(
        default=None,
        description=(
            "RSA private key in PEM format for JWT signing. "
            "Generate at: GitHub App settings → Private keys"
        ),
    )

    webhook_secret: SecretStr | None = Field(
        default=None,
        description=("HMAC secret for webhook verification. Generate with: openssl rand -hex 32"),
    )

    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================

    @property
    def is_configured(self) -> bool:
        """Check if GitHub App is fully configured for API access."""
        return bool(self.app_id and self.installation_id and self.private_key)

    @property
    def can_verify_webhooks(self) -> bool:
        """Check if webhook verification is enabled."""
        return self.webhook_secret is not None

    @property
    def bot_username(self) -> str | None:
        """Get bot username for commit attribution."""
        if self.app_name:
            return f"{self.app_name}[bot]"
        return None

    @property
    def bot_email(self) -> str | None:
        """Get bot email in GitHub noreply format."""
        if self.app_id and self.app_name:
            return f"{self.app_id}+{self.app_name}[bot]@users.noreply.github.com"
        return None

    # =========================================================================
    # VALIDATION
    # =========================================================================

    @model_validator(mode="after")
    def validate_complete(self) -> Self:
        """Ensure all-or-nothing configuration.

        If any required field is set, all must be set.
        This prevents partial configuration errors.
        """
        required = [self.app_id, self.installation_id, self.private_key]
        provided = sum(1 for f in required if f is not None)

        if 0 < provided < 3:
            missing = []
            if not self.app_id:
                missing.append(ENV_APP_ID)
            if not self.installation_id:
                missing.append(ENV_INSTALLATION_ID)
            if not self.private_key:
                missing.append(ENV_PRIVATE_KEY)
            msg = f"Incomplete GitHub config. Missing: {', '.join(missing)}"
            raise ValueError(msg)

        return self
