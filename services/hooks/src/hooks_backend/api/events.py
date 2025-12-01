"""Event API endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request

from hooks_backend.models import EventsAcceptedResponse, HookEventIn, HookEventStored

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])


@router.post("/events", response_model=EventsAcceptedResponse, status_code=202)
async def receive_event(event: HookEventIn, request: Request) -> EventsAcceptedResponse:
    """Receive a single hook event.

    Args:
        event: The hook event to store.
        request: The FastAPI request object (for accessing app state).

    Returns:
        Accepted response with count of 1.

    Raises:
        HTTPException: If storage fails.
    """
    storage = request.app.state.storage
    metrics = request.app.state.metrics

    metrics["events_received_total"] += 1

    try:
        stored_event = HookEventStored.from_input(event)
        count = await storage.store([stored_event])
        metrics["events_stored_total"] += count
        return EventsAcceptedResponse(accepted=count)
    except Exception as e:
        metrics["storage_errors_total"] += 1
        logger.exception("Failed to store event")
        raise HTTPException(status_code=500, detail=f"Storage error: {e}") from e


@router.post("/events/batch", response_model=EventsAcceptedResponse, status_code=202)
async def receive_batch(events: list[HookEventIn], request: Request) -> EventsAcceptedResponse:
    """Receive a batch of hook events.

    Args:
        events: List of hook events to store.
        request: The FastAPI request object (for accessing app state).

    Returns:
        Accepted response with count of events stored.

    Raises:
        HTTPException: If storage fails.
    """
    storage = request.app.state.storage
    metrics = request.app.state.metrics

    metrics["events_received_total"] += len(events)

    if not events:
        return EventsAcceptedResponse(accepted=0, message="No events to store")

    try:
        stored_events = [HookEventStored.from_input(e) for e in events]
        count = await storage.store(stored_events)
        metrics["events_stored_total"] += count
        return EventsAcceptedResponse(accepted=count)
    except Exception as e:
        metrics["storage_errors_total"] += 1
        logger.exception("Failed to store batch")
        raise HTTPException(status_code=500, detail=f"Storage error: {e}") from e
