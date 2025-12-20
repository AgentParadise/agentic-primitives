#!/usr/bin/env python3
"""Capture agent session recording from container logs.

Zero-overhead recording by capturing container stderr externally.
The agent writes events to stderr as JSONL, this script captures
and converts them to a recording file with timing.

See ADR-030: Session Recording for Testing.

Usage:
    # Pipe from docker logs
    docker logs -f {container} 2>&1 | python capture_recording.py -o recording.jsonl

    # Capture from running container
    python capture_recording.py --container {container_id} -o recording.jsonl

    # Capture from docker run (inline)
    docker run --rm myimage claude -p "task" 2>&1 | python capture_recording.py -o recording.jsonl

Examples:
    # Record a simple session
    docker run --rm agentic-workspace-claude-cli claude -p "What is 2+2?" 2>&1 | \\
        python capture_recording.py -o v1.0.52_claude-3-5-sonnet_math.jsonl

    # Record from a running container
    python capture_recording.py --container my-agent -o session.jsonl --follow
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, TextIO


def is_jsonl_event(line: str) -> bool:
    """Check if a line looks like a JSONL event.

    Supports two formats:
    1. Hook events: {"event_type": "tool_execution_started", ...}
    2. Claude CLI native: {"type": "assistant", ...}
    """
    line = line.strip()
    if not line:
        return False
    if not line.startswith("{"):
        return False
    try:
        data = json.loads(line)
        # Hook events have event_type, Claude CLI has type
        return "event_type" in data or "type" in data
    except json.JSONDecodeError:
        return False


def parse_event(line: str) -> dict | None:
    """Parse a JSONL event line."""
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


def capture_from_stream(
    input_stream: TextIO,
    output_path: Path,
    cli_version: str = "unknown",
    model: str = "unknown",
    task: str = "",
    verbose: bool = False,
) -> int:
    """Capture events from input stream to recording file.

    Args:
        input_stream: Stream to read from (stdin, docker logs, etc)
        output_path: Path to write recording
        cli_version: CLI version for metadata
        model: Model name for metadata
        task: Task description for metadata
        verbose: Print progress

    Returns:
        Number of events captured
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start_time = time.monotonic()
    start_datetime = datetime.now(UTC)
    events: list[dict] = []
    session_id: str | None = None

    if verbose:
        print(f"📹 Capturing to {output_path}...", file=sys.stderr)

    for line in input_stream:
        if not is_jsonl_event(line):
            # Pass through non-event output
            if verbose:
                print(f"  [pass] {line.rstrip()}", file=sys.stderr)
            continue

        event = parse_event(line)
        if event is None:
            continue

        # Add timing offset
        offset_ms = int((time.monotonic() - start_time) * 1000)
        event["_offset_ms"] = offset_ms

        # Capture session_id
        if session_id is None and "session_id" in event:
            session_id = event["session_id"]

        events.append(event)

        if verbose:
            # Support both hook events (event_type) and CLI events (type)
            event_type = event.get("event_type") or event.get("type", "unknown")
            print(f"  [event] {event_type} @ {offset_ms}ms", file=sys.stderr)

    # Calculate duration
    duration_ms = int((time.monotonic() - start_time) * 1000)

    # Write recording with metadata header
    metadata = {
        "_recording": {
            "version": 1,
            "cli_version": cli_version,
            "model": model,
            "provider": "claude",
            "task": task,
            "recorded_at": start_datetime.isoformat(),
            "duration_ms": duration_ms,
            "event_count": len(events),
            "session_id": session_id,
            "capture_method": "container_logs",
        }
    }

    with open(output_path, "w") as f:
        f.write(json.dumps(metadata) + "\n")
        for event in events:
            f.write(json.dumps(event, default=str) + "\n")

    if verbose:
        print(f"✅ Captured {len(events)} events in {duration_ms}ms", file=sys.stderr)
        print(f"   Recording: {output_path}", file=sys.stderr)

    return len(events)


def capture_from_container(
    container: str,
    output_path: Path,
    follow: bool = False,
    cli_version: str = "unknown",
    model: str = "unknown",
    task: str = "",
    verbose: bool = False,
) -> int:
    """Capture events from a Docker container.

    Args:
        container: Container name or ID
        output_path: Path to write recording
        follow: Follow container logs (like tail -f)
        cli_version: CLI version for metadata
        model: Model name for metadata
        task: Task description for metadata
        verbose: Print progress

    Returns:
        Number of events captured
    """
    cmd = ["docker", "logs"]
    if follow:
        cmd.append("-f")
    cmd.append(container)

    if verbose:
        print(f"📹 Capturing from container: {container}", file=sys.stderr)

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        return capture_from_stream(
            proc.stdout,
            output_path,
            cli_version=cli_version,
            model=model,
            task=task,
            verbose=verbose,
        )
    finally:
        proc.terminate()


def generate_filename(cli_version: str, model: str, task_slug: str) -> str:
    """Generate recording filename following naming convention."""
    model_slug = re.sub(r"[^a-zA-Z0-9\-]", "-", model)
    task_slug = re.sub(r"[^a-zA-Z0-9\-]", "-", task_slug)
    return f"v{cli_version}_{model_slug}_{task_slug}.jsonl"


def main():
    parser = argparse.ArgumentParser(
        description="Capture agent session recording from container logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output recording file path",
    )
    parser.add_argument(
        "-c",
        "--container",
        help="Docker container name or ID to capture from",
    )
    parser.add_argument(
        "-f",
        "--follow",
        action="store_true",
        help="Follow container logs (like tail -f)",
    )
    parser.add_argument(
        "--cli-version",
        default="unknown",
        help="Claude CLI version for metadata",
    )
    parser.add_argument(
        "--model",
        default="unknown",
        help="Model name for metadata",
    )
    parser.add_argument(
        "--task",
        default="",
        help="Task description for metadata",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print progress",
    )
    parser.add_argument(
        "--generate-name",
        action="store_true",
        help="Generate filename from cli-version, model, and task",
    )

    args = parser.parse_args()

    # Generate output filename if requested
    if args.generate_name and not args.output:
        task_slug = args.task.replace(" ", "-").lower() or "session"
        filename = generate_filename(args.cli_version, args.model, task_slug)
        args.output = Path("recordings") / filename

    if not args.output:
        parser.error("--output is required (or use --generate-name)")

    # Capture from container or stdin
    if args.container:
        count = capture_from_container(
            container=args.container,
            output_path=args.output,
            follow=args.follow,
            cli_version=args.cli_version,
            model=args.model,
            task=args.task,
            verbose=args.verbose,
        )
    else:
        # Read from stdin (piped docker logs)
        count = capture_from_stream(
            input_stream=sys.stdin,
            output_path=args.output,
            cli_version=args.cli_version,
            model=args.model,
            task=args.task,
            verbose=args.verbose,
        )

    # Exit with error if no events captured
    sys.exit(0 if count > 0 else 1)


if __name__ == "__main__":
    main()

