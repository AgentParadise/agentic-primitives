"""Centralized settings for agentic-primitives.

This package provides a unified configuration system for all agentic tools,
handling API keys, logging configuration, and project paths.

Example:
    ```python
    from agentic_settings import get_settings

    # Get settings instance (singleton)
    settings = get_settings()

    # Check if provider is configured
    if settings.has_provider("anthropic"):
        api_key = settings.anthropic_api_key.get_secret_value()

    # Require a provider (raises MissingProviderError if not set)
    settings.require_provider("firecrawl")

    # Safe logging (secrets masked)
    print(settings.model_dump_safe())
    ```
"""

from .discovery import (
    find_env_file,
    find_project_root,
    get_workspace_root,
    is_in_workspace,
    resolve_path,
)
from .exceptions import (
    ConfigurationError,
    EnvFileNotFoundError,
    InvalidConfigurationError,
    MissingProviderError,
)
from .settings import AgenticSettings, get_settings, reset_settings

__all__ = [
    # Settings
    "AgenticSettings",
    "get_settings",
    "reset_settings",
    # Discovery
    "find_project_root",
    "find_env_file",
    "get_workspace_root",
    "is_in_workspace",
    "resolve_path",
    # Exceptions
    "ConfigurationError",
    "MissingProviderError",
    "InvalidConfigurationError",
    "EnvFileNotFoundError",
]

__version__ = "0.1.0"
