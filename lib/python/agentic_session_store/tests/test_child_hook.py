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


@pytest.mark.parametrize("nested", [False, True])
def test_v2_binds_exact_native_child_from_task_path(environment, tmp_path, nested):
    home = tmp_path / "home"
    sessions = home / "sessions"
    sessions.mkdir(parents=True)
    environment["CODEX_HOME"] = str(home)
    parent = "nested-parent" if nested else "root"
    parent_file = sessions / "parent.jsonl"
    parent_file.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "payload": {
                    "id": parent,
                    "session_id": "root",
                    "multi_agent_version": "v2",
                },
            }
        )
        + "\n"
    )
    task = "/root/parent/child" if nested else "/root/child"
    event = json.loads(_event("PreToolUse", "v2"))
    event.update(
        tool_name="collaborationspawn_agent",
        session_id="root",
        transcript_path=str(parent_file),
    )
    result = _run(environment, json.dumps(event).encode())
    assert result.returncode == 0, result.stderr
    child = {
        "id": "child",
        "session_id": "root",
        "multi_agent_version": "v2",
        "parent_thread_id": parent,
        "agent_path": task,
    }
    (sessions / "child.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": child})
        + "\n"
        + parent_file.read_text()
    )
    event.update(
        hook_event_name="PostToolUse", tool_response=json.dumps({"task_name": task})
    )
    result = _run(environment, json.dumps(event).encode())
    assert result.returncode == 0, result.stderr
    journal = ChildJournal(
        Path(environment[Env.SPOOL])
        / METADATA_NAMESPACE
        / "run/workspace/children.sqlite"
    )
    call = ChildCall("invocation", "attempt", "codex", parent, "v2")
    assert journal.lookup(call).child_native_id == "child"
    # A second native ID for the same parent/task is ambiguous, never guessed.
    child["id"] = "other-child"
    (sessions / "duplicate.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": child}) + "\n"
    )
    assert _run(environment, json.dumps(event).encode()).returncode == 2


@pytest.mark.parametrize("tool", ["Agent", "Task"])
@pytest.mark.parametrize("nested", [False, True])
def test_claude_native_child_uses_exact_call_and_parent(environment, tool, nested):
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "session_id": "root",
        "tool_use_id": "claude-call",
        "tool_input": {"prompt": "PRIVATE"},
    }
    if nested:
        event["agent_id"] = "parent"
    assert _run(environment, json.dumps(event).encode()).returncode == 0
    event.update(hook_event_name="PostToolUse", tool_response={"agentId": "child"})
    assert _run(environment, json.dumps(event).encode()).returncode == 0
    journal = ChildJournal(
        Path(environment[Env.SPOOL])
        / METADATA_NAMESPACE
        / "run/workspace/children.sqlite"
    )
    changes = journal.page().changes
    assert len(changes) == 2
    assert changes[0].intent.child_native_id is None
    assert changes[1].intent.child_native_id == "agent-child"
    assert changes[1].intent.call.harness == "claude"
    assert changes[1].intent.call.parent_native_id == (
        "agent-parent" if nested else "root"
    )
    # A conflicting identity is recorded as evidence and never replaces the
    # binding; repeating it adds nothing.
    event["tool_response"] = {"agentId": "different-child"}
    for _ in range(2):
        assert _run(environment, json.dumps(event).encode()).returncode == 2
    changes = journal.page().changes
    assert len(changes) == 3
    assert changes[2].conflict_native_id == "agent-different-child"
    assert changes[2].intent.child_native_id == "agent-child"


@pytest.mark.parametrize("response", [None, {}, "agentId: secret", {"agentId": ""}])
def test_claude_invalid_response_keeps_unbound_intent(environment, response):
    event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "session_id": "root",
        "tool_use_id": "call",
    }
    assert _run(environment, json.dumps(event).encode()).returncode == 0
    event.update(hook_event_name="PostToolUse", tool_response=response)
    result = _run(environment, json.dumps(event).encode())
    assert result.returncode == 2
    assert result.stderr == b"Durable child-session recording failed.\n"
    journal = ChildJournal(
        Path(environment[Env.SPOOL])
        / METADATA_NAMESPACE
        / "run/workspace/children.sqlite"
    )
    assert len(journal.page().changes) == 1
