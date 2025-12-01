"""Health and metrics API endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request, Response

from hooks_backend import __version__
from hooks_backend.models import HealthResponse, MetricsResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint.

    Args:
        request: The FastAPI request object.

    Returns:
        Health status response.
    """
    storage = request.app.state.storage

    is_healthy = await storage.health_check()

    return HealthResponse(
        status="healthy" if is_healthy else "unhealthy",
        storage=storage.name,
        version=__version__,
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(request: Request) -> MetricsResponse:
    """Get service metrics.

    Args:
        request: The FastAPI request object.

    Returns:
        Metrics response with event counts.
    """
    metrics = request.app.state.metrics
    start_time = request.app.state.start_time

    return MetricsResponse(
        events_received_total=metrics["events_received_total"],
        events_stored_total=metrics["events_stored_total"],
        storage_errors_total=metrics["storage_errors_total"],
        uptime_seconds=time.time() - start_time,
    )


@router.get("/metrics/prometheus")
async def get_prometheus_metrics(request: Request) -> Response:
    """Get metrics in Prometheus format.

    Args:
        request: The FastAPI request object.

    Returns:
        Prometheus-formatted metrics text.
    """
    metrics = request.app.state.metrics
    start_time = request.app.state.start_time
    uptime = time.time() - start_time

    prometheus_text = f"""# HELP hooks_events_received_total Total number of events received
# TYPE hooks_events_received_total counter
hooks_events_received_total {metrics["events_received_total"]}

# HELP hooks_events_stored_total Total number of events stored
# TYPE hooks_events_stored_total counter
hooks_events_stored_total {metrics["events_stored_total"]}

# HELP hooks_storage_errors_total Total number of storage errors
# TYPE hooks_storage_errors_total counter
hooks_storage_errors_total {metrics["storage_errors_total"]}

# HELP hooks_uptime_seconds Service uptime in seconds
# TYPE hooks_uptime_seconds gauge
hooks_uptime_seconds {uptime:.2f}
"""

    return Response(content=prometheus_text, media_type="text/plain; charset=utf-8")
