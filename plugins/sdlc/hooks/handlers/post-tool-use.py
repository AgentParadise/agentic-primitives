#!/usr/bin/env python3
"""
PostToolUse Handler - Logs tool execution results for analytics.

This handler:
1. Receives PostToolUse events from Claude
2. Emits tool completion event to stdout
3. Always allows (post-execution, can't block)

Events are emitted as JSONL to stdout, captured by the agent runner
and stored in TimescaleDB for observability.
"""

import json
import os
import sys
from typing import Any

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


def extract_output_preview(tool_response: Any, max_length: int = 500) -> str:
    """Extract a preview of the tool output for logging."""
    if tool_response is None:
        return ""

    if isinstance(tool_response, str):
        output = tool_response
    elif isinstance(tool_response, dict):
        # Try common output fields
        result = (
            tool_response.get("output") or tool_response.get("stdout") or str(tool_response)
        )
        output = str(result)
    else:
        output = str(tool_response)

    if len(output) > max_length:
        return output[:max_length] + "..."
    return output


def main() -> None:
    """Main entry point."""
    try:
        # Read event from stdin
        input_data = ""
        if not sys.stdin.isatty():
            input_data = sys.stdin.read()

        if not input_data:
            return

        event = json.loads(input_data)

        # Extract fields
        tool_name = event.get("tool_name", "")
        tool_response = event.get("tool_response", {})
        session_id = event.get("session_id")
        tool_use_id = event.get("tool_use_id", "unknown")

        # Determine success/failure
        is_error = False
        error_msg = None
        if isinstance(tool_response, dict):
            is_error = tool_response.get("is_error", False) or "error" in tool_response
            if is_error:
                error_msg = str(tool_response.get("error", "Tool execution failed"))

        # Get emitter and emit tool completed event
        emitter = _get_emitter(session_id)
        if emitter:
            emitter.tool_completed(
                tool_name=tool_name,
                tool_use_id=tool_use_id,
                success=not is_error,
                output_preview=extract_output_preview(tool_response),
                error=error_msg,
            )

        # Always allow (post-execution)

    except Exception as e:
        # Fail open


if __name__ == "__main__":
    main()
