#!/usr/bin/env python3
"""
SessionStart Handler - Logs when a session starts.

This handler:
1. Receives SessionStart events from Claude
2. Emits session started event to stdout
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

        # Get emitter and emit session started event
        emitter = _get_emitter(session_id)
        if emitter:
            # Determine start source from matcher
            source = event.get("matcher", "startup")
            emitter.session_started(
                source=source,
                transcript_path=event.get("transcript_path"),
                cwd=event.get("cwd"),
                permission_mode=event.get("permission_mode"),
            )

    except Exception:
        pass  # Silent fail - session events don't block


if __name__ == "__main__":
    main()
