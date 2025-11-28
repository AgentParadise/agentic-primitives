"""Repository pattern for database operations.

This abstraction allows swapping SQLite for Postgres/Supabase later.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.events import AgentEvent
from ..models.schemas import (
    EventResponse,
    MetricsResponse,
    SessionDetail,
    SessionSummary,
)
from .tables import Event, ImportState, Session


class EventRepository(Protocol):
    """Abstract event repository interface."""

    async def append_event(self, event: AgentEvent) -> str:
        """Append an event, return its ID."""
        ...

    async def get_events(
        self,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventResponse]:
        """Get events with optional filtering."""
        ...

    async def get_sessions(self, limit: int = 50) -> list[SessionSummary]:
        """Get session summaries."""
        ...

    async def get_session_detail(self, session_id: str) -> SessionDetail | None:
        """Get session with all events."""
        ...

    async def get_metrics(self) -> MetricsResponse:
        """Get aggregated metrics."""
        ...


class SQLiteEventRepository:
    """SQLite implementation of EventRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def append_event(self, event: AgentEvent) -> str:
        """Append an event to the database."""
        event_id = str(uuid.uuid4())

        db_event = Event(
            id=event_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            handler=event.handler,
            hook_event=event.hook_event,
            tool_name=event.tool_name,
            tool_use_id=event.tool_use_id,
            session_id=event.session_id,
            decision=getattr(event, "decision", None),
            reason=getattr(event, "reason", None),
            success=getattr(event, "success", None),
            output_preview=getattr(event, "output_preview", None),
            input_preview=getattr(event, "input_preview", None),
            validators_run=getattr(event, "validators_run", None),
            estimated_tokens=event.estimated_tokens,
            estimated_cost_usd=event.estimated_cost_usd,
            audit_transcript_path=event.audit.transcript_path if event.audit else None,
            audit_cwd=event.audit.cwd if event.audit else None,
            audit_permission_mode=event.audit.permission_mode if event.audit else None,
            raw_event=event.model_dump_json(),
        )

        self.session.add(db_event)

        # Update or create session
        await self._update_session(event, db_event)

        return event_id

    async def _update_session(self, event: AgentEvent, db_event: Event) -> None:
        """Update session aggregates."""
        if not event.session_id:
            return

        result = await self.session.execute(
            select(Session).where(Session.session_id == event.session_id)
        )
        session = result.scalar_one_or_none()

        if session is None:
            session = Session(
                session_id=event.session_id,
                started_at=event.timestamp,
                total_events=0,
                tool_calls=0,
                blocked_calls=0,
                total_tokens=0,
                total_cost_usd=0.0,
            )
            self.session.add(session)

        # Update aggregates
        session.total_events += 1
        if event.event_type == "tool_execution":
            session.tool_calls += 1
        if getattr(event, "decision", None) == "block":
            session.blocked_calls += 1
        if event.estimated_tokens:
            session.total_tokens += event.estimated_tokens
        if event.estimated_cost_usd:
            session.total_cost_usd += event.estimated_cost_usd

        # Update end time
        session.ended_at = event.timestamp

    async def get_events(
        self,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[EventResponse]:
        """Get events with optional filtering."""
        query = select(Event).order_by(Event.timestamp.desc()).limit(limit).offset(offset)

        if session_id:
            query = query.where(Event.session_id == session_id)

        result = await self.session.execute(query)
        events = result.scalars().all()

        return [
            EventResponse(
                id=e.id,
                timestamp=e.timestamp,
                event_type=e.event_type,
                handler=e.handler,
                hook_event=e.hook_event,
                tool_name=e.tool_name,
                session_id=e.session_id,
                decision=e.decision,
                reason=e.reason,
                success=e.success,
                estimated_tokens=e.estimated_tokens,
                estimated_cost_usd=e.estimated_cost_usd,
            )
            for e in events
        ]

    async def get_sessions(self, limit: int = 50) -> list[SessionSummary]:
        """Get session summaries."""
        result = await self.session.execute(
            select(Session).order_by(Session.started_at.desc()).limit(limit)
        )
        sessions = result.scalars().all()

        return [
            SessionSummary(
                session_id=s.session_id,
                started_at=s.started_at,
                ended_at=s.ended_at,
                duration_seconds=(
                    (s.ended_at - s.started_at).total_seconds() if s.ended_at else None
                ),
                model=s.model,
                total_events=s.total_events,
                tool_calls=s.tool_calls,
                blocked_calls=s.blocked_calls,
                total_tokens=s.total_tokens,
                total_cost_usd=s.total_cost_usd,
            )
            for s in sessions
        ]

    async def get_session_detail(self, session_id: str) -> SessionDetail | None:
        """Get session with all events."""
        result = await self.session.execute(select(Session).where(Session.session_id == session_id))
        session = result.scalar_one_or_none()

        if session is None:
            return None

        events = await self.get_events(session_id=session_id, limit=1000)

        # Count tools used
        tools_used: dict[str, int] = {}
        for e in events:
            if e.tool_name:
                tools_used[e.tool_name] = tools_used.get(e.tool_name, 0) + 1

        return SessionDetail(
            session_id=session.session_id,
            started_at=session.started_at,
            ended_at=session.ended_at,
            duration_seconds=(
                (session.ended_at - session.started_at).total_seconds()
                if session.ended_at
                else None
            ),
            model=session.model,
            total_events=session.total_events,
            tool_calls=session.tool_calls,
            blocked_calls=session.blocked_calls,
            total_tokens=session.total_tokens,
            total_cost_usd=session.total_cost_usd,
            events=events,
            tools_used=tools_used,
        )

    async def get_metrics(self) -> MetricsResponse:
        """Get aggregated metrics."""
        now = datetime.now(UTC)
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(hours=24)

        # Total counts
        total_events = await self.session.scalar(select(func.count(Event.id)))
        total_sessions = await self.session.scalar(select(func.count(Session.session_id)))

        # Tool calls and blocks
        total_tool_calls = await self.session.scalar(
            select(func.count(Event.id)).where(Event.event_type == "tool_execution")
        )
        total_blocked = await self.session.scalar(
            select(func.count(Event.id)).where(Event.decision == "block")
        )

        # Totals from sessions
        totals = await self.session.execute(
            select(
                func.sum(Session.total_tokens),
                func.sum(Session.total_cost_usd),
            )
        )
        total_tokens, total_cost = totals.one()

        # Last hour
        tokens_last_hour = await self.session.scalar(
            select(func.sum(Event.estimated_tokens)).where(Event.timestamp >= hour_ago)
        )
        cost_last_hour = await self.session.scalar(
            select(func.sum(Event.estimated_cost_usd)).where(Event.timestamp >= hour_ago)
        )

        # Last 24h
        tokens_last_24h = await self.session.scalar(
            select(func.sum(Event.estimated_tokens)).where(Event.timestamp >= day_ago)
        )
        cost_last_24h = await self.session.scalar(
            select(func.sum(Event.estimated_cost_usd)).where(Event.timestamp >= day_ago)
        )

        # By tool
        tool_counts = await self.session.execute(
            select(Event.tool_name, func.count(Event.id))
            .where(Event.tool_name.isnot(None))
            .group_by(Event.tool_name)
        )
        calls_by_tool = {name: count for name, count in tool_counts.all() if name}

        block_counts = await self.session.execute(
            select(Event.tool_name, func.count(Event.id))
            .where(Event.tool_name.isnot(None), Event.decision == "block")
            .group_by(Event.tool_name)
        )
        blocks_by_tool = {name: count for name, count in block_counts.all() if name}

        return MetricsResponse(
            total_sessions=total_sessions or 0,
            total_events=total_events or 0,
            total_tool_calls=total_tool_calls or 0,
            total_blocked=total_blocked or 0,
            total_tokens=int(total_tokens or 0),
            total_cost_usd=float(total_cost or 0.0),
            tokens_last_hour=int(tokens_last_hour or 0),
            tokens_last_24h=int(tokens_last_24h or 0),
            cost_last_hour=float(cost_last_hour or 0.0),
            cost_last_24h=float(cost_last_24h or 0.0),
            calls_by_tool=calls_by_tool,
            blocks_by_tool=blocks_by_tool,
        )

    # Import state management

    async def get_import_position(self, file_path: str) -> int:
        """Get last import byte position for a file."""
        result = await self.session.execute(
            select(ImportState.last_position).where(ImportState.file_path == file_path)
        )
        position = result.scalar_one_or_none()
        return position or 0

    async def set_import_position(self, file_path: str, position: int) -> None:
        """Set last import byte position for a file."""
        result = await self.session.execute(
            select(ImportState).where(ImportState.file_path == file_path)
        )
        state = result.scalar_one_or_none()

        if state is None:
            state = ImportState(
                file_path=file_path,
                last_position=position,
                last_import_at=datetime.now(UTC),
            )
            self.session.add(state)
        else:
            state.last_position = position
            state.last_import_at = datetime.now(UTC)
