#!/usr/bin/env python3
"""
Analytics Event Normalizer Middleware

Reads hook input from stdin (JSON), normalizes it using provider adapters,
and outputs normalized event to stdout (JSON).

This is a middleware entry point called by the agentic-primitives hook system.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path to import analytics module
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analytics.models.hook_input import HookInput
from analytics.normalizer import EventNormalizer


async def main() -> None:
    """Main entry point for normalizer middleware."""
    try:
        # Read hook input from stdin
        hook_input_json = sys.stdin.read()
        hook_input_dict = json.loads(hook_input_json)

        # Validate with Pydantic
        hook_input = HookInput.model_validate(hook_input_dict)

        # Normalize event (provider is detected from hook_input.provider)
        normalizer = EventNormalizer()
        normalized_event = normalizer.normalize(hook_input)

        # Output normalized event to stdout (JSON)
        output = normalized_event.model_dump_json()
        sys.stdout.write(output)
        sys.stdout.flush()

    except Exception as e:
        # Log error but don't crash (observability middleware is non-blocking)
        sys.stderr.write(f"Analytics normalizer error: {e}\n")
        # Output empty dict to indicate error
        sys.stdout.write("{}")
        sys.stdout.flush()
        sys.exit(0)  # Exit 0 to not block hook pipeline


if __name__ == "__main__":
    asyncio.run(main())
