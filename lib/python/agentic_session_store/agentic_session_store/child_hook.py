"""Bounded native child hook adapter. Run with python -m agentic_session_store.child_hook.

Exit 2 with nonempty stderr explicitly denies a failed pre-tool registration in
Codex 0.156.1. The harness can still fail open if this process cannot start.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from agentic_session_store.child_journal import ChildCall, ChildJournal
from agentic_session_store.codex_child_identity import child_identity, parent_identity
from agentic_session_store.contract import METADATA_NAMESPACE, SessionStoreContract

MAX_HOOK_BYTES = 1024 * 1024


class InvocationEnv(StrEnum):
    INVOCATION_ID = "AGENTIC_INVOCATION_ID"
    ATTEMPT_ID = "AGENTIC_ATTEMPT_ID"


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


def record_child_hook(content: bytes, environment: Mapping[str, str]) -> None:
    contract = SessionStoreContract.from_env(environment)
    if contract is None:
        return
    if len(content) > MAX_HOOK_BYTES:
        raise ValueError("Hook byte limit exceeded")
    event = _parse(content)
    if event.get("tool_name") not in {
        "spawn_agent",
        "collaborationspawn_agent",
        "Agent",
        "Task",
    }:
        return
    kind = event.get("hook_event_name")
    if kind not in {"PreToolUse", "PostToolUse"}:
        raise ValueError("Unsupported child hook event")
    claude = event.get("tool_name") in {"Agent", "Task"}
    parent = _identity(event.get("session_id"))
    if claude and "agent_id" in event:
        parent = _claude_identity(event["agent_id"])
    root = None
    if event.get("tool_name") == "collaborationspawn_agent":
        parent, root = parent_identity(event, environment)
    call = ChildCall(
        invocation_id=_identity(environment.get(InvocationEnv.INVOCATION_ID)),
        attempt_id=_identity(environment.get(InvocationEnv.ATTEMPT_ID)),
        harness="claude" if claude else "codex",
        parent_native_id=_identity(parent),
        tool_call_id=_identity(event.get("tool_use_id")),
    )
    # Init owns the retained partition. A missing directory is an error, not a
    # reason to create a new ephemeral location and claim durable registration.
    path = (
        Path(contract.spool)
        / METADATA_NAMESPACE
        / contract.partition
        / "children.sqlite"
    )
    journal = ChildJournal(path)
    if kind == "PreToolUse":
        journal.register(call)
        return
    response = event.get("tool_response")
    if claude:
        if not isinstance(response, dict):
            raise TypeError("Unsupported Agent response")
        journal.bind(call, _claude_identity(response.get("agentId")))
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
    journal.bind(call, child)


def main() -> int:
    try:
        record_child_hook(sys.stdin.buffer.read(MAX_HOOK_BYTES + 1), os.environ)
    except (
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
        OSError,
        sqlite3.Error,
    ):
        # Never emit payload, prompt, path, environment or database error text.
        print("Durable child-session recording failed.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
