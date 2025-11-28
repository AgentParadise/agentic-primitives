#!/usr/bin/env python3
"""
Analytics Event Validation Utilities

Validates that expected hook events were logged to the analytics file.
Useful for testing that self-logging hooks are working correctly.

Usage (CLI):
    python -m agentic_analytics.validation [jsonl_path]
    python -m agentic_analytics.validation .agentic/analytics/events.jsonl
    python -m agentic_analytics.validation --require-hooks bash-validator,file-security

Usage (Python):
    from agentic_analytics.validation import validate, analyze_events, load_events

    events = load_events(Path("events.jsonl"))
    stats = analyze_events(events)
    passed = validate(Path("events.jsonl"), min_events=5)
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EventStats:
    """Statistics from analyzing analytics events."""

    total: int = 0
    by_hook: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_event_type: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_decision: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    by_provider: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    sessions: set[str] = field(default_factory=set)
    hooks: set[str] = field(default_factory=set)
    blocked: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of event validation."""

    passed: bool
    total_events: int
    missing_hooks: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


def load_events(jsonl_path: Path) -> list[dict[str, Any]]:
    """Load events from JSONL file.

    Args:
        jsonl_path: Path to the JSONL events file

    Returns:
        List of event dictionaries

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If a line is invalid JSON
    """
    events = []
    with open(jsonl_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise json.JSONDecodeError(
                        f"Invalid JSON on line {line_num}: {e.msg}",
                        e.doc,
                        e.pos,
                    ) from e
    return events


def analyze_events(events: list[dict[str, Any]]) -> EventStats:
    """Analyze events and return statistics.

    Args:
        events: List of event dictionaries

    Returns:
        EventStats with aggregated statistics
    """
    stats = EventStats(total=len(events))

    for event in events:
        hook_id = event.get("hook_id", "unknown")
        event_type = event.get("event_type", "unknown")
        decision = event.get("decision", "unknown")
        provider = event.get("provider", "unknown")
        session_id = event.get("session_id", "unknown")

        stats.by_hook[hook_id] += 1
        stats.by_event_type[event_type] += 1
        stats.by_decision[decision] += 1
        stats.by_provider[provider] += 1
        stats.sessions.add(session_id)
        stats.hooks.add(hook_id)

        if decision == "block":
            stats.blocked.append(
                {
                    "hook": hook_id,
                    "reason": event.get("reason"),
                    "metadata": event.get("metadata", {}),
                }
            )
        elif decision == "warn":
            stats.warnings.append(
                {
                    "hook": hook_id,
                    "reason": event.get("reason"),
                    "metadata": event.get("metadata", {}),
                }
            )
        elif decision == "error":
            stats.errors.append(
                {
                    "hook": hook_id,
                    "reason": event.get("reason"),
                    "metadata": event.get("metadata", {}),
                }
            )

    return stats


def format_summary(stats: EventStats, verbose: bool = False) -> str:
    """Format event statistics as a string summary.

    Args:
        stats: EventStats to format
        verbose: Include detailed information

    Returns:
        Formatted string summary
    """
    lines = []
    lines.append(f"\n{'=' * 60}")
    lines.append("  📊 Analytics Event Summary")
    lines.append(f"{'=' * 60}")

    lines.append(f"\n  Total Events: {stats.total}")
    lines.append(f"  Sessions: {len(stats.sessions)}")
    lines.append(f"  Hooks: {', '.join(sorted(stats.hooks))}")

    lines.append(f"\n  {'─' * 40}")
    lines.append("  Events by Hook:")
    for hook, count in sorted(stats.by_hook.items()):
        lines.append(f"    {hook}: {count}")

    lines.append(f"\n  {'─' * 40}")
    lines.append("  Events by Type:")
    for event_type, count in sorted(stats.by_event_type.items()):
        lines.append(f"    {event_type}: {count}")

    lines.append(f"\n  {'─' * 40}")
    lines.append("  Decisions:")
    decision_icons = {"allow": "✅", "block": "🛡️", "warn": "⚠️"}
    for decision, count in sorted(stats.by_decision.items()):
        icon = decision_icons.get(decision, "❌")
        lines.append(f"    {icon} {decision}: {count}")

    if stats.blocked:
        lines.append(f"\n  {'─' * 40}")
        lines.append("  🛡️ Blocked Operations:")
        for item in stats.blocked:
            lines.append(f"    - {item['hook']}: {item['reason']}")

    if stats.errors:
        lines.append(f"\n  {'─' * 40}")
        lines.append("  ❌ Errors:")
        for item in stats.errors:
            lines.append(f"    - {item['hook']}: {item['reason']}")

    if stats.warnings and verbose:
        lines.append(f"\n  {'─' * 40}")
        lines.append("  ⚠️ Warnings:")
        for item in stats.warnings:
            lines.append(f"    - {item['hook']}: {item['reason']}")

    return "\n".join(lines)


def validate(
    jsonl_path: Path,
    min_events: int = 1,
    required_hooks: set[str] | None = None,
    verbose: bool = False,
    print_output: bool = True,
) -> ValidationResult:
    """Validate analytics events.

    Args:
        jsonl_path: Path to JSONL file
        min_events: Minimum number of events expected
        required_hooks: Set of hook IDs that must have logged
        verbose: Show detailed output
        print_output: Whether to print to stdout

    Returns:
        ValidationResult with validation details
    """
    result = ValidationResult(passed=True, total_events=0)

    # Check file exists
    if not jsonl_path.exists():
        result.passed = False
        result.errors.append(f"File not found: {jsonl_path}")
        if print_output:
            print(f"\n❌ File not found: {jsonl_path}")
            print("\n   Make sure hooks have been executed and logged events.")
        return result

    # Load events
    try:
        events = load_events(jsonl_path)
    except json.JSONDecodeError as e:
        result.passed = False
        result.errors.append(f"Invalid JSON: {e}")
        if print_output:
            print(f"\n❌ Invalid JSON in file: {e}")
        return result

    if not events:
        result.passed = False
        result.errors.append(f"No events in file: {jsonl_path}")
        if print_output:
            print(f"\n❌ No events in file: {jsonl_path}")
        return result

    # Analyze
    stats = analyze_events(events)
    result.total_events = stats.total

    if print_output:
        print(format_summary(stats, verbose=verbose))

    # Validate
    if print_output:
        print(f"\n{'=' * 60}")
        print("  🧪 Validation Results")
        print(f"{'=' * 60}")

    # Check minimum events
    if stats.total < min_events:
        result.passed = False
        result.errors.append(f"Expected at least {min_events} events, got {stats.total}")
        if print_output:
            print(f"\n  ❌ Expected at least {min_events} events, got {stats.total}")
    elif print_output:
        print(f"\n  ✅ Event count: {stats.total} >= {min_events}")

    # Check required hooks
    if required_hooks:
        missing = required_hooks - stats.hooks
        if missing:
            result.passed = False
            result.missing_hooks = missing
            result.errors.append(f"Missing hooks: {', '.join(sorted(missing))}")
            if print_output:
                print(f"  ❌ Missing hooks: {', '.join(sorted(missing))}")
        elif print_output:
            print(f"  ✅ All required hooks logged: {', '.join(sorted(required_hooks))}")

    # Final result
    if print_output:
        print(f"\n{'=' * 60}")
        if result.passed:
            print("  ✅ VALIDATION PASSED")
        else:
            print("  ❌ VALIDATION FAILED")
        print(f"{'=' * 60}\n")

    return result


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Validate analytics events from hook execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m agentic_analytics.validation
  python -m agentic_analytics.validation .agentic/analytics/events.jsonl
  python -m agentic_analytics.validation --require-hooks bash-validator,file-security
  python -m agentic_analytics.validation --min-events 10 --verbose
        """,
    )
    parser.add_argument(
        "jsonl_path",
        nargs="?",
        default=".agentic/analytics/events.jsonl",
        help="Path to JSONL events file (default: .agentic/analytics/events.jsonl)",
    )
    parser.add_argument(
        "--min-events",
        type=int,
        default=1,
        help="Minimum number of events expected (default: 1)",
    )
    parser.add_argument(
        "--require-hooks",
        type=str,
        default=None,
        help="Comma-separated list of required hook IDs",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed event information",
    )

    args = parser.parse_args()

    jsonl_path = Path(args.jsonl_path)
    required_hooks = set(args.require_hooks.split(",")) if args.require_hooks else None

    result = validate(
        jsonl_path=jsonl_path,
        min_events=args.min_events,
        required_hooks=required_hooks,
        verbose=args.verbose,
    )

    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
