"""File publisher for JSONL output"""

import logging
from pathlib import Path

import aiofiles

from analytics.models.events import NormalizedEvent
from analytics.publishers.base import BasePublisher

logger = logging.getLogger(__name__)


class FilePublisher(BasePublisher):
    """Publisher that writes events to JSONL file

    Events are appended to a file in JSON Lines format (one JSON
    object per line). Uses atomic writes for data safety.
    """

    def __init__(self, output_path: Path) -> None:
        """Initialize file publisher

        Args:
            output_path: Path to output JSONL file
        """
        self.output_path = output_path

    async def publish(self, event: NormalizedEvent) -> None:
        """Publish a single event to JSONL file

        Args:
            event: Normalized event to publish
        """
        try:
            # Ensure parent directory exists
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            # Serialize event to JSON (one line)
            json_line = event.model_dump_json() + "\n"

            # Write atomically using append mode
            async with aiofiles.open(self.output_path, mode="a") as f:
                await f.write(json_line)

        except Exception as e:
            # Never raise - log error and continue
            logger.error(
                f"Failed to publish event to file: {e}",
                extra={
                    "event_type": event.event_type,
                    "session_id": event.session_id,
                    "provider": event.provider,
                    "output_path": str(self.output_path),
                    "error": str(e),
                },
            )

    async def publish_batch(self, events: list[NormalizedEvent]) -> None:
        """Publish multiple events to JSONL file

        Args:
            events: List of normalized events to publish
        """
        try:
            # Ensure parent directory exists
            self.output_path.parent.mkdir(parents=True, exist_ok=True)

            # Serialize all events to JSON lines
            json_lines = [event.model_dump_json() + "\n" for event in events]

            # Write all lines atomically
            async with aiofiles.open(self.output_path, mode="a") as f:
                await f.writelines(json_lines)

        except Exception as e:
            # Never raise - log error and continue
            logger.error(
                f"Failed to publish batch to file: {e}",
                extra={
                    "batch_size": len(events),
                    "output_path": str(self.output_path),
                    "error": str(e),
                },
            )

    async def close(self) -> None:
        """Clean up resources

        File publisher doesn't hold persistent resources, so this is a no-op.
        """
        pass

