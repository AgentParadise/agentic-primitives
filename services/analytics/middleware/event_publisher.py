#!/usr/bin/env python3
"""
Analytics Event Publisher Middleware

Reads normalized event from stdin (JSON), publishes to configured backend
(file or API), and exits.

This is a middleware entry point called by the agentic-primitives hook system.
"""
import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path to import analytics module
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analytics.models.events import NormalizedEvent
from analytics.models.config import AnalyticsConfig

# TODO(Agent A): Import publishers when implemented
try:
    from analytics.publishers.file import FilePublisher
    from analytics.publishers.api import APIPublisher
except ImportError:
    # Placeholder until Agent A implements publishers
    class FilePublisher:  # type: ignore
        def __init__(self, output_path: Path):
            self.output_path = output_path
        
        async def publish(self, event: NormalizedEvent) -> None:
            # FIXME: This is a stub - Agent A needs to implement the actual file publisher
            pass
        
        async def close(self) -> None:
            pass
    
    class APIPublisher:  # type: ignore
        def __init__(self, endpoint: str, timeout: int = 30, retry_attempts: int = 3):
            self.endpoint = endpoint
            self.timeout = timeout
            self.retry_attempts = retry_attempts
        
        async def publish(self, event: NormalizedEvent) -> None:
            # FIXME: This is a stub - Agent A needs to implement the actual API publisher
            pass
        
        async def close(self) -> None:
            pass


async def main() -> None:
    """Main entry point for publisher middleware."""
    try:
        # Read normalized event from stdin
        event_json = sys.stdin.read()
        
        # Handle empty input (from normalizer error)
        if not event_json or event_json.strip() == "{}":
            sys.exit(0)
        
        event_dict = json.loads(event_json)
        
        # Validate with Pydantic
        normalized_event = NormalizedEvent.model_validate(event_dict)
        
        # Load configuration from environment
        config = AnalyticsConfig()
        
        # Select publisher backend
        if config.publisher_backend == "file":
            if not config.output_path:
                raise ValueError("output_path required for file backend")
            publisher = FilePublisher(output_path=config.output_path)
        elif config.publisher_backend == "api":
            if not config.api_endpoint:
                raise ValueError("api_endpoint required for API backend")
            publisher = APIPublisher(
                endpoint=config.api_endpoint,
                timeout=config.api_timeout,
                retry_attempts=config.retry_attempts,
            )
        else:
            raise ValueError(f"Unknown publisher backend: {config.publisher_backend}")
        
        # Publish event
        await publisher.publish(normalized_event)
        await publisher.close()
        
    except Exception as e:
        # Log error but don't crash (observability middleware is non-blocking)
        sys.stderr.write(f"Analytics publisher error: {e}\n")
        sys.exit(0)  # Exit 0 to not block hook pipeline


if __name__ == "__main__":
    asyncio.run(main())

