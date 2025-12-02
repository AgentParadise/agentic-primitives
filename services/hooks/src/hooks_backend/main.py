"""Main FastAPI application for the hooks backend service."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from hooks_backend import __version__
from hooks_backend.api import events_router, health_router
from hooks_backend.config import Settings, StorageType, settings
from hooks_backend.storage import JSONLStorage, PostgresStorage, Storage

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_storage(config: Settings) -> Storage:
    """Create storage adapter based on configuration.

    Args:
        config: Application settings.

    Returns:
        Configured storage adapter.
    """
    storage_type = config.get_effective_storage_type()

    if storage_type == StorageType.POSTGRES:
        if not config.database_url:
            raise ValueError("DATABASE_URL is required for PostgreSQL storage")
        logger.info("Using PostgreSQL storage")
        return PostgresStorage(database_url=config.database_url)

    logger.info(f"Using JSONL storage at {config.jsonl_path}")
    return JSONLStorage(path=config.jsonl_path)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager.

    Handles startup and shutdown of storage connections.
    """
    # Startup
    logger.info(f"Starting hooks-backend v{__version__}")

    storage = create_storage(settings)
    await storage.connect()

    app.state.storage = storage
    app.state.start_time = time.time()
    app.state.metrics = {
        "events_received_total": 0,
        "events_stored_total": 0,
        "storage_errors_total": 0,
    }

    logger.info(f"Storage initialized: {storage.name}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await storage.close()
    logger.info("Storage connection closed")


# Create FastAPI app
app = FastAPI(
    title="agentic-hooks-backend",
    description="High-performance backend service for agentic hook events",
    version=__version__,
    lifespan=lifespan,
)

# Include routers
app.include_router(events_router)
app.include_router(health_router)


def main() -> None:
    """Run the server."""
    uvicorn.run(
        "hooks_backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
