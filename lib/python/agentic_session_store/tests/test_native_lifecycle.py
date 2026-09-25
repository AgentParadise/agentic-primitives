"""Native child lifecycle and the fail-closed hook guard (syntropic137#1398).

The guard is exercised through /bin/sh exactly as both pinned harnesses run
hook commands, with PATH controlled so a missing or hung interpreter is real.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentic_session_store.child_export import export_page
from agentic_session_store.child_hook import InvocationEnv
from agentic_session_store.child_journal import (
    ChildBindingConflict,
    ChildCall,
    ChildJournal,
    LaunchFailureReason,
)
from agentic_session_store.contract import METADATA_NAMESPACE, Env
from agentic_session_store.hook_command import (
    FAILURE_MESSAGE,
    HARNESS_TIMEOUT_SECONDS,
    HookHarness,
    guarded_command,
)

SLEEP = shutil.which("sleep")
CALL = ChildCall("invocation", "attempt", "claude", "root", "call")


@pytest.fixture
def journal(tmp_path: Path) -> ChildJournal:
    return ChildJournal(tmp_path / "children.sqlite")


def _statuses(journal: ChildJournal) -> list[tuple[str | None, str | None, str | None]]:
    return [
        (c.intent.status, c.intent.child_native_id, c.conflict_native_id)
        for c in journal.page().changes
    ]


# --- Journal lifecycle -------------------------------------------------------


def test_launch_then_stop_is_idempotent(journal: ChildJournal) -> None:
    for _ in range(2):
        journal.register(CALL)
        journal.observe_launch(CALL, "agent-child")
    for _ in range(2):
        assert journal.observe_stop(
            "invocation", "attempt", "claude", "agent-child"
        ) in {
            0,
            1,
        }
    journal.observe_launch(CALL, "agent-child")
    assert _statuses(journal) == [
        (None, None, None),
        ("launched", "agent-child", None),
        ("completed", "agent-child", None),
    ]
    intent = journal.lookup(CALL)
    assert (intent.status, intent.exit_code) == ("completed", None)


def test_stop_before_launch_ack_settles_on_binding(journal: ChildJournal) -> None:
    """A stop carries only the child's ID; it never creates a binding."""
    journal.register(CALL)
    assert journal.observe_stop("invocation", "attempt", "claude", "agent-child") == 0
    assert journal.lookup(CALL).child_native_id is None
    journal.observe_launch(CALL, "agent-child")
    assert _statuses(journal)[1:] == [
        ("launched", "agent-child", None),
        ("completed", "agent-child", None),
    ]


def test_stop_scoped_to_invocation_attempt_and_harness(journal: ChildJournal) -> None:
    journal.register(CALL)
    journal.observe_launch(CALL, "agent-child")
    for invocation, attempt, harness in (
        ("other", "attempt", "claude"),
        ("invocation", "other", "claude"),
        ("invocation", "attempt", "codex"),
    ):
        assert journal.observe_stop(invocation, attempt, harness, "agent-child") == 0
    assert journal.lookup(CALL).status == "launched"


def test_synchronous_result_launches_and_completes(journal: ChildJournal) -> None:
    journal.register(CALL)
    journal.observe_launch(CALL, "agent-child", stopped=True)
    assert [s for s, _, _ in _statuses(journal)] == [None, "launched", "completed"]


def test_conflicting_child_is_recorded_once_and_never_applied(
    journal: ChildJournal,
) -> None:
    journal.register(CALL)
    journal.observe_launch(CALL, "agent-child")
    for _ in range(2):
        with pytest.raises(ChildBindingConflict):
            journal.observe_launch(CALL, "agent-other")
    with pytest.raises(ChildBindingConflict):
        journal.bind(CALL, "agent-other")
    assert journal.lookup(CALL).child_native_id == "agent-child"
    assert _statuses(journal)[-1] == ("launched", "agent-child", "agent-other")
    assert len(journal.page().changes) == 3
    # A second distinct conflict is its own observation.
    with pytest.raises(ChildBindingConflict):
        journal.observe_launch(CALL, "agent-third")
    assert _statuses(journal)[-1] == ("launched", "agent-child", "agent-third")


