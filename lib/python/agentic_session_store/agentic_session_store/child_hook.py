"""Bounded native child hook adapter. Run with python -m agentic_session_store.child_hook.

Installed behind ``hook_command.guarded_command``, which turns every failure
of this process (including it never starting) into the configured hook status.
A PreToolUse failure exits 2, which denies the launch in both pinned harnesses
(Claude Code 2.1.281 and Codex 0.156.1). Other events never block.

Events handled, per harness:

* PreToolUse (Agent/Task; spawn_agent/collaborationspawn_agent): commit intent.
* PostToolUse (same tools): launched, bound to the returned child, in one commit.
* PostToolUseFailure (Claude only; Codex fires no hook for a failed tool):
  launch_failed, never bound.
* SubagentStop (both): the child stopped; settles its launched intent.
* AgenticCaptureProbe: no journal write; proves the guard, interpreter,
  package, active contract and journal schema are all reachable.

Installed hooks require an active session-store contract. Capture hooks are
only installed when capture is enabled, so a missing or ``none`` provider at
hook time means the hook environment lost it, and the launch is denied.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import FrameType

from agentic_session_store.child_journal import (
    ChildCall,
    ChildJournal,
    LaunchFailureReason,
)
from agentic_session_store.codex_child_identity import child_identity, parent_identity
from agentic_session_store.contract import METADATA_NAMESPACE, SessionStoreContract
from agentic_session_store.hook_command import (
    FAILURE_MESSAGE,
    RECORDER_DEADLINE_SECONDS,
    HookHarness,
)

MAX_HOOK_BYTES = 1024 * 1024
CLAUDE_TOOLS = frozenset({"Agent", "Task"})
CODEX_TOOLS = frozenset({"spawn_agent", "collaborationspawn_agent"})
# Best-effort launch_failed after a denial must not outlive the shell watchdog.
BEST_EFFORT_BUSY_SECONDS = 1


class InvocationEnv(StrEnum):
    INVOCATION_ID = "AGENTIC_INVOCATION_ID"
    ATTEMPT_ID = "AGENTIC_ATTEMPT_ID"


class HookEvent(StrEnum):
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    SUBAGENT_STOP = "SubagentStop"
    CAPTURE_PROBE = "AgenticCaptureProbe"


class _WatchdogTerminated(Exception):
    """The guard's watchdog sent SIGTERM."""


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate hook field")
        result[key] = value
    return result


def _parse(content: bytes | str) -> dict[str, object]:
    value = json.loads(content, object_pairs_hook=_object)
    if not isinstance(value, dict):
        raise TypeError("Hook must be an object")
    return value


def _identity(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode()) > 2048
        or "\x00" in value
    ):
        raise ValueError("Missing or invalid hook identity")
    return value


def _claude_identity(value: object) -> str:
    native = _identity(value)
    return native if native.startswith("agent-") else "agent-" + native


@dataclass(frozen=True)
class _Pending:
    """The intent a PreToolUse hook is committing, kept for a failure record."""

    journal_path: Path
    call: ChildCall


def _journal_path(contract: SessionStoreContract) -> Path:
    # Init owns the retained partition. A missing directory is an error, not a
    # reason to create a new ephemeral location and claim durable registration.
    return (
        Path(contract.spool)
        / METADATA_NAMESPACE
        / contract.partition
        / "children.sqlite"
    )


