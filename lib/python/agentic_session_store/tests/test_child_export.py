"""The host-facing subprocess export must never synthesize missing evidence."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_session_store.child_journal import ChildCall, ChildJournal


def _export(path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "agentic_session_store.child_export",
            str(path),
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_read_only_export_preserves_file_and_reports_late_binding(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal ?#.sqlite"
    journal = ChildJournal(path)
    call = ChildCall("invocation", "attempt", "codex", "parent/α", "call")
    journal.register(call)
    before = path.read_bytes()
    exported = _export(path)
    assert exported.returncode == 0
    assert exported.stderr == ""
    assert path.read_bytes() == before
    document = json.loads(exported.stdout)
    assert document["schema_version"] == 1
    page = document["page"]
    assert page["changes"][0]["intent"]["call"]["parent_native_id"] == "parent/α"
    assert page["changes"][0]["intent"]["child_native_id"] is None
    journal.bind(call, "child/β")
    late = _export(path, "--after", str(page["watermark"]))
    changes = json.loads(late.stdout)["page"]["changes"]
    assert len(changes) == 1
    assert changes[0]["intent"]["child_native_id"] == "child/β"


@pytest.mark.parametrize("state", ["missing", "empty", "corrupt"])
def test_missing_or_invalid_journal_never_becomes_empty_success(
    tmp_path: Path, state: str
) -> None:
    path = tmp_path / "PRIVATE.sqlite"
    if state == "empty":
        path.touch()
    elif state == "corrupt":
        path.write_bytes(b"PRIVATE INVALID DATABASE")
    before = path.read_bytes() if path.exists() else None
    result = _export(path)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Child-session journal unavailable or invalid.\n"
    assert (path.read_bytes() if path.exists() else None) == before


def test_read_only_handle_rejects_mutation(tmp_path: Path) -> None:
    path = tmp_path / "journal.sqlite"
    journal = ChildJournal(path)
    call = ChildCall("invocation", "attempt", "codex", "parent", "call")
    journal.register(call)
    read_only = ChildJournal(path, read_only=True)
    with pytest.raises(sqlite3.OperationalError):
        read_only.bind(call, "child")
    assert journal.lookup(call).child_native_id is None
