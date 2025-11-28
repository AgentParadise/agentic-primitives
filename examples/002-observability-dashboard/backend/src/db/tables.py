"""SQLAlchemy table definitions."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class Event(Base):
    """Event table storing all hook events."""

    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    handler: Mapped[str] = mapped_column(String(50))
    hook_event: Mapped[str | None] = mapped_column(String(50))

    # Tool context
    tool_name: Mapped[str | None] = mapped_column(String(100), index=True)
    tool_use_id: Mapped[str | None] = mapped_column(String(100))

    # Session context
    session_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # Decision (for hook decisions)
    decision: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)

    # Execution result (for tool executions)
    success: Mapped[bool | None] = mapped_column(Boolean)
    output_preview: Mapped[str | None] = mapped_column(Text)
    input_preview: Mapped[str | None] = mapped_column(Text)

    # Validators
    validators_run: Mapped[str | None] = mapped_column(JSON)  # list[str] as JSON

    # Metrics
    estimated_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)

    # Audit context
    audit_transcript_path: Mapped[str | None] = mapped_column(Text)
    audit_cwd: Mapped[str | None] = mapped_column(Text)
    audit_permission_mode: Mapped[str | None] = mapped_column(String(50))

    # Raw event JSON for extensibility
    raw_event: Mapped[str | None] = mapped_column(JSON)


class Session(Base):
    """Session table for aggregated session data."""

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    model: Mapped[str | None] = mapped_column(String(100))

    # Aggregates (denormalized for fast queries)
    total_events: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    blocked_calls: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class ImportState(Base):
    """Track which events have been imported from JSONL."""

    __tablename__ = "import_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String(500), unique=True)
    last_position: Mapped[int] = mapped_column(Integer, default=0)  # Byte offset
    last_import_at: Mapped[datetime] = mapped_column(DateTime)
