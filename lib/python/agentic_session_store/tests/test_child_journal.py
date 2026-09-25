"""Real durable transactions, concurrent hook connections and interrupted binding."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from agentic_session_store.child_journal import ChildCall, ChildJournal


@pytest.fixture
def call() -> ChildCall:
    return ChildCall("invocation", "attempt", "codex", "parent/α", "call/β")


def test_restart_retains_unbound_intent_and_exact_binding(
    tmp_path: Path, call: ChildCall
) -> None:
    path = tmp_path / "children.sqlite"
    registered = ChildJournal(path).register(call)
    assert registered.child_native_id is None
    restarted = ChildJournal(path)
    assert restarted.register(call) == registered
    bound = restarted.bind(call, "child/γ")
    assert bound.child_invocation_id == registered.child_invocation_id
    assert ChildJournal(path).lookup(call) == bound
    assert restarted.bind(call, "child/γ") == bound
    with pytest.raises(ValueError, match="Conflicting"):
        restarted.bind(call, "other")
    assert restarted.lookup(call) == bound


def test_concurrent_connections_register_one_intent(
    tmp_path: Path, call: ChildCall
) -> None:
    path = tmp_path / "children.sqlite"
    ChildJournal(path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        registrations = list(
            pool.map(lambda _: ChildJournal(path).register(call), range(32))
        )
    assert len({item.child_invocation_id for item in registrations}) == 1
    assert len({item.sequence for item in registrations}) == 1


def test_reverse_child_completion_cannot_cross_bind(
    tmp_path: Path, call: ChildCall
) -> None:
    journal = ChildJournal(tmp_path / "children.sqlite")
    calls = [replace(call, tool_call_id=f"call-{index}") for index in range(12)]
    intents = [journal.register(item) for item in calls]
    for index in reversed(range(len(calls))):
        journal.bind(calls[index], f"child-{index}")
    for index, item in enumerate(calls):
        assert journal.lookup(item).child_native_id == f"child-{index}"
        assert (
            journal.lookup(item).child_invocation_id
            == intents[index].child_invocation_id
        )


@pytest.mark.parametrize(
    "field", ["invocation_id", "attempt_id", "harness", "parent_native_id"]
)
def test_same_tool_call_is_scoped_by_launch_and_parent(
    tmp_path: Path,
    call: ChildCall,
    field: str,
) -> None:
    journal = ChildJournal(tmp_path / "children.sqlite")
    first = journal.register(call)
    second = journal.register(
        replace(call, **{field: "claude" if field == "harness" else "other"})
    )
    assert first.child_invocation_id != second.child_invocation_id


def test_unknown_call_cannot_bind_and_failed_storage_does_not_acknowledge(
    tmp_path: Path,
    call: ChildCall,
) -> None:
    journal = ChildJournal(tmp_path / "children.sqlite")
    with pytest.raises(ValueError, match="no durable registration"):
        journal.bind(call, "child")
    with sqlite3.connect(journal.path) as connection:
        connection.execute("DROP TABLE child_intents")
    with pytest.raises(sqlite3.OperationalError):
        journal.register(call)


def test_competing_bindings_never_overwrite(tmp_path: Path, call: ChildCall) -> None:
    path = tmp_path / "children.sqlite"
    ChildJournal(path).register(call)

    def bind(child: str) -> str | None:
        try:
            return ChildJournal(path).bind(call, child).child_native_id
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(bind, ["child-a", "child-b"]))
    winner = [value for value in outcomes if value is not None]
    assert len(winner) == 1
    assert ChildJournal(path).lookup(call).child_native_id == winner[0]


def test_late_binding_is_a_new_change_after_consumed_intent(
    tmp_path: Path, call: ChildCall
) -> None:
    journal = ChildJournal(tmp_path / "children.sqlite")
    registered = journal.register(call)
    initial = journal.page()
    assert len(initial.changes) == 1
    assert initial.changes[0].intent == registered
    bound = journal.bind(call, "late-child")
    late = ChildJournal(journal.path).page(initial.watermark)
    assert len(late.changes) == 1
    assert late.changes[0].intent == bound
    assert late.watermark > initial.watermark
    assert journal.page(watermark=initial.watermark) == initial
    journal.bind(call, "late-child")
    journal.register(call)
    assert journal.page(late.watermark).changes == ()


def test_pinned_pages_exclude_concurrent_updates_without_losing_them(
    tmp_path: Path,
    call: ChildCall,
) -> None:
    journal = ChildJournal(tmp_path / "children.sqlite")
    calls = [replace(call, tool_call_id=str(index)) for index in range(5)]
    for item in calls:
        journal.register(item)
    page = journal.page(limit=2)
    head = page.watermark
    seen = list(page.changes)
    journal.bind(calls[0], "late")
    while page.next_after is not None:
        page = journal.page(page.next_after, watermark=head, limit=2)
        seen.extend(page.changes)
    assert len(seen) == 5
    assert all(change.intent.child_native_id is None for change in seen)
    tail = journal.page(head)
    assert len(tail.changes) == 1
    assert tail.changes[0].intent.child_native_id == "late"


def test_change_append_failure_rolls_back_binding(
    tmp_path: Path, call: ChildCall
) -> None:
    journal = ChildJournal(tmp_path / "children.sqlite")
    registered = journal.register(call)
    before = journal.page()
    with sqlite3.connect(journal.path) as connection:
        connection.execute("""CREATE TRIGGER reject_change BEFORE INSERT ON child_changes
                              BEGIN SELECT RAISE(ABORT, 'disk simulation'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        journal.bind(call, "child")
    assert journal.lookup(call) == registered
    assert journal.page() == before


@pytest.mark.parametrize(
    "after,watermark,limit",
    [(-1, None, 1), (0, None, 0), (0, None, 501), (2, 1, 1), (0, 99, 1)],
)
def test_invalid_recovery_cursor_fails(
    tmp_path: Path,
    after: int,
    watermark: int | None,
    limit: int,
) -> None:
    journal = ChildJournal(tmp_path / "children.sqlite")
    with pytest.raises(ValueError):
        journal.page(after, watermark=watermark, limit=limit)


def test_cross_harness_lifecycle_is_durable_and_conflicts_fail(tmp_path, call):
    cross = replace(call, target_harness="claude")
    journal = ChildJournal(tmp_path / "children.sqlite")
    initial = journal.register(cross)
    assert initial.status is None
    assert journal.launched(cross).status == "launched"
    journal.bind(cross, "actual-native-child")
    outcome = journal.finished(cross, 7)
    assert (outcome.status, outcome.exit_code) == ("failed", 7)
    assert ChildJournal(journal.path).lookup(cross) == outcome
    assert journal.finished(cross, 7) == outcome
    with pytest.raises(ValueError, match="terminal"):
        journal.finished(cross, 0)
    with pytest.raises(ValueError, match="target harness"):
        journal.register(replace(cross, target_harness="codex"))
    changes = journal.page().changes
    assert len(changes) == 4
    assert [c.intent.status for c in changes] == [
        None,
        "launched",
        "launched",
        "failed",
    ]
    assert changes[0].intent.child_native_id is None
    assert changes[2].intent.child_native_id == "actual-native-child"


def test_failed_launch_is_distinct_and_cannot_finish(tmp_path, call):
    journal = ChildJournal(tmp_path / "children.sqlite")
    journal.register(call)
    with pytest.raises(ValueError, match="before finishing"):
        journal.finished(call, 0)
    result = journal.launch_failed(call)
    assert result.child_native_id is None
    assert result.status == "launch_failed"
    assert result.exit_code is None
    assert journal.launch_failed(call) == result
    with pytest.raises(ValueError, match="Failed launch"):
        journal.bind(call, "fabricated")
    with pytest.raises(ValueError, match="terminal"):
        journal.launched(call)


def test_additive_migration_preserves_old_wire_records(tmp_path):
    from agentic_session_store.child_export import export_page

    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE child_intents (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                child_invocation_id TEXT NOT NULL UNIQUE,
                invocation_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
                harness TEXT NOT NULL, parent_native_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL, child_native_id TEXT,
                UNIQUE(invocation_id,attempt_id,harness,parent_native_id,tool_call_id));
            CREATE TABLE child_changes (sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                intent_sequence INTEGER NOT NULL, child_native_id TEXT);
            INSERT INTO child_intents VALUES (1,'child-invocation','invocation','attempt','codex','parent','call', 'child');
            INSERT INTO child_changes VALUES (1,1,NULL),(2,1,'child');
        """)
    before = export_page(ChildJournal(path, read_only=True).page())
    journal = ChildJournal(path)
    assert export_page(journal.page()) == before
    assert before["schema_version"] == 1
    cross = ChildCall("invocation", "attempt", "codex", "parent", "new-call", "claude")
    journal.register(cross)
    journal.launched(cross)
    journal.finished(cross, 0)
    assert export_page(journal.page())["schema_version"] == 2
    assert export_page(journal.page(watermark=2)) == before


def test_launch_failure_reason_is_durable_and_exported(tmp_path, call):
    from agentic_session_store.child_export import export_page
    from agentic_session_store.child_journal import LaunchFailureReason

    path = tmp_path / "children.sqlite"
    journal = ChildJournal(path)
    journal.register(call)
    failed = journal.launch_failed(call, LaunchFailureReason.CODEX_SANDBOX_UNAVAILABLE)
    assert failed.reason == "codex_sandbox_unavailable"
    assert (
        journal.launch_failed(call, LaunchFailureReason.CODEX_SANDBOX_UNAVAILABLE)
        == failed
    )
    with pytest.raises(ValueError, match="terminal"):
        journal.launch_failed(call, LaunchFailureReason.PROCESS_START_FAILED)
    reopened = ChildJournal(path, read_only=True)
    assert reopened.page().changes[-1].intent.reason == "codex_sandbox_unavailable"
    exported = export_page(reopened.page())
    assert exported["page"]["changes"][-1]["intent"]["reason"] == (
        "codex_sandbox_unavailable"
    )
    assert "reason" not in exported["page"]["changes"][0]["intent"]


def test_pre_reason_journal_upgrades_its_update_trigger(tmp_path, call):
    from agentic_session_store.child_journal import LaunchFailureReason

    path = tmp_path / "children.sqlite"
    ChildJournal(path)
    with sqlite3.connect(path) as connection:
        # Recreate the state a journal written before `reason` existed had.
        connection.executescript("""
            DROP TRIGGER child_updated;
            CREATE TRIGGER child_updated
            AFTER UPDATE OF child_native_id, status, exit_code ON child_intents
            BEGIN
                INSERT INTO child_changes (intent_sequence, child_native_id, status, exit_code)
                VALUES (NEW.sequence, NEW.child_native_id, NEW.status, NEW.exit_code);
            END;
            -- Journals written before agentic-session-store 0.5.0 never set it.
            PRAGMA user_version=0;
        """)
    journal = ChildJournal(path)
    journal.register(call)
    journal.launch_failed(call, LaunchFailureReason.PROCESS_START_FAILED)
    assert journal.page().changes[-1].intent.reason == "process_start_failed"
