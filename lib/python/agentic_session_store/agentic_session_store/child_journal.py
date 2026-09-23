"""Durable hook observations; no workflow membership or completeness decisions.

The caller owns a partition-specific database path. Successful registration is
acknowledged only after SQLite's FULL-synchronous transaction commits. A missing
post-tool response leaves an unbound intent, never a guessed child identity.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from agentic_session_store.child_schema import upgrade


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


@dataclass(frozen=True)
class ChildChange:
    sequence: int
    intent: ChildIntent


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

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path
        self._read_only = read_only
        if read_only:
            return
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
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

    def _connect(self) -> sqlite3.Connection:
        if self._read_only:
            return sqlite3.connect(
                self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5
            )
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @staticmethod
    def _get(connection: sqlite3.Connection, call: ChildCall) -> ChildIntent:
        row = connection.execute(
            """SELECT sequence, child_invocation_id, child_native_id, target_harness, status, exit_code FROM child_intents
               WHERE invocation_id=? AND attempt_id=? AND harness=?
                 AND parent_native_id=? AND tool_call_id=?""",
            call.key,
        ).fetchone()
        if row is None:
            raise ValueError("Child call has no durable registration")
        if row[3] != call.target_harness:
            raise ValueError("Conflicting child target harness")
        return ChildIntent(row[0], row[1], call, row[2], row[4], row[5])

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

    def bind(self, call: ChildCall, child_native_id: str) -> ChildIntent:
        if (
            not child_native_id
            or len(child_native_id.encode("utf-8")) > 2048
            or "\x00" in child_native_id
        ):
            raise ValueError("Invalid child native identity")
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                intent = self._get(connection, call)
                if intent.status == "launch_failed":
                    raise ValueError("Failed launch cannot bind a native child")
                if intent.child_native_id not in {None, child_native_id}:
                    raise ValueError("Conflicting child native identity")
                connection.execute(
                    "UPDATE child_intents SET child_native_id=? WHERE sequence=?",
                    (child_native_id, intent.sequence),
                )
                bound = self._get(connection, call)
            return bound

    def launched(self, call: ChildCall) -> ChildIntent:
        return self._transition(call, "launched", None)

    def launch_failed(self, call: ChildCall) -> ChildIntent:
        return self._transition(call, "launch_failed", None)

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
        self, call: ChildCall, status: str, exit_code: int | None
    ) -> ChildIntent:
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            intent = self._get(connection, call)
            if (intent.status, intent.exit_code) == (status, exit_code):
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
                "UPDATE child_intents SET status=?, exit_code=? WHERE sequence=?",
                (status, exit_code, intent.sequence),
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
            rows = connection.execute(
                f"""SELECT change.sequence, intent.sequence, intent.child_invocation_id,
                          intent.invocation_id, intent.attempt_id, intent.harness,
                          intent.parent_native_id, intent.tool_call_id, change.child_native_id, {target}, {status}
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
                    ),
                )
                for row in rows[:limit]
            )
            continuation = changes[-1].sequence if len(rows) > limit else None
            return ChildPage(head, changes, continuation)
