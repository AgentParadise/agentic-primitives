"""Additive child journal migration; existing change rows remain immutable."""

from __future__ import annotations

import sqlite3

# Stored in SQLite's user_version once upgrade() has run. Bump whenever
# upgrade() or the base tables change, so existing journals migrate once.
SCHEMA_VERSION = 1


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
    connection.execute("DROP TRIGGER IF EXISTS child_registered")
    connection.execute("DROP TRIGGER IF EXISTS child_bound")
    # Recreated so journals written before `reason` existed record it too.
    connection.execute("DROP TRIGGER IF EXISTS child_updated")
    connection.execute("DROP TRIGGER IF EXISTS child_conflicted")
    connection.execute("""
        CREATE TRIGGER child_registered AFTER INSERT ON child_intents
        BEGIN
            INSERT INTO child_changes
                (intent_sequence, child_native_id, status, exit_code, reason)
            VALUES (NEW.sequence, NEW.child_native_id, NEW.status, NEW.exit_code, NEW.reason);
        END
    """)
    connection.execute("""
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
    """)
    connection.execute("""
        CREATE TRIGGER child_conflicted AFTER INSERT ON child_conflicts
        BEGIN
            INSERT INTO child_changes
                (intent_sequence, child_native_id, status, exit_code, reason,
                 conflict_native_id)
            SELECT sequence, child_native_id, status, exit_code, reason,
                   NEW.observed_native_id
            FROM child_intents WHERE sequence=NEW.intent_sequence;
        END
    """)
