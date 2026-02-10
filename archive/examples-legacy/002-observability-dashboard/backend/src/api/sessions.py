"""Sessions API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.repository import SQLiteEventRepository
from ..models.schemas import SessionDetail, SessionSummary

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionSummary])
async def list_sessions(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[SessionSummary]:
    """List session summaries."""
    repo = SQLiteEventRepository(db)
    return await repo.get_sessions(limit=limit)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    """Get session detail with events."""
    repo = SQLiteEventRepository(db)
    session = await repo.get_session_detail(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session