def record_child_hook(
    content: bytes,
    environment: Mapping[str, str],
    harness: HookHarness | None = None,
    pending: list[_Pending] | None = None,
) -> None:
    contract = SessionStoreContract.from_env(environment)
    if contract is None:
        raise ValueError("Capture hook installed without an active contract")
    if len(content) > MAX_HOOK_BYTES:
        raise ValueError("Hook byte limit exceeded")
    event = _parse(content)
    kind = event.get("hook_event_name")
    if kind == HookEvent.CAPTURE_PROBE:
        ChildJournal(_journal_path(contract))
        return
    if kind == HookEvent.SUBAGENT_STOP:
        if harness is None:
            raise ValueError("SubagentStop requires an explicit harness")
        child = (
            _claude_identity(event.get("agent_id"))
            if harness is HookHarness.CLAUDE
            else _identity(event.get("agent_id"))
        )
        ChildJournal(_journal_path(contract)).observe_stop(
            _identity(environment.get(InvocationEnv.INVOCATION_ID)),
            _identity(environment.get(InvocationEnv.ATTEMPT_ID)),
            harness.value,
            child,
        )
        return
    tool = event.get("tool_name")
    if tool not in CLAUDE_TOOLS | CODEX_TOOLS:
        return
    claude = tool in CLAUDE_TOOLS
    if harness is not None and (harness is HookHarness.CLAUDE) != claude:
        raise ValueError("Hook harness does not match its tool")
    if kind not in {
        HookEvent.PRE_TOOL_USE,
        HookEvent.POST_TOOL_USE,
        HookEvent.POST_TOOL_USE_FAILURE,
    } or (kind == HookEvent.POST_TOOL_USE_FAILURE and not claude):
        raise ValueError("Unsupported child hook event")
    parent = _identity(event.get("session_id"))
    if claude and "agent_id" in event:
        parent = _claude_identity(event["agent_id"])
    root = None
    if tool == "collaborationspawn_agent":
        parent, root = parent_identity(event, environment)
    call = ChildCall(
        invocation_id=_identity(environment.get(InvocationEnv.INVOCATION_ID)),
        attempt_id=_identity(environment.get(InvocationEnv.ATTEMPT_ID)),
        harness="claude" if claude else "codex",
        parent_native_id=_identity(parent),
        tool_call_id=_identity(event.get("tool_use_id")),
    )
    path = _journal_path(contract)
    if kind == HookEvent.PRE_TOOL_USE:
        # Recorded before the commit: a watchdog signal can arrive between the
        # commit and the return. A denial record only ever moves a pending
        # intent, so an uncommitted one is left alone.
        if pending is not None:
            pending.append(_Pending(path, call))
        ChildJournal(path).register(call, pending=True)
        return
    journal = ChildJournal(path)
    if kind == HookEvent.POST_TOOL_USE_FAILURE:
        journal.observe_launch_failure(
            call,
            LaunchFailureReason.NATIVE_TOOL_INTERRUPTED
            if event.get("is_interrupt") is True
            else LaunchFailureReason.NATIVE_TOOL_FAILED,
        )
        return
    response = event.get("tool_response")
    if claude:
        if not isinstance(response, dict):
            raise TypeError("Unsupported Agent response")
        # 2.1.281 reports "async_launched" for a background child and
        # "completed" for one that already ran to completion.
        journal.observe_launch(
            call,
            _claude_identity(response.get("agentId")),
            stopped=response.get("status") == "completed",
        )
        return
    # Codex serializes the model-facing FunctionCallOutput body as a JSON string.
    if not isinstance(response, str):
        raise TypeError("Unsupported spawn response")
    result = _parse(response)
    child = _identity(
        child_identity(root, parent, result.get("task_name"))
        if root is not None
        else result.get("agent_id")
    )
    journal.observe_launch(call, child)


def _deadline(_signum: int, _frame: FrameType | None) -> None:
    raise TimeoutError("Child hook deadline exceeded")


def _terminated(_signum: int, _frame: FrameType | None) -> None:
    raise _WatchdogTerminated


def _record_denial(pending: Sequence[_Pending], reason: LaunchFailureReason) -> None:
    """Best effort: mark an intent committed before a denial as launch_failed."""
    for item in pending:
        try:
            ChildJournal(
                item.journal_path, busy_timeout=BEST_EFFORT_BUSY_SECONDS
            ).observe_launch_failure(item.call, reason)
        except (ValueError, TypeError, OSError, sqlite3.Error):
            # No intent (or no journal): the launch is denied with nothing to mark.
            pass


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--harness", choices=[h.value for h in HookHarness])
    args = parser.parse_args(argv)
    harness = None if args.harness is None else HookHarness(args.harness)
    pending: list[_Pending] = []
    signal.signal(signal.SIGALRM, _deadline)
    signal.signal(signal.SIGTERM, _terminated)
    signal.alarm(RECORDER_DEADLINE_SECONDS)
    try:
        record_child_hook(
            sys.stdin.buffer.read(MAX_HOOK_BYTES + 1), os.environ, harness, pending
        )
    except _WatchdogTerminated:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.alarm(0)
        _record_denial(pending, LaunchFailureReason.HOOK_WATCHDOG)
        print(FAILURE_MESSAGE, file=sys.stderr)
        return 2
    except (
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
        OSError,
        sqlite3.Error,
    ):
        signal.alarm(0)
        _record_denial(pending, LaunchFailureReason.CAPTURE_HOOK_FAILED)
        # Never emit payload, prompt, path, environment or database error text.
        print(FAILURE_MESSAGE, file=sys.stderr)
        return 2
    finally:
        signal.alarm(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
