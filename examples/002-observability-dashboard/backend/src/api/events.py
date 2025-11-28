"""Events API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.repository import SQLiteEventRepository
from ..models.schemas import EventResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
async def list_events(
    session_id: str | None = Query(None, description="Filter by session ID"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[EventResponse]:
    """List events with optional filtering."""
    repo = SQLiteEventRepository(db)
    return await repo.get_events(session_id=session_id, limit=limit, offset=offset)
