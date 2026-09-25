"""Additive child journal migration; existing change rows remain immutable."""

from __future__ import annotations

import sqlite3

# Stored in SQLite's user_version once upgrade() has run. Bump whenever
# upgrade() or the base tables change. The marker alone is never trusted:
# agentic-session-store <= 0.4.0 does not read it and rewrites its own triggers
# on every open, so schema_current() also checks the actual definitions.
SCHEMA_VERSION = 1

# Every column a writer of this version relies on, per table.
REQUIRED_COLUMNS = {
    "child_intents": frozenset(
        {
            "sequence",
            "child_invocation_id",
            "invocation_id",
            "attempt_id",
            "harness",
            "parent_native_id",
            "tool_call_id",
            "child_native_id",
            "target_harness",
            "status",
            "exit_code",
            "reason",
        }
    ),
    "child_changes": frozenset(
        {
            "sequence",
            "intent_sequence",
            "child_native_id",
            "status",
            "exit_code",
            "reason",
            "conflict_native_id",
        }
    ),
    "child_conflicts": frozenset({"sequence", "intent_sequence", "observed_native_id"}),
    "child_stops": frozenset(
        {"invocation_id", "attempt_id", "harness", "child_native_id"}
    ),
}

# The triggers that append every lifecycle change. Owned by this journal.
TRIGGERS = {
    "child_registered": """
        CREATE TRIGGER child_registered AFTER INSERT ON child_intents
        BEGIN
            INSERT INTO child_changes
                (intent_sequence, child_native_id, status, exit_code, reason)
            VALUES (NEW.sequence, NEW.child_native_id, NEW.status, NEW.exit_code, NEW.reason);
        END
    """,
    "child_updated": """
        CREATE TRIGGER child_updated
        AFTER UPDATE OF child_native_id, status, exit_code, reason ON child_intents
        WHEN OLD.child_native_id IS NOT NEW.child_native_id
          OR OLD.status IS NOT NEW.status OR OLD.exit_code IS NOT NEW.exit_code
          OR OLD.reason IS NOT NEW.reason
        BEGIN
            INSERT INTO child_changes
                (intent_sequence, child_native_id, status, exit_code, reason)
            VALUES (NEW.sequence, NEW.child_native_id, NEW.status, NEW.exit_code, NEW.reason);
        END
    """,
    "child_conflicted": """
        CREATE TRIGGER child_conflicted AFTER INSERT ON child_conflicts
        BEGIN
            INSERT INTO child_changes
                (intent_sequence, child_native_id, status, exit_code, reason,
                 conflict_native_id)
            SELECT sequence, child_native_id, status, exit_code, reason,
                   NEW.observed_native_id
            FROM child_intents WHERE sequence=NEW.intent_sequence;
        END
    """,
}
# Triggers written by earlier versions that must not survive a migration.
RETIRED_TRIGGERS = ("child_bound",)


class JournalSchemaTooNew(ValueError):
    """The journal was written by a newer, unsupported schema; never downgrade."""


def _normalized(sql: str | None) -> str:
    return " ".join((sql or "").split())


def schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def schema_current(connection: sqlite3.Connection) -> bool:
    """True only when the marker, every required column and every trigger match.

    Raises JournalSchemaTooNew rather than reinterpret a newer journal.
    """
    version = schema_version(connection)
    if version > SCHEMA_VERSION:
        raise JournalSchemaTooNew("Child journal schema is newer than supported")
    if version != SCHEMA_VERSION:
        return False
    for table, required in REQUIRED_COLUMNS.items():
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not required <= columns:
            return False
    triggers = dict(
        connection.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")
    )
    if any(name in triggers for name in RETIRED_TRIGGERS):
        return False
    return all(
        _normalized(triggers.get(name)) == _normalized(sql)
        for name, sql in TRIGGERS.items()
    )


def upgrade(connection: sqlite3.Connection) -> None:
    for table, additions in (
        (
            "child_intents",
            {
                "target_harness": "TEXT",
                "status": "TEXT",
                "exit_code": "INTEGER",
                "reason": "TEXT",
            },
        ),
        (
            "child_changes",
            {
                "status": "TEXT",
                "exit_code": "INTEGER",
                "reason": "TEXT",
                "conflict_native_id": "TEXT",
            },
        ),
    ):
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for name, kind in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
    # A conflicting identity is evidence, never a replacement for the binding.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS child_conflicts (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            intent_sequence INTEGER NOT NULL REFERENCES child_intents(sequence),
            observed_native_id TEXT NOT NULL,
            UNIQUE (intent_sequence, observed_native_id)
        )
    """)
    # Stop observations carry only the child's own identity. They settle a
    # bound, launched intent whichever of the two hooks arrives first.
    connection.execute("""
        CREATE TABLE IF NOT EXISTS child_stops (
            invocation_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL,
            harness TEXT NOT NULL,
            child_native_id TEXT NOT NULL,
            PRIMARY KEY (invocation_id, attempt_id, harness, child_native_id)
        )
    """)
    # These triggers belong exclusively to this journal implementation.
    # Recreated on every migration, so a journal written before `reason`
    # existed, or one an older process rewrote, records every change again.
    for name in (*RETIRED_TRIGGERS, *TRIGGERS):
        connection.execute(f"DROP TRIGGER IF EXISTS {name}")
    for sql in TRIGGERS.values():
        connection.execute(sql)
