"""Additive child journal migration; existing change rows remain immutable."""

from __future__ import annotations

import sqlite3


def upgrade(connection: sqlite3.Connection) -> None:
    for table, additions in (
        (
            "child_intents",
            {"target_harness": "TEXT", "status": "TEXT", "exit_code": "INTEGER"},
        ),
        ("child_changes", {"status": "TEXT", "exit_code": "INTEGER"}),
    ):
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for name, kind in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
    # These triggers belong exclusively to this journal implementation.
    connection.execute("DROP TRIGGER IF EXISTS child_registered")
    connection.execute("DROP TRIGGER IF EXISTS child_bound")
    connection.execute("""
        CREATE TRIGGER child_registered AFTER INSERT ON child_intents
        BEGIN
            INSERT INTO child_changes (intent_sequence, child_native_id, status, exit_code)
            VALUES (NEW.sequence, NEW.child_native_id, NEW.status, NEW.exit_code);
        END
    """)
    connection.execute("""
        CREATE TRIGGER IF NOT EXISTS child_updated
        AFTER UPDATE OF child_native_id, status, exit_code ON child_intents
        WHEN OLD.child_native_id IS NOT NEW.child_native_id
          OR OLD.status IS NOT NEW.status OR OLD.exit_code IS NOT NEW.exit_code
        BEGIN
            INSERT INTO child_changes (intent_sequence, child_native_id, status, exit_code)
            VALUES (NEW.sequence, NEW.child_native_id, NEW.status, NEW.exit_code);
        END
    """)
