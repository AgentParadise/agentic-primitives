#!/usr/bin/env python3
"""Validate analytics events from JSONL file.

Simple validation to ensure events are properly structured.
"""

import json
import sys
from pathlib import Path


def validate_events(events_path: str = ".agentic/analytics/events.jsonl") -> bool:
    """Validate events in JSONL file.

    Args:
        events_path: Path to events file

    Returns:
        True if all events valid, False otherwise
    """
    path = Path(events_path)

    if not path.exists():
        print(f"No events file found at {events_path}")
        return True

    errors = []
    event_count = 0
    event_types: dict[str, int] = {}

    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                event = json.loads(line)
                event_count += 1

                # Basic structure validation
                if "timestamp" not in event:
                    errors.append(f"Line {line_num}: Missing 'timestamp'")

                if "event_type" not in event:
                    errors.append(f"Line {line_num}: Missing 'event_type'")
                else:
                    et = event["event_type"]
                    event_types[et] = event_types.get(et, 0) + 1

                if "session_id" not in event:
                    errors.append(f"Line {line_num}: Missing 'session_id'")

            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: Invalid JSON - {e}")

    # Print summary
    print(f"Validated {event_count} events")
    print(f"Event types: {event_types}")

    if errors:
        print(f"\n{len(errors)} validation errors:")
        for err in errors[:10]:
            print(f"  - {err}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
        return False

    return True


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate analytics events")
    parser.add_argument(
        "--path",
        default=".agentic/analytics/events.jsonl",
        help="Path to events file",
    )
    args = parser.parse_args()

    if validate_events(args.path):
        print("✓ All events valid")
        return 0
    else:
        print("✗ Validation failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
