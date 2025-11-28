"""Metrics API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_db
from ..db.repository import SQLiteEventRepository
from ..models.schemas import MetricsResponse

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsResponse)
async def get_metrics(
    db: AsyncSession = Depends(get_db),
) -> MetricsResponse:
    """Get aggregated metrics."""
    repo = SQLiteEventRepository(db)
    return await repo.get_metrics()
