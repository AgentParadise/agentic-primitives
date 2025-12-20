#!/usr/bin/env python3
"""
UserPrompt Handler - Logs when user submits a prompt.

This handler:
1. Receives UserPromptSubmit events from Claude
2. Emits prompt submitted event to stdout
3. Always allows (no blocking on prompt events)

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
            # Always allow even with no input
            print(json.dumps({"decision": "allow"}))
            return

        event = json.loads(input_data)
        session_id = event.get("session_id")

        # Get emitter and emit prompt submitted event
        emitter = _get_emitter(session_id)
        if emitter:
            # Get prompt preview (truncated for privacy)
            prompt = event.get("prompt", event.get("message", ""))
            emitter.prompt_submitted(prompt_preview=prompt[:200] if prompt else "")

    except Exception:
        pass  # Silent fail


if __name__ == "__main__":
    main()
