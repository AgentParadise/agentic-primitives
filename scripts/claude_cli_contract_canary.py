#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["agentic-isolation"]
#
# [tool.uv.sources]
# agentic-isolation = { path = "../lib/python/agentic_isolation", editable = true }
# ///
"""Harness output-contract canary for the Claude CLI stream-json parser.

`agentic_isolation.providers.claude_cli.event_parser.EventParser` normalizes
`claude --output-format stream-json` output. That stream is NOT a contract --
it is an observation of current CLI behaviour Anthropic can change at any
release. It already did once: the CLI renamed its subagent tool from "Task"
to "Agent", the parser kept a hardcoded `== "Task"` check, and every subagent
was silently downgraded to an ordinary tool call with zero errors anywhere.

This script runs a REAL `claude` CLI invocation and asserts that the pieces
event_parser.py actually depends on are still present and shaped as expected.
Empirically enumerated by reading event_parser.py (see PR description for the
full list); summarized:

  - Top-level stream event types: system, assistant, user, result
    (event_parser.py's dispatch table -- imported here as
    `KNOWN_STREAM_EVENT_TYPES`, not re-typed, so this script can't drift from
    the parser the way the old hardcoded "Task" check drifted from the enum).
  - assistant.message.content[].{type=="tool_use", id, name, input}
  - assistant.message.usage.{input_tokens, output_tokens,
    cache_creation_input_tokens, cache_read_input_tokens}
  - user.message.content[].{type=="tool_result", tool_use_id, is_error}
  - result.{is_error, total_cost_usd, duration_ms, duration_api_ms, num_turns,
    usage}
  - Subagent tool names: must be a member of ClaudeToolName ("Agent" or the
    legacy "Task") -- imported from the real types module, not hand-listed.
  - system/init's `tools` field must include a ClaudeToolName member. This is
    checked BEFORE authentication matters at all: `tools` is emitted before
    the first model turn, so this specific check runs even against an
    unauthenticated CLI (verified in the sandbox this script was authored in,
    which had no credentials -- see PR description).

Unlike event_parser.py itself (which silently drops anything it doesn't
recognize -- that silent-drop is exactly what let the Task/Agent bug live
unnoticed), this script treats every unrecognized event type or tool name as
a hard failure.

Requirements to actually run this (NOT satisfiable in a sandboxed CI runner
without credentials):
  - A real, authenticated `claude` CLI on PATH.
  - Network access to the Anthropic API.

This is a self-contained `uv run` script (PEP 723 inline metadata below pulls
in agentic_isolation as an editable path dependency, so it always imports the
in-repo source, not a stale published version) -- run it with plain
`uv run scripts/claude_cli_contract_canary.py`, or via `just
canary-claude-cli-contract`.

This could not be exercised end-to-end in the workspace that authored it: a
nested `claude` invocation there reported `authentication_failed` /
`apiKeySource: none`, and `/login` was disabled. This script is written to be
run by a human, or a differently-provisioned CI runner, with real credentials.

Usage:
    uv run scripts/claude_cli_contract_canary.py [--model MODEL] [--prompt PROMPT]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

from agentic_isolation.providers.claude_cli.event_parser import (
    KNOWN_STREAM_EVENT_TYPES,
    EventParser,
)
from agentic_isolation.providers.claude_cli.types import ClaudeToolName

DEFAULT_PROMPT = (
    "You MUST use the Task tool (a subagent) to delegate this exact subtask: "
    "run the shell command `echo canary-subagent` and report back its output. "
    "Do not run the command yourself -- delegate it to a subagent via the "
    "Task tool. This is a test of subagent delegation, not a request to save "
    "time."
)

# Fields the parser actually reads off each event type (see event_parser.py's
# _handle_system / _handle_assistant / _handle_user / _handle_result). A
# missing field here doesn't crash the parser (it uses .get() with defaults
# everywhere), but it silently degrades output the same way the tool-name bug
# did, so the canary treats absence as a contract violation, not a shrug.
REQUIRED_TOP_LEVEL_FIELDS: dict[str, tuple[str, ...]] = {
    "system": (),
    "assistant": ("message",),
    "user": ("message",),
    "result": ("is_error", "total_cost_usd", "duration_ms", "duration_api_ms", "num_turns"),
}

REQUIRED_TOOL_USE_FIELDS = ("id", "name", "input")
REQUIRED_TOOL_RESULT_FIELDS = ("tool_use_id",)


class ContractViolation(RuntimeError):
    """Raised when the live CLI output no longer matches what the parser depends on."""


def _fail(message: str) -> None:
    raise ContractViolation(message)


def run_claude(model: str, prompt: str, max_turns: int) -> list[str]:
    """Invoke the real claude CLI and return its stream-json lines."""
    if shutil.which("claude") is None:
        _fail("`claude` CLI not found on PATH -- this canary requires the real CLI.")

    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        model,
        "--max-turns",
        str(max_turns),
        "--allowedTools",
        "Bash,Task,Agent",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        _fail(f"`claude` produced no stdout.\nstderr:\n{result.stderr}")
    return lines


def check_contract(raw_lines: list[str]) -> None:
    """Assert the live stream matches what event_parser.py depends on.

    Also feeds every line through the REAL EventParser (not a re-implemented
    stand-in) so a regression in subagent detection is caught the same way it
    would show up in production: subagent_count staying at 0.
    """
    parser = EventParser(session_id="canary")
    known_tool_names = {t.value for t in ClaudeToolName}
    seen_types: set[str] = set()
    seen_tool_names: set[str] = set()
    init_tools: list[str] | None = None

    for line in raw_lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue  # non-JSON lines (e.g. plain log noise) aren't part of the contract

        event_type = raw.get("type", "")
        seen_types.add(event_type)

        # The system/init event's "tools" field enumerates every built-in tool
        # name the CLI knows about for this session, independent of whether
        # the model ever calls one. It's emitted before any model turn runs
        # (confirmed: present even when the API call itself then fails
        # authentication), so this check works even without valid credentials
        # -- a much cheaper and more reliable drift signal than waiting for
        # the model to actually delegate to a subagent.
        if event_type == "system" and raw.get("subtype") == "init" and "tools" in raw:
            init_tools = raw["tools"]
            if not (known_tool_names & set(init_tools)):
                _fail(
                    "system/init's declared `tools` list contains NONE of "
                    f"ClaudeToolName {sorted(known_tool_names)}. The CLI's "
                    f"subagent tool has been renamed again. Declared tools: "
                    f"{init_tools}"
                )

        if event_type not in KNOWN_STREAM_EVENT_TYPES:
            _fail(
                f"UNKNOWN top-level stream event type {event_type!r} "
                f"(known: {sorted(KNOWN_STREAM_EVENT_TYPES)}).\n"
                "event_parser.py's parse_line() silently drops unknown types "
                "instead of raising -- that silent-drop is exactly what let "
                "the Task/Agent rename go unnoticed. Full event:\n"
                f"{json.dumps(raw)[:500]}"
            )

        for field in REQUIRED_TOP_LEVEL_FIELDS.get(event_type, ()):
            if field not in raw:
                _fail(f"{event_type!r} event is missing required field {field!r}: {raw}")

        if event_type == "assistant":
            for item in raw.get("message", {}).get("content", []):
                if not (isinstance(item, dict) and item.get("type") == "tool_use"):
                    continue
                for field in REQUIRED_TOOL_USE_FIELDS:
                    if field not in item:
                        _fail(f"tool_use item is missing required field {field!r}: {item}")
                seen_tool_names.add(item["name"])

        if event_type == "user":
            for item in raw.get("message", {}).get("content", []):
                if not (isinstance(item, dict) and item.get("type") == "tool_result"):
                    continue
                for field in REQUIRED_TOOL_RESULT_FIELDS:
                    if field not in item:
                        _fail(f"tool_result item is missing required field {field!r}: {item}")

        parser.parse_line(line)

    summary = parser.get_summary()
    if summary.subagent_count < 1:
        _fail(
            "The REAL EventParser observed ZERO subagent lifecycle events "
            "from a prompt explicitly designed to force one. Either the "
            "model didn't delegate to a subagent (try a different model or "
            "loosen the prompt), or the CLI's subagent tool name has drifted "
            f"outside ClaudeToolName {sorted(known_tool_names)} again. "
            f"Tool names actually observed on the wire: {sorted(seen_tool_names)}"
        )

    print(f"OK: stream event types observed: {sorted(seen_types)}")
    print(f"OK: system/init declared tools included: {sorted(known_tool_names & set(init_tools or []))}")
    print(f"OK: tool names actually invoked: {sorted(seen_tool_names)}")
    print(f"OK: subagent_count = {summary.subagent_count}")
    print(f"OK: subagent_names = {summary.subagent_names}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5-20251001",
        help="Model to use for the canary invocation (default: %(default)s)",
    )
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt forcing subagent use")
    parser.add_argument("--max-turns", type=int, default=6)
    args = parser.parse_args()

    try:
        raw_lines = run_claude(args.model, args.prompt, args.max_turns)
        check_contract(raw_lines)
    except ContractViolation as exc:
        print(f"CONTRACT VIOLATION: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired:
        print("`claude` CLI invocation timed out", file=sys.stderr)
        return 1

    print("Harness output contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
