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

    def _extract_input_preview(self, data: dict) -> str | None:
        """Extract meaningful preview from tool input data."""
        if not data:
            return None

        # For Write/Read tools - show file path
        if "file_path" in data:
            return f"file: {data['file_path']}"
        if "path" in data:
            return f"path: {data['path']}"

        # For Bash - show command
        if "command" in data:
            cmd = data["command"]
            return f"$ {cmd[:100]}..." if len(cmd) > 100 else f"$ {cmd}"

        # For search tools
        if "query" in data:
            return f"query: {data['query'][:50]}"

        # For any tool_input dict
        if "tool_input" in data:
            tool_input = data["tool_input"]
            if isinstance(tool_input, dict):
                if "command" in tool_input:
                    cmd = tool_input["command"]
                    return f"$ {cmd[:100]}..." if len(cmd) > 100 else f"$ {cmd}"
                if "file_path" in tool_input:
                    return f"file: {tool_input['file_path']}"
                if "path" in tool_input:
                    return f"path: {tool_input['path']}"

        return None

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

            # Extract nested data fields (from Claude Agent SDK events)
            data = raw.get("data", {})
            event_type = raw.get("event_type") or raw.get("hook_event") or "unknown"

            # Extract tool_name from either top-level or nested data
            tool_name = raw.get("tool_name") or data.get("tool_name")

            # Extract tool input preview (file path, command, etc.)
            input_preview = self._extract_input_preview(data)

            # For session events, show model info as input_preview
            if event_type == "agent_session_start" and data.get("model"):
                model_name = data.get("model_display_name") or data.get("model")
                input_preview = f"model: {model_name}"
            elif event_type == "agent_session_end" and data.get("total_tokens"):
                tokens = data.get("total_tokens", 0)
                cost = data.get("total_cost_usd", 0)
                input_preview = f"tokens: {tokens:,} | cost: ${cost:.4f}"
            elif event_type == "agent_interaction":
                # Show prompt and response preview for interactions
                prompt = data.get("prompt_preview", "")[:50]
                response = data.get("response_preview", "")[:50]
                if prompt and response:
                    input_preview = f'"{prompt}..." → "{response}..."'
                elif prompt:
                    input_preview = f'prompt: "{prompt}..."'

            # Extract tokens and cost from nested data (agent_session_end, agent_interaction)
            estimated_tokens = (
                raw.get("estimated_tokens")
                or data.get("total_tokens")
                or data.get("input_tokens", 0) + data.get("output_tokens", 0)
                or None
            )
            estimated_cost_usd = raw.get("estimated_cost_usd") or data.get("total_cost_usd")

            return AgentEvent(
                timestamp=timestamp,
                event_type=event_type,
                handler=raw.get("handler", "unknown"),
                hook_event=raw.get("hook_event"),
                tool_name=tool_name,
                session_id=raw.get("session_id"),
                tool_use_id=raw.get("tool_use_id"),
                audit=audit,
                estimated_tokens=estimated_tokens if estimated_tokens else None,
                estimated_cost_usd=estimated_cost_usd,
                input_preview=input_preview,
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
