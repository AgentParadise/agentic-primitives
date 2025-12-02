"""JSONL file storage adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles  # type: ignore[import-untyped]

from hooks_backend.storage.base import Storage

if TYPE_CHECKING:
    from hooks_backend.models import HookEventStored


@dataclass
class JSONLStorage(Storage):
    """JSONL file storage adapter.

    Stores events as JSON Lines (one JSON object per line).
    Suitable for local development and small-scale deployments.

    Attributes:
        path: Path to the JSONL file.
    """

    path: Path = field(default_factory=lambda: Path(".agentic/analytics/events.jsonl"))

    async def store(self, events: list[HookEventStored]) -> int:
        """Store events to JSONL file.

        Args:
            events: List of events to store.

        Returns:
            Number of events stored.
        """
        if not events:
            return 0

        # Ensure parent directory exists
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Convert events to JSON lines
        lines = [json.dumps(event.model_dump(mode="json")) + "\n" for event in events]

        # Append to file (async)
        async with aiofiles.open(self.path, mode="a", encoding="utf-8") as f:
            await f.writelines(lines)

        return len(events)

    async def health_check(self) -> bool:
        """Check if JSONL storage is healthy.

        Returns:
            True if the directory is writable.
        """
        try:
            # Check if we can create/write to parent directory
            self.path.parent.mkdir(parents=True, exist_ok=True)
            return True
        except Exception:
            return False

    @property
    def name(self) -> str:
        """Storage adapter name."""
        return "jsonl"
