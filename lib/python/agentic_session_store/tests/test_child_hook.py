"""Actual hook subprocesses share a durable journal without sharing process state."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_session_store.child_hook import MAX_HOOK_BYTES, InvocationEnv
from agentic_session_store.child_journal import ChildCall, ChildJournal
from agentic_session_store.contract import METADATA_NAMESPACE, Env


@pytest.fixture
def environment(tmp_path: Path) -> dict[str, str]:
    (tmp_path / METADATA_NAMESPACE / "run/workspace").mkdir(parents=True)
    return {
        **os.environ,
        Env.PROVIDER: "local",
        Env.SPOOL: str(tmp_path),
        Env.PARTITION: "run/workspace",
        InvocationEnv.INVOCATION_ID: "invocation",
        InvocationEnv.ATTEMPT_ID: "attempt",
    }


def _run(
    environment: dict[str, str], content: bytes
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "agentic_session_store.child_hook"],
        input=content,
        env=environment,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _event(kind: str, call: str, child: str = "child") -> bytes:
    return json.dumps(
        {
            "hook_event_name": kind,
            "tool_name": "spawn_agent",
            "session_id": "parent",
            "tool_use_id": call,
            "tool_input": {"message": "PRIVATE PROMPT"},
            "tool_response": json.dumps(
                {"agent_id": child, "nickname": "PRIVATE NICKNAME"}
            ),
        }
    ).encode()


def test_hook_processes_register_and_bind_reverse_order(
    environment: dict[str, str],
) -> None:
    for call in ("a", "b"):
        result = _run(environment, _event("PreToolUse", call))
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b"")
    for call in ("b", "a"):
        result = _run(environment, _event("PostToolUse", call, f"child-{call}"))
        assert (result.returncode, result.stdout, result.stderr) == (0, b"", b"")
    path = (
        Path(environment[Env.SPOOL])
        / METADATA_NAMESPACE
        / "run/workspace/children.sqlite"
    )
    journal = ChildJournal(path)
    for call in ("a", "b"):
        assert (
            journal.lookup(
                ChildCall("invocation", "attempt", "codex", "parent", call)
            ).child_native_id
            == f"child-{call}"
        )
    assert b"PRIVATE" not in path.read_bytes()


@pytest.mark.parametrize(
    "failure",
    [
        "missing_context",
        "missing_partition",
        "oversized",
        "duplicate",
        "unregistered_result",
    ],
)
def test_hook_failure_is_explicit_and_redacted(
    environment: dict[str, str], failure: str
) -> None:
    content = _event("PreToolUse", "call")
    if failure == "missing_context":
        environment.pop(InvocationEnv.INVOCATION_ID)
    elif failure == "missing_partition":
        environment[Env.PARTITION] = "missing/PRIVATE"
    elif failure == "oversized":
        content = b" " * (MAX_HOOK_BYTES + 1)
    elif failure == "duplicate":
        content = b'{"tool_name":"spawn_agent","tool_name":"PRIVATE"}'
    else:
        content = _event("PostToolUse", "call")
    result = _run(environment, content)
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == b"Durable child-session recording failed.\n"


def test_disabled_capability_has_no_side_effect(environment: dict[str, str]) -> None:
    environment[Env.PROVIDER] = "none"
    result = _run(environment, b"invalid")
    assert result.returncode == 0
    assert not list(Path(environment[Env.SPOOL]).rglob("*.sqlite"))
