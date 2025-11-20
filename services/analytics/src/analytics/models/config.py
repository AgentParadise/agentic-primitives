"""Configuration models for analytics service using Pydantic Settings

These models handle environment variable configuration with validation.
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AnalyticsConfig(BaseSettings):
    """Configuration for analytics service loaded from environment variables

    Environment variables:
    - ANALYTICS_PROVIDER: Provider name (claude, openai, etc.)
    - ANALYTICS_PUBLISHER_BACKEND: Backend type (file, api)
    - ANALYTICS_OUTPUT_PATH: File path for file backend
    - ANALYTICS_API_ENDPOINT: API endpoint for API backend
    - ANALYTICS_API_TIMEOUT: API timeout in seconds
    - ANALYTICS_RETRY_ATTEMPTS: Number of retry attempts
    - ANALYTICS_DEBUG: Enable debug logging
    """

    model_config = SettingsConfigDict(
        env_prefix="ANALYTICS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Provider configuration
    # NOTE: No validation on provider name - system is provider-agnostic
    # Provider names are determined by the hook system that calls this middleware
    provider: str = Field(
        default="unknown",
        description="Provider name (e.g., claude, openai, cursor). Set by hook caller.",
    )

    # Publisher configuration
    publisher_backend: Literal["file", "api"] = Field(
        default="file", description="Publisher backend type"
    )

    # File backend configuration
    output_path: Path | None = Field(
        default=None, description="Output file path for file backend (JSONL format)"
    )

    # API backend configuration
    api_endpoint: str | None = Field(default=None, description="API endpoint URL for API backend")
    api_timeout: int = Field(default=30, ge=1, le=300, description="API request timeout in seconds")
    retry_attempts: int = Field(
        default=3, ge=0, le=10, description="Number of retry attempts for failed requests"
    )

    # General configuration
    debug: bool = Field(default=False, description="Enable debug logging")

    @field_validator("output_path")
    @classmethod
    def validate_output_path_for_file_backend(cls, v: Path | None, info: Any) -> Path | None:
        """Validate that output_path is set when using file backend"""
        # Note: We can't access other fields during validation in Pydantic v2
        # This validation will happen at the application level
        return v

    @field_validator("api_endpoint")
    @classmethod
    def validate_api_endpoint_for_api_backend(cls, v: str | None, info: Any) -> str | None:
        """Validate that api_endpoint is set when using API backend"""
        # Note: We can't access other fields during validation in Pydantic v2
        # This validation will happen at the application level
        return v

    def validate_backend_config(self) -> None:
        """Validate that required fields are set based on backend type

        Raises:
            ValueError: If required configuration is missing
        """
        if self.publisher_backend == "file":
            if self.output_path is None:
                raise ValueError("output_path is required when publisher_backend is 'file'")
        elif self.publisher_backend == "api":
            if self.api_endpoint is None:
                raise ValueError("api_endpoint is required when publisher_backend is 'api'")

    def get_output_path_resolved(self) -> Path:
        """Get output path with parent directory created

        Returns:
            Path: Resolved output path

        Raises:
            ValueError: If output_path is not set
        """
        if self.output_path is None:
            raise ValueError("output_path is not configured")

        # Expand user home directory and resolve path
        resolved_path = self.output_path.expanduser().resolve()

        # Create parent directory if it doesn't exist
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

        return resolved_path
