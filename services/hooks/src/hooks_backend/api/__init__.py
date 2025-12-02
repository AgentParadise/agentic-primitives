"""API routers for the hooks backend service."""

from hooks_backend.api.events import router as events_router
from hooks_backend.api.health import router as health_router

__all__ = ["events_router", "health_router"]
