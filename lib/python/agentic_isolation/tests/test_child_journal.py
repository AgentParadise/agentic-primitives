"""Validate the actual producer-to-reader transport and reject truncated pages."""

import asyncio
import json
import shlex
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from agentic_session_store.child_journal import ChildCall, ChildJournal

from agentic_isolation.child_journal import JournalReadError, WorkspaceChildJournalReader
from agentic_isolation.providers.base import ExecuteResult


@pytest.mark.asyncio
@pytest.mark.parametrize("target_harness", [None, "claude"])
async def test_real_export_roundtrip_recovers_late_binding(tmp_path: Path, target_harness) -> None:
    path = tmp_path / "retained 'quoted' journal.sqlite"
    journal = ChildJournal(path)
    call = ChildCall("invocation", "attempt", "codex", "parent/α", "call", target_harness)
    registered = journal.register(call)

    async def execute(command: str, **kwargs: object) -> ExecuteResult:
        process = await asyncio.create_subprocess_exec(
            *shlex.split(command),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        return ExecuteResult(
            exit_code=process.returncode or 0,
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            duration_ms=0,
        )

    reader = WorkspaceChildJournalReader(execute, str(path))
    initial = await reader.page()
    assert initial.changes[0].intent.child_invocation_id == registered.child_invocation_id
    assert initial.changes[0].intent.call.parent_native_id == "parent/α"
    journal.bind(call, "child/β")
    if target_harness is not None:
        journal.launched(call)
        journal.finished(call, 3)
    late = await reader.page(initial.watermark)
    assert late.changes[0].intent.child_native_id == "child/β"
    assert late.changes[0].intent.call.target_harness == target_harness
    if target_harness is not None:
        assert late.changes[-1].intent.status == "failed"
        assert late.changes[-1].intent.exit_code == 3
    assert await reader.page(watermark=initial.watermark) == initial


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sequences,head,next_after",
    [
        ([], 2, None),
        ([2, 1], 2, None),
        ([1, 1], 2, 1),
        ([3], 2, None),
        ([1], 2, None),
        ([1], 2, 2),
        ([2], 2, 2),
    ],
)
async def test_invalid_page_cannot_advance(
    sequences: list[int], head: int, next_after: int | None
) -> None:
    changes = [
        {
            "sequence": seq,
            "intent": {
                "sequence": 1,
                "child_invocation_id": "child-invocation",
                "call": {
                    "invocation_id": "invocation",
                    "attempt_id": "attempt",
                    "harness": "codex",
                    "parent_native_id": "parent",
                    "tool_call_id": "call",
                },
                "child_native_id": None,
            },
        }
        for seq in sequences
    ]
    execute = AsyncMock(
        return_value=ExecuteResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "schema_version": 1,
                    "page": {"watermark": head, "changes": changes, "next_after": next_after},
                }
            ),
            stderr="",
            duration_ms=0,
        )
    )
    with pytest.raises(JournalReadError):
        await WorkspaceChildJournalReader(execute, "/spool/journal.sqlite").page()


async def _real_execute(command: str, **kwargs: object) -> ExecuteResult:
    process = await asyncio.create_subprocess_exec(
        *shlex.split(command),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
    return ExecuteResult(
        exit_code=process.returncode or 0,
        stdout=stdout.decode(),
        stderr=stderr.decode(),
        duration_ms=0,
    )


@pytest.mark.asyncio
async def test_native_lifecycle_and_conflict_roundtrip(tmp_path: Path) -> None:
    """Schema v3: native launched/completed without exit status, and a
    recorded conflict that leaves the original binding in place."""
    from agentic_session_store.child_journal import ChildBindingConflict, LaunchFailureReason

    journal = ChildJournal(tmp_path / "children.sqlite")
    call = ChildCall("invocation", "attempt", "claude", "root", "call")
    failed = ChildCall("invocation", "attempt", "claude", "root", "failed")
    journal.register(call)
    journal.register(failed)
    journal.observe_launch(call, "agent-child")
    journal.observe_stop("invocation", "attempt", "claude", "agent-child")
    journal.observe_launch_failure(failed, LaunchFailureReason.NATIVE_TOOL_FAILED)
    with pytest.raises(ChildBindingConflict):
        journal.observe_launch(call, "agent-other")
    page = await WorkspaceChildJournalReader(
        _real_execute, str(tmp_path / "children.sqlite")
    ).page()
    assert [(c.intent.call.tool_call_id, c.intent.status) for c in page.changes] == [
        ("call", None),
        ("failed", None),
        ("call", "launched"),
        ("call", "completed"),
        ("failed", "launch_failed"),
        ("call", "completed"),
    ]
    assert page.changes[4].intent.reason == "native_tool_failed"
    assert page.changes[-1].conflict_native_id == "agent-other"
    assert page.changes[-1].intent.child_native_id == "agent-child"
    assert all(c.intent.exit_code is None for c in page.changes)


def _v3_change(intent: dict[str, object], conflict: str | None = None) -> dict[str, object]:
    change: dict[str, object] = {
        "sequence": 1,
        "intent": {
            "sequence": 1,
            "child_invocation_id": "child-invocation",
            "call": {
                "invocation_id": "invocation",
                "attempt_id": "attempt",
                "harness": "claude",
                "parent_native_id": "root",
                "tool_call_id": "call",
            },
            **intent,
        },
    }
    if conflict is not None:
        change["conflict_native_id"] = conflict
    return change


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        # A native child never reports an exit status.
        _v3_change({"child_native_id": "agent-a", "status": "completed", "exit_code": 0}),
        # Native failure/cancellation are not observable; only a stop is.
        _v3_change({"child_native_id": "agent-a", "status": "failed", "exit_code": 1}),
        # A launched native child is always bound in the same commit.
        _v3_change({"child_native_id": None, "status": "launched"}),
        # A failed launch has no child.
        _v3_change({"child_native_id": "agent-a", "status": "launch_failed"}),
        # A conflict needs a different, recorded binding.
        _v3_change({"child_native_id": None}, conflict="agent-b"),
        _v3_change({"child_native_id": "agent-a", "status": "launched"}, conflict="agent-a"),
        # Only a failed launch carries a reason.
        _v3_change({"child_native_id": "agent-a", "status": "launched", "reason": "x"}),
    ],
)
async def test_invalid_native_lifecycle_is_rejected(change: dict[str, object]) -> None:
    execute = AsyncMock(
        return_value=ExecuteResult(
            exit_code=0,
            stdout=json.dumps(
                {
                    "schema_version": 3,
                    "page": {"watermark": 1, "changes": [change], "next_after": None},
                }
            ),
            stderr="",
            duration_ms=0,
        )
    )
    with pytest.raises(JournalReadError):
        await WorkspaceChildJournalReader(execute, "/spool/journal.sqlite").page()
