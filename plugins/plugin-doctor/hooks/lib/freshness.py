"""
Pure functions for plugin-doctor: state I/O, cadence gating, semver
comparison, and outdated-plugin context formatting.

No I/O side effects except read_state/write_state, which take explicit
paths so callers (and tests) control where state lives. No subprocess
calls anywhere in this module — the marketplace refresh subprocess call
lives in session-start.py, not here.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def read_state(state_path: Path) -> dict:
    """Read the state file, returning {} if missing or malformed."""
    try:
        data = json.loads(state_path.read_text())
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state_path: Path, state: dict) -> None:
    """Write the state file, creating parent directories as needed."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state))


def is_check_due(
    last_checked_at: str | None, now: datetime, interval_days: int = 7
) -> bool:
    """True if a refresh is due: no valid last_checked_at, or it's at
    least interval_days old."""
    if not last_checked_at:
        return True
    try:
        last = datetime.fromisoformat(last_checked_at)
    except (ValueError, TypeError):
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return now - last >= timedelta(days=interval_days)
