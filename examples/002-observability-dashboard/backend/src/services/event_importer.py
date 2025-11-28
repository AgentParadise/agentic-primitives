"""Event importer - reads JSONL file and imports to SQLite."""

import asyncio
import json
import logging
from datetime import datetime

from ..config import get_events_jsonl_path, settings
from ..db.database import async_session_maker
from ..db.repository import SQLiteEventRepository
from ..models.events import AgentEvent, AuditContext

logger = logging.getLogger(__name__)


class EventImporter:
    """Imports events from JSONL file into SQLite database."""

    def __init__(self):
        self.running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the background import task."""
        if self.running:
            return

        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Event importer started")

    async def stop(self) -> None:
        """Stop the background import task."""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Event importer stopped")

    async def _run_loop(self) -> None:
        """Main import loop."""
        while self.running:
            try:
                await self._import_new_events()
            except Exception as e:
                logger.error(f"Import error: {e}")

            await asyncio.sleep(settings.poll_interval)

    async def _import_new_events(self) -> None:
        """Import new events from JSONL file."""
        jsonl_path = get_events_jsonl_path()

        if not jsonl_path.exists():
            return

        async with async_session_maker() as session:
            repo = SQLiteEventRepository(session)

            # Get last read position
            file_path_str = str(jsonl_path)
            last_position = await repo.get_import_position(file_path_str)

            # Read new lines
            file_size = jsonl_path.stat().st_size
            if file_size <= last_position:
                return  # No new data

            with jsonl_path.open() as f:
                f.seek(last_position)
                new_content = f.read()
                new_position = f.tell()

            # Parse and import events
            imported_count = 0
            for line in new_content.strip().split("\n"):
                if not line.strip():
                    continue

                try:
                    raw_event = json.loads(line)
                    event = self._parse_event(raw_event)
                    if event:
                        await repo.append_event(event)
                        imported_count += 1
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON line: {e}")
                except Exception as e:
                    logger.warning(f"Failed to import event: {e}")

            # Update position
            await repo.set_import_position(file_path_str, new_position)
            await session.commit()

            if imported_count > 0:
                logger.info(f"Imported {imported_count} events")

    def _parse_event(self, raw: dict) -> AgentEvent | None:
        """Parse raw JSON into AgentEvent."""
        try:
            # Parse audit context if present
            audit = None
            if "audit" in raw:
                audit = AuditContext(**raw["audit"])

            # Parse timestamp
            timestamp = raw.get("timestamp")
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elif timestamp is None:
                timestamp = datetime.now()

            return AgentEvent(
                timestamp=timestamp,
                event_type=raw.get("event_type", "unknown"),
                handler=raw.get("handler", "unknown"),
                hook_event=raw.get("hook_event"),
                tool_name=raw.get("tool_name"),
                session_id=raw.get("session_id"),
                tool_use_id=raw.get("tool_use_id"),
                audit=audit,
                # TODO: Add token/cost estimation based on model pricing
                estimated_tokens=raw.get("estimated_tokens"),
                estimated_cost_usd=raw.get("estimated_cost_usd"),
            )
        except Exception as e:
            logger.warning(f"Failed to parse event: {e}")
            return None

    async def import_once(self) -> int:
        """Run a single import (for manual trigger). Returns count imported."""
        jsonl_path = get_events_jsonl_path()

        if not jsonl_path.exists():
            return 0

        async with async_session_maker() as session:
            repo = SQLiteEventRepository(session)

            file_path_str = str(jsonl_path)
            last_position = await repo.get_import_position(file_path_str)

            file_size = jsonl_path.stat().st_size
            if file_size <= last_position:
                return 0

            with jsonl_path.open() as f:
                f.seek(last_position)
                new_content = f.read()
                new_position = f.tell()

            imported_count = 0
            for line in new_content.strip().split("\n"):
                if not line.strip():
                    continue

                try:
                    raw_event = json.loads(line)
                    event = self._parse_event(raw_event)
                    if event:
                        await repo.append_event(event)
                        imported_count += 1
                except Exception:
                    pass

            await repo.set_import_position(file_path_str, new_position)
            await session.commit()

            return imported_count
