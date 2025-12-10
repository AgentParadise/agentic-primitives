#!/usr/bin/env python3
"""
Notification Handler - Logs various notifications.

This handler:
1. Receives Notification events from Claude
2. Logs notification events for analytics
3. Always allows (no blocking on notifications)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def log_analytics(event: dict[str, Any]) -> None:
    """Log to analytics file. Fail-safe - never blocks."""
    try:
        path = Path(os.getenv("ANALYTICS_PATH", ".agentic/analytics/events.jsonl"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(
                json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), **event}) + "\n"
            )
    except Exception:
        pass


def main() -> None:
    """Main entry point."""
    try:
        input_data = ""
        if not sys.stdin.isatty():
            input_data = sys.stdin.read()

        if not input_data:
            return  # No response needed for non-blocking events

        event = json.loads(input_data)

        # Get content preview (first 200 bytes, safely truncated for UTF-8)
        message = event.get("message", "")
        content_preview = (
            message.encode("utf-8")[:200].decode("utf-8", errors="ignore")
            if message
            else ""
        )

        log_analytics(
            {
                "event_type": "notification_sent",
                "handler": "notification",
                "hook_event": event.get("hook_event_name", "Notification"),
                "session_id": event.get("session_id"),
                "notification_type": event.get(
                    "matcher"
                ),  # permission_prompt, idle_prompt, error, warning
                "content_preview": content_preview,
                "audit": {
                    "transcript_path": event.get("transcript_path"),
                    "cwd": event.get("cwd"),
                },
            }
        )

    except Exception:
        pass  # Silent fail - notification events don't block


if __name__ == "__main__":
    main()
