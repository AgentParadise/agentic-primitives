"""Configuration settings for the hooks backend service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class StorageType(str, Enum):
    """Storage backend type."""

    AUTO = "auto"
    POSTGRES = "postgres"
    JSONL = "jsonl"


@dataclass
class Settings:
    """Application settings loaded from environment variables.

    Attributes:
        database_url: PostgreSQL connection string.
        storage_type: Storage backend type (auto, postgres, jsonl).
        jsonl_path: Path for JSONL storage.
        log_level: Logging level.
        host: Server host.
        port: Server port.
    """

    database_url: str | None = None
    storage_type: StorageType = StorageType.AUTO
    jsonl_path: Path = field(default_factory=lambda: Path(".agentic/analytics/events.jsonl"))
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8080

    @classmethod
    def from_env(cls) -> Settings:
        """Load settings from environment variables.

        Returns:
            Settings instance with values from environment.
        """
        database_url = os.getenv("DATABASE_URL")
        storage_type_str = os.getenv("STORAGE_TYPE", "auto").lower()

        try:
            storage_type = StorageType(storage_type_str)
        except ValueError:
            storage_type = StorageType.AUTO

        jsonl_path_str = os.getenv("JSONL_PATH", ".agentic/analytics/events.jsonl")

        return cls(
            database_url=database_url,
            storage_type=storage_type,
            jsonl_path=Path(jsonl_path_str),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8080")),
        )

    def get_effective_storage_type(self) -> StorageType:
        """Determine the effective storage type based on configuration.

        If storage_type is AUTO, uses PostgreSQL if DATABASE_URL is set,
        otherwise falls back to JSONL.

        Returns:
            The effective storage type to use.
        """
        if self.storage_type != StorageType.AUTO:
            return self.storage_type

        if self.database_url:
            return StorageType.POSTGRES

        return StorageType.JSONL


# Global settings instance
settings = Settings.from_env()
