"""Application configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/events.db"

    # Event source - the JSONL file hooks write to
    events_jsonl_path: str = ".agentic/analytics/events.jsonl"

    # Model pricing config path (relative to repo root)
    pricing_config_path: str = "providers/models/anthropic/claude-sonnet-4.yaml"

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Polling interval for event watcher (seconds)
    poll_interval: float = 1.0

    class Config:
        env_prefix = "OBSERVABILITY_"
        env_file = ".env"


settings = Settings()


def get_repo_root() -> Path:
    """Get the repository root (3 levels up from this file)."""
    return Path(__file__).parent.parent.parent.parent.parent


def get_events_jsonl_path() -> Path:
    """Get absolute path to events JSONL file."""
    path = Path(settings.events_jsonl_path)
    if path.is_absolute():
        return path
    # Relative to repo root
    return get_repo_root() / path


def get_pricing_config_path() -> Path:
    """Get absolute path to pricing config."""
    return get_repo_root() / settings.pricing_config_path
