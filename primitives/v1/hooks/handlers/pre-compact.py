#!/usr/bin/env python3
"""
PreCompact Handler - Logs when context window is about to be compacted.

This handler:
1. Receives PreCompact events from Claude
2. Emits context compacted event to stdout
3. Always allows (no blocking on compact events)

Events are emitted as JSONL to stdout, captured by the agent runner
and stored in TimescaleDB for observability.
"""

import json
import os
import sys

# === EVENT EMITTER (lazy initialized) ===
_emitter = None


def _get_emitter(session_id: str | None = None):
    """Get event emitter, creating if needed."""
    global _emitter
    if _emitter is not None:
        return _emitter

    try:
        from agentic_events import EventEmitter

        _emitter = EventEmitter(
            session_id=session_id or os.getenv("CLAUDE_SESSION_ID", "unknown"),
            provider="claude",
        )
        return _emitter
    except ImportError:
        return None


def main() -> None:
    """Main entry point."""
    try:
        input_data = ""
        if not sys.stdin.isatty():
            input_data = sys.stdin.read()

        if not input_data:
            return

        event = json.loads(input_data)
        session_id = event.get("session_id")

        # Get emitter and emit context compacted event
        emitter = _get_emitter(session_id)
        if emitter:
            # Try to extract token counts from event
            before_tokens = event.get("before_tokens", event.get("current_tokens", 0))
            after_tokens = event.get("after_tokens", event.get("target_tokens", 0))

            if before_tokens or after_tokens:
                emitter.context_compacted(
                    before_tokens=before_tokens,
                    after_tokens=after_tokens,
                )

    except Exception:
        pass  # Silent fail


if __name__ == "__main__":
    main()
