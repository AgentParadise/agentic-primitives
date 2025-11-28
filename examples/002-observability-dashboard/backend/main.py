"""FastAPI application for observability dashboard."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import events_router, metrics_router, sessions_router
from src.config import settings
from src.db.database import init_db
from src.services import EventImporter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Event importer singleton
event_importer = EventImporter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    # Startup
    logger.info("Starting observability dashboard backend...")
    await init_db()
    await event_importer.start()
    logger.info("Backend ready")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await event_importer.stop()


# Create app
app = FastAPI(
    title="Agent Observability Dashboard",
    description="Real-time observability for Claude Agent SDK applications",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(events_router)
app.include_router(sessions_router)
app.include_router(metrics_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "observability-dashboard"}


@app.post("/import")
async def trigger_import():
    """Manually trigger an event import."""
    count = await event_importer.import_once()
    return {"imported": count}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
