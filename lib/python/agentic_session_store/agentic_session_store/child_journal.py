"""Durable hook observations; no workflow membership or completeness decisions.

The caller owns a partition-specific database path. Successful registration is
acknowledged only after SQLite's FULL-synchronous transaction commits. A missing
post-tool response leaves an unbound intent, never a guessed child identity.

Lifecycle states, per intent:

* ``None``: intent committed, launch never acknowledged. For a native child
  this also covers a launch denied by another hook, and a spawn the harness
  rejected without reporting it (Codex fires no hook for a failed tool).
* ``launched``: the harness acknowledged the launch. Native children are bound
  in the same transaction, so a launched native intent always has its child ID.
* ``launch_failed``: the harness reported the launch failed; never bound.
* ``completed``/``failed``/``cancelled``: terminal. Delegates carry their exit
  status. Native children carry none: ``completed`` means the harness reported
  the child stopped (Claude/Codex SubagentStop, or a synchronous Agent result),
  not that its descendants settled or that it can never be resumed.

A second, different child identity for a bound intent is recorded in
``child_conflicts`` and exported as a change; the binding is never replaced.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from agentic_session_store.child_schema import SCHEMA_VERSION, upgrade


def _schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


class LaunchFailureReason(StrEnum):
    """Why a registered delegate never started. Stable wire values."""

    PROCESS_START_FAILED = "process_start_failed"
    CODEX_SANDBOX_UNAVAILABLE = "codex_sandbox_unavailable"
    # The native spawn tool reported failure without returning a child.
    NATIVE_TOOL_FAILED = "native_tool_failed"
    # The native spawn tool was interrupted before returning a child.
    NATIVE_TOOL_INTERRUPTED = "native_tool_interrupted"
    # The capture hook failed after committing the intent and denied the launch.
    CAPTURE_HOOK_FAILED = "capture_hook_failed"


class ChildBindingConflict(ValueError):
    """A different child identity was observed for a bound intent.

    The observation is committed before this is raised; the binding is kept.
    """


NATIVE_STATUS_LAUNCHED = "launched"
NATIVE_STATUS_COMPLETED = "completed"


@dataclass(frozen=True)
class ChildCall:
    invocation_id: str
    attempt_id: str
    harness: str
    parent_native_id: str
    tool_call_id: str
    target_harness: str | None = None

    def __post_init__(self) -> None:
        if self.harness not in {"claude", "codex"}:
            raise ValueError("Unsupported child-call harness")
        if self.target_harness not in {None, "claude", "codex"}:
            raise ValueError("Unsupported target harness")
        for value in self.key:
            if not value or len(value.encode("utf-8")) > 2048 or "\x00" in value:
                raise ValueError("Invalid child-call identity")

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.invocation_id,
            self.attempt_id,
            self.harness,
            self.parent_native_id,
            self.tool_call_id,
        )


@dataclass(frozen=True)
class ChildIntent:
    sequence: int
    child_invocation_id: str
    call: ChildCall
    child_native_id: str | None
    status: str | None = None
    exit_code: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ChildChange:
    sequence: int
    intent: ChildIntent
    # Set only on a change that records a rejected, conflicting child identity.
    conflict_native_id: str | None = None


@dataclass(frozen=True)
class ChildPage:
    watermark: int
    changes: tuple[ChildChange, ...]
    next_after: int | None


class ChildJournal:
    """One durable journal per retained workspace partition.

    Reopening is safe across hook processes. Correlation uses exact opaque IDs;
    replaying registration returns the existing ID, and binding conflicts fail.
    SQLite errors propagate so the hook can explicitly deny a launch.
    """

    def __init__(
        self, path: Path, *, read_only: bool = False, busy_timeout: float = 5
    ) -> None:
        self.path = path
        self._read_only = read_only
        self._busy_timeout = busy_timeout
        if read_only:
            return
        with closing(self._connect()) as connection:
            # Every hook process opens the journal. Rewriting the schema on each
            # open serializes concurrent launches behind an exclusive lock and,
            # now that a lock timeout denies the launch, turns contention into
            # refused children. A current journal is left untouched.
            if _schema_version(connection) == SCHEMA_VERSION:
                return
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                if _schema_version(connection) != SCHEMA_VERSION:
                    self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS child_intents (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                child_invocation_id TEXT NOT NULL UNIQUE,
                invocation_id TEXT NOT NULL,
                attempt_id TEXT NOT NULL,
                harness TEXT NOT NULL,
                parent_native_id TEXT NOT NULL,
                tool_call_id TEXT NOT NULL,
                child_native_id TEXT,
                UNIQUE (invocation_id, attempt_id, harness, parent_native_id, tool_call_id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS child_changes (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                intent_sequence INTEGER NOT NULL REFERENCES child_intents(sequence),
                child_native_id TEXT
            )
        """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS child_changes_intent
            ON child_changes(intent_sequence)
        """)
        # Upgrade journals written before incremental recovery existed.
        connection.execute("""
            INSERT INTO child_changes (intent_sequence, child_native_id)
            SELECT sequence, child_native_id FROM child_intents AS intent
            WHERE NOT EXISTS (
                SELECT 1 FROM child_changes WHERE intent_sequence=intent.sequence
            )
        """)
        upgrade(connection)
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def _connect(self) -> sqlite3.Connection:
        if self._read_only:
            return sqlite3.connect(
                self.path.resolve().as_uri() + "?mode=ro",
                uri=True,
                timeout=self._busy_timeout,
            )
        connection = sqlite3.connect(self.path, timeout=self._busy_timeout)
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _get(connection: sqlite3.Connection, call: ChildCall) -> ChildIntent:
        row = connection.execute(
            """SELECT sequence, child_invocation_id, child_native_id, target_harness, status, exit_code, reason
               FROM child_intents
               WHERE invocation_id=? AND attempt_id=? AND harness=?
                 AND parent_native_id=? AND tool_call_id=?""",
            call.key,
        ).fetchone()
        if row is None:
            raise ValueError("Child call has no durable registration")
        if row[3] != call.target_harness:
            raise ValueError("Conflicting child target harness")
        return ChildIntent(row[0], row[1], call, row[2], row[4], row[5], row[6])

    def register(self, call: ChildCall) -> ChildIntent:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """INSERT INTO child_intents
                       (child_invocation_id, invocation_id, attempt_id, harness,
                        parent_native_id, tool_call_id, target_harness) VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT (invocation_id, attempt_id, harness,
                                    parent_native_id, tool_call_id) DO NOTHING""",
                    (str(uuid4()), *call.key, call.target_harness),
                )
                intent = self._get(connection, call)
            return intent

    @staticmethod
    def _valid_native(child_native_id: str) -> None:
        if (
            not isinstance(child_native_id, str)
            or not child_native_id
            or len(child_native_id.encode("utf-8")) > 2048
            or "\x00" in child_native_id
        ):
            raise ValueError("Invalid child native identity")

    @staticmethod
    def _conflict(
        connection: sqlite3.Connection, intent: ChildIntent, child_native_id: str
    ) -> bool:
        """Record a different identity for a bound intent; True if it conflicts."""
        if intent.child_native_id in {None, child_native_id}:
            return False
        connection.execute(
            """INSERT INTO child_conflicts (intent_sequence, observed_native_id)
               VALUES (?, ?)
               ON CONFLICT (intent_sequence, observed_native_id) DO NOTHING""",
            (intent.sequence, child_native_id),
        )
        return True

    def bind(self, call: ChildCall, child_native_id: str) -> ChildIntent:
        self._valid_native(child_native_id)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                intent = self._get(connection, call)
                if intent.status == "launch_failed":
                    raise ValueError("Failed launch cannot bind a native child")
                conflict = self._conflict(connection, intent, child_native_id)
                if not conflict:
                    connection.execute(
                        "UPDATE child_intents SET child_native_id=? WHERE sequence=?",
                        (child_native_id, intent.sequence),
                    )
                bound = self._get(connection, call)
            # Raised after commit, so the conflicting observation is durable.
            if conflict:
                raise ChildBindingConflict("Conflicting child native identity")
            return bound

    def observe_launch(
        self, call: ChildCall, child_native_id: str, *, stopped: bool = False
    ) -> ChildIntent:
        """Record a native launch acknowledgement and its child in one commit.

        ``stopped`` is for a harness result that also reports the child done.
        A stop observed earlier for this child settles it in the same commit.
        Repeats are no-ops; a different child is a recorded conflict.
        """
        if call.target_harness is not None:
            raise ValueError("Delegate lifecycle is recorded by its runner")
        self._valid_native(child_native_id)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                intent = self._get(connection, call)
                if intent.status == "launch_failed":
                    raise ValueError("Failed launch cannot bind a native child")
                conflict = self._conflict(connection, intent, child_native_id)
                if not conflict:
                    connection.execute(
                        """UPDATE child_intents
                           SET child_native_id=?, status=COALESCE(status, ?)
                           WHERE sequence=?""",
                        (child_native_id, NATIVE_STATUS_LAUNCHED, intent.sequence),
                    )
                    stopped = stopped or (
                        connection.execute(
                            """SELECT 1 FROM child_stops
                               WHERE invocation_id=? AND attempt_id=? AND harness=?
                                 AND child_native_id=?""",
                            (*call.key[:3], child_native_id),
                        ).fetchone()
                        is not None
                    )
                    if stopped:
                        connection.execute(
                            "UPDATE child_intents SET status=? WHERE sequence=? AND status=?",
                            (
                                NATIVE_STATUS_COMPLETED,
                                intent.sequence,
                                NATIVE_STATUS_LAUNCHED,
                            ),
                        )
                bound = self._get(connection, call)
            if conflict:
                raise ChildBindingConflict("Conflicting child native identity")
            return bound

    def observe_launch_failure(
        self, call: ChildCall, reason: LaunchFailureReason
    ) -> ChildIntent:
        """Record a native launch the harness reported as failed, idempotently."""
        if call.target_harness is not None:
            raise ValueError("Delegate lifecycle is recorded by its runner")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            intent = self._get(connection, call)
            if intent.status == "launch_failed":
                return intent
            if intent.status is not None or intent.child_native_id is not None:
                raise ValueError("Launched child cannot have failed to launch")
            connection.execute(
                "UPDATE child_intents SET status=?, reason=? WHERE sequence=?",
                ("launch_failed", reason.value, intent.sequence),
            )
            return self._get(connection, call)

    def observe_stop(
        self, invocation_id: str, attempt_id: str, harness: str, child_native_id: str
    ) -> int:
        """Record that a native child stopped; settle its launched intents.

        The stop carries only the child's identity, so it never creates or
        chooses a binding. It is kept so a later launch acknowledgement for the
        same child settles too. Returns the number of intents settled now.
        """
        self._valid_native(child_native_id)
        # Validates the harness and bounds the context identities.
        ChildCall(invocation_id, attempt_id, harness, "stop", "stop")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO child_stops
                   (invocation_id, attempt_id, harness, child_native_id)
                   VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                (invocation_id, attempt_id, harness, child_native_id),
            )
            return connection.execute(
                """UPDATE child_intents SET status=?
                   WHERE invocation_id=? AND attempt_id=? AND harness=?
                     AND child_native_id=? AND status=? AND target_harness IS NULL""",
                (
                    NATIVE_STATUS_COMPLETED,
                    invocation_id,
                    attempt_id,
                    harness,
                    child_native_id,
                    NATIVE_STATUS_LAUNCHED,
                ),
            ).rowcount

    def launched(self, call: ChildCall) -> ChildIntent:
        return self._transition(call, "launched", None)

    def launch_failed(
        self, call: ChildCall, reason: LaunchFailureReason | None = None
    ) -> ChildIntent:
        return self._transition(call, "launch_failed", None, reason)

    def finished(self, call: ChildCall, exit_code: int) -> ChildIntent:
        if (
            isinstance(exit_code, bool)
            or not isinstance(exit_code, int)
            or not -255 <= exit_code <= 255
        ):
            raise ValueError("Invalid delegate exit status")
        status = (
            "completed"
            if exit_code == 0
            else "cancelled"
            if exit_code < 0
            else "failed"
        )
        return self._transition(call, status, exit_code)

    def _transition(
        self,
        call: ChildCall,
        status: str,
        exit_code: int | None,
        reason: LaunchFailureReason | None = None,
    ) -> ChildIntent:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            intent = self._get(connection, call)
            if (intent.status, intent.exit_code, intent.reason) == (
                status,
                exit_code,
                None if reason is None else reason.value,
            ):
                return intent
            if intent.status is not None and intent.status != "launched":
                raise ValueError("Child launch outcome is terminal")
            if status == "launch_failed" and intent.child_native_id is not None:
                raise ValueError("Bound child cannot have failed to launch")
            if status in {"launched", "launch_failed"} and intent.status is not None:
                raise ValueError("Conflicting child launch state")
            if (
                status not in {"launched", "launch_failed"}
                and intent.status != "launched"
            ):
                raise ValueError("Child must launch before finishing")
            connection.execute(
                "UPDATE child_intents SET status=?, exit_code=?, reason=? WHERE sequence=?",
                (
                    status,
                    exit_code,
                    None if reason is None else reason.value,
                    intent.sequence,
                ),
            )
            return self._get(connection, call)

    def lookup(self, call: ChildCall) -> ChildIntent:
        with closing(self._connect()) as connection:
            return self._get(connection, call)

    def page(
        self, after: int = 0, *, watermark: int | None = None, limit: int = 100
    ) -> ChildPage:
        """Read immutable changes, including bindings newer than their intent.

        A supplied watermark pins a traversal while hooks continue writing.
        The next traversal starts at that watermark to recover later bindings.
        """
        if (
            after < 0
            or not 1 <= limit <= 500
            or (watermark is not None and watermark < after)
        ):
            raise ValueError("Invalid child journal cursor")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            latest = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM child_changes"
            ).fetchone()[0]
            head = latest if watermark is None else watermark
            if head > latest or after > head:
                raise ValueError("Child journal cursor is beyond retained history")
            intent_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(child_intents)")
            }
            change_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(child_changes)")
            }
            target = (
                "intent.target_harness"
                if "target_harness" in intent_columns
                else "NULL"
            )
            status = (
                "change.status, change.exit_code"
                if "status" in change_columns
                else "NULL, NULL"
            )
            reason = "change.reason" if "reason" in change_columns else "NULL"
            conflict = (
                "change.conflict_native_id"
                if "conflict_native_id" in change_columns
                else "NULL"
            )
            rows = connection.execute(
                f"""SELECT change.sequence, intent.sequence, intent.child_invocation_id,
                          intent.invocation_id, intent.attempt_id, intent.harness,
                          intent.parent_native_id, intent.tool_call_id, change.child_native_id, {target}, {status}, {reason}, {conflict}
                   FROM child_changes AS change
                   JOIN child_intents AS intent ON intent.sequence=change.intent_sequence
                   WHERE change.sequence > ? AND change.sequence <= ?
                   ORDER BY change.sequence LIMIT ?""",
                (after, head, limit + 1),
            ).fetchall()
            changes = tuple(
                ChildChange(
                    row[0],
                    ChildIntent(
                        row[1],
                        row[2],
                        ChildCall(*row[3:8], target_harness=row[9]),
                        row[8],
                        row[10],
                        row[11],
                        row[12],
                    ),
                    row[13],
                )
                for row in rows[:limit]
            )
            continuation = changes[-1].sequence if len(rows) > limit else None
            return ChildPage(head, changes, continuation)