def test_launch_failure_is_distinct_and_idempotent(journal: ChildJournal) -> None:
    journal.register(CALL)
    for _ in range(2):
        intent = journal.observe_launch_failure(
            CALL, LaunchFailureReason.NATIVE_TOOL_FAILED
        )
    assert (intent.status, intent.reason, intent.child_native_id) == (
        "launch_failed",
        "native_tool_failed",
        None,
    )
    with pytest.raises(ValueError):
        journal.observe_launch(CALL, "agent-child")
    # A stop for some child never touches an unbound failed launch.
    journal.observe_stop("invocation", "attempt", "claude", "agent-child")
    assert journal.lookup(CALL).status == "launch_failed"
    assert len(journal.page().changes) == 2


def test_launched_child_cannot_become_launch_failed(journal: ChildJournal) -> None:
    journal.register(CALL)
    journal.observe_launch(CALL, "agent-child")
    with pytest.raises(ValueError):
        journal.observe_launch_failure(CALL, LaunchFailureReason.NATIVE_TOOL_FAILED)


def test_unregistered_launch_is_never_fabricated(journal: ChildJournal) -> None:
    with pytest.raises(ValueError):
        journal.observe_launch(CALL, "agent-child")
    assert journal.page().changes == ()


def test_native_lifecycle_rejects_delegate_intents(journal: ChildJournal) -> None:
    delegate = ChildCall("invocation", "attempt", "claude", "root", "d", "codex")
    journal.register(delegate)
    with pytest.raises(ValueError):
        journal.observe_launch(delegate, "child")
    with pytest.raises(ValueError):
        journal.observe_launch_failure(delegate, LaunchFailureReason.NATIVE_TOOL_FAILED)


def test_export_uses_v3_only_for_native_lifecycle_and_conflicts(
    journal: ChildJournal,
) -> None:
    journal.register(CALL)
    assert export_page(journal.page())["schema_version"] == 1
    journal.observe_launch(CALL, "agent-child")
    exported = export_page(journal.page())
    assert exported["schema_version"] == 3
    assert "conflict_native_id" not in exported["page"]["changes"][0]
    with pytest.raises(ChildBindingConflict):
        journal.observe_launch(CALL, "agent-other")
    last = export_page(journal.page())["page"]["changes"][-1]
    assert last["conflict_native_id"] == "agent-other"
    assert last["intent"]["child_native_id"] == "agent-child"


