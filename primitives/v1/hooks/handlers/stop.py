#!/usr/bin/env python3
"""
Stop Handler - Logs when agent stops.

This handler:
1. Receives Stop events from Claude
2. Emits agent stopped event to stdout
3. Always allows (no blocking on stop events)

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

        # Get emitter and emit agent stopped event
        emitter = _get_emitter(session_id)
        if emitter:
            emitter.agent_stopped(
                reason=event.get("reason", "normal"),
            )

    except Exception:
        pass  # Silent fail


if __name__ == "__main__":
    main()
