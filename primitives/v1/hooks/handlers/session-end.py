#!/usr/bin/env python3
"""
SessionEnd Handler - Logs when a session ends.

This handler:
1. Receives SessionEnd events from Claude
2. Emits session completed event to stdout
3. Always allows (no blocking on session events)

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
            output=sys.stderr,  # Events to stderr, decision to stdout
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
            return  # No response needed for non-blocking events

        event = json.loads(input_data)
        session_id = event.get("session_id")

        # Get emitter and emit session completed event
        emitter = _get_emitter(session_id)
        if emitter:
            emitter.session_completed(
                reason=event.get("reason", "normal"),
                duration_ms=event.get("duration_ms"),
            )

    except Exception:
        pass  # Silent fail - session events don't block


if __name__ == "__main__":
    main()