def test_upgrade_of_pre_lifecycle_journal_keeps_history(tmp_path: Path) -> None:
    path = tmp_path / "children.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE child_intents (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                child_invocation_id TEXT NOT NULL UNIQUE,
                invocation_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
                harness TEXT NOT NULL, parent_native_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL, child_native_id TEXT,
                UNIQUE (invocation_id, attempt_id, harness, parent_native_id, tool_call_id));
            INSERT INTO child_intents VALUES
                (1, 'id', 'invocation', 'attempt', 'claude', 'root', 'call', NULL);
        """)
    journal = ChildJournal(path)
    journal.observe_launch(CALL, "agent-child")
    assert _statuses(journal) == [(None, None, None), ("launched", "agent-child", None)]


# --- Guarded hook command ----------------------------------------------------


def _bin(tmp_path: Path, python: str | None) -> dict[str, str]:
    """PATH with only sleep and, optionally, a python3 shim."""
    directory = tmp_path / "bin"
    directory.mkdir(exist_ok=True)
    assert SLEEP is not None
    (directory / "sleep").symlink_to(SLEEP)
    if python is not None:
        shim = directory / "python3"
        shim.write_text("#!/bin/sh\n" + python + "\n")
        shim.chmod(0o755)
    return {"PATH": str(directory)}


@pytest.fixture
def environment(tmp_path: Path) -> dict[str, str]:
    (tmp_path / METADATA_NAMESPACE / "run").mkdir(parents=True)
    return {
        "PYTHONPATH": os.pathsep.join(sys.path),
        Env.PROVIDER: "local",
        Env.SPOOL: str(tmp_path),
        Env.PARTITION: "run",
        InvocationEnv.INVOCATION_ID: "invocation",
        InvocationEnv.ATTEMPT_ID: "attempt",
    }


def _journal(environment: dict[str, str]) -> ChildJournal:
    return ChildJournal(
        Path(environment[Env.SPOOL]) / METADATA_NAMESPACE / "run/children.sqlite"
    )


def _hook(
    environment: dict[str, str],
    payload: dict[str, object],
    *,
    harness: HookHarness = HookHarness.CLAUDE,
    deny: bool | None = None,
    watchdog: int = 5,
) -> subprocess.CompletedProcess[bytes]:
    if deny is None:
        deny = payload["hook_event_name"] == "PreToolUse"
    return subprocess.run(
        ["/bin/sh", "-c", guarded_command(harness, deny=deny, watchdog=watchdog)],
        input=json.dumps(payload).encode(),
        env=environment,
        capture_output=True,
        timeout=HARNESS_TIMEOUT_SECONDS,
        check=False,
    )


PYTHON = f'exec "{sys.executable}" "$@"'


def _claude(kind: str, **fields: object) -> dict[str, object]:
    return {
        "hook_event_name": kind,
        "tool_name": "Agent",
        "session_id": "root",
        "tool_use_id": "call",
        "tool_input": {"prompt": "PRIVATE PROMPT"},
        **fields,
    }


def test_guarded_claude_lifecycle_with_duplicate_hooks(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    environment.update(_bin(tmp_path, PYTHON))
    steps = [
        _claude("PreToolUse"),
        _claude(
            "PostToolUse",
            tool_response={"status": "async_launched", "agentId": "abc"},
        ),
        {
            "hook_event_name": "SubagentStop",
            "session_id": "root",
            "agent_id": "abc",
            "last_assistant_message": "PRIVATE",
        },
    ]
    for step in steps:
        for _ in range(2):
            result = _hook(environment, step)
            assert (result.returncode, result.stdout, result.stderr) == (0, b"", b"")
    assert _statuses(_journal(environment)) == [
        (None, None, None),
        ("launched", "agent-abc", None),
        ("completed", "agent-abc", None),
    ]
    assert (
        b"PRIVATE"
        not in (
            Path(environment[Env.SPOOL]) / METADATA_NAMESPACE / "run/children.sqlite"
        ).read_bytes()
    )


def test_guarded_codex_lifecycle(tmp_path: Path, environment: dict[str, str]) -> None:
    environment.update(_bin(tmp_path, PYTHON))
    base = {"tool_name": "spawn_agent", "session_id": "parent", "tool_use_id": "c"}
    for step in (
        {**base, "hook_event_name": "PreToolUse"},
        {
            **base,
            "hook_event_name": "PostToolUse",
            "tool_response": json.dumps({"agent_id": "child-thread"}),
        },
        {
            "hook_event_name": "SubagentStop",
            "session_id": "r",
            "agent_id": "child-thread",
        },
    ):
        result = _hook(environment, step, harness=HookHarness.CODEX)
        assert result.returncode == 0, result.stderr
    intent = _journal(environment).lookup(
        ChildCall("invocation", "attempt", "codex", "parent", "c")
    )
    assert (intent.status, intent.child_native_id) == ("completed", "child-thread")


@pytest.mark.parametrize("interrupted", [False, True])
def test_claude_tool_failure_is_a_distinct_failed_launch(
    tmp_path: Path, environment: dict[str, str], interrupted: bool
) -> None:
    environment.update(_bin(tmp_path, PYTHON))
    assert _hook(environment, _claude("PreToolUse")).returncode == 0
    failure = _claude("PostToolUseFailure", error="PRIVATE", is_interrupt=interrupted)
    for _ in range(2):
        assert _hook(environment, failure).returncode == 0
    intent = _journal(environment).lookup(CALL)
    assert (intent.status, intent.child_native_id, intent.reason) == (
        "launch_failed",
        None,
        "native_tool_interrupted" if interrupted else "native_tool_failed",
    )


def test_guarded_conflict_is_recorded_and_reported_without_blocking(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    environment.update(_bin(tmp_path, PYTHON))
    _hook(environment, _claude("PreToolUse"))
    _hook(environment, _claude("PostToolUse", tool_response={"agentId": "a"}))
    result = _hook(environment, _claude("PostToolUse", tool_response={"agentId": "b"}))
    assert (result.returncode, result.stderr) == (1, FAILURE_MESSAGE.encode() + b"\n")
    assert _statuses(_journal(environment))[-1] == ("launched", "agent-a", "agent-b")


def test_missing_interpreter_denies_launch(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    environment.update(_bin(tmp_path, None))
    result = _hook(environment, _claude("PreToolUse"))
    assert result.returncode == 2
    assert result.stderr == FAILURE_MESSAGE.encode() + b"\n"
    # Post-launch hooks report the failure but never block.
    post = _hook(environment, _claude("PostToolUse", tool_response={"agentId": "a"}))
    assert post.returncode == 1


def test_interpreter_without_package_denies_launch(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    """An interpreter that cannot import the recorder exits 1; still a denial."""
    base = Path(sys.base_prefix) / "bin" / "python3"
    environment.update(_bin(tmp_path, f'exec "{base}" -I "$@"'))
    result = _hook(environment, _claude("PreToolUse"))
    assert (result.returncode, result.stderr) == (2, FAILURE_MESSAGE.encode() + b"\n")


def test_hung_interpreter_is_killed_and_denied_before_harness_timeout(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    environment.update(_bin(tmp_path, f"exec {SLEEP} 60"))
    started = time.monotonic()
    result = _hook(environment, _claude("PreToolUse"), watchdog=1)
    assert time.monotonic() - started < 10
    assert (result.returncode, result.stderr) == (2, FAILURE_MESSAGE.encode() + b"\n")


def test_recorder_deadline_denies_when_stdin_never_closes(
    environment: dict[str, str],
) -> None:
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import agentic_session_store.child_hook as h;"
                "h.RECORDER_DEADLINE_SECONDS = 1;"
                "raise SystemExit(h.main(['--harness', 'claude']))"
            ),
        ],
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, **environment},
    )
    try:
        assert process.wait(timeout=10) == 2
        assert process.stderr is not None
        assert process.stderr.read() == FAILURE_MESSAGE.encode() + b"\n"
    finally:
        assert process.stdin is not None
        process.stdin.close()
        process.kill()
        process.wait()


def test_locked_journal_denies_launch(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    """An IO failure (journal locked past the busy timeout) is a denial."""
    environment.update(_bin(tmp_path, PYTHON))
    path = Path(environment[Env.SPOOL]) / METADATA_NAMESPACE / "run/children.sqlite"
    ChildJournal(path)
    holder = sqlite3.connect(path, isolation_level=None)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        result = _hook(environment, _claude("PreToolUse"), watchdog=15)
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert (result.returncode, result.stderr) == (2, FAILURE_MESSAGE.encode() + b"\n")
    assert _journal(environment).page().changes == ()


def test_unwritable_partition_denies_launch(
    tmp_path: Path, environment: dict[str, str]
) -> None:
    environment.update(_bin(tmp_path, PYTHON))
    environment[Env.PARTITION] = "missing"
    result = _hook(environment, _claude("PreToolUse"))
    assert (result.returncode, result.stderr) == (2, FAILURE_MESSAGE.encode() + b"\n")


def test_watchdog_must_fire_before_harness_timeout() -> None:
    with pytest.raises(ValueError):
        guarded_command(HookHarness.CLAUDE, deny=True, watchdog=HARNESS_TIMEOUT_SECONDS)


def test_stop_requires_explicit_harness(environment: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "agentic_session_store.child_hook"],
        input=b'{"hook_event_name":"SubagentStop","agent_id":"a"}',
        env={**os.environ, **environment},
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2


def test_harness_must_match_tool(tmp_path: Path, environment: dict[str, str]) -> None:
    environment.update(_bin(tmp_path, PYTHON))
    result = _hook(environment, _claude("PreToolUse"), harness=HookHarness.CODEX)
    assert result.returncode == 2
    assert _journal(environment).page().changes == ()


def test_opening_a_current_journal_takes_no_write_lock(tmp_path: Path) -> None:
    """Every hook opens the journal; with the launch now denied on a lock
    timeout, opening must not queue behind another writer's schema rewrite."""
    path = tmp_path / "children.sqlite"
    ChildJournal(path)
    holder = sqlite3.connect(path, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")
    try:
        ChildJournal(path, busy_timeout=0.05)
    finally:
        holder.execute("ROLLBACK")
        holder.close()
