"""Bounded native identity lookup for Codex 0.156.1 task-path spawn replies."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

MAX_HEADER_BYTES = 1024 * 1024
MAX_SCAN_ENTRIES = 4096


def _header(path: Path) -> dict[str, object]:
    with path.open("rb") as source:
        line = source.readline(MAX_HEADER_BYTES + 1)
    if len(line) > MAX_HEADER_BYTES:
        raise ValueError("Codex header exceeds limit")
    row = json.loads(line)
    if not isinstance(row, dict) or row.get("type") != "session_meta":
        raise ValueError("Canonical Codex header missing")
    meta = row.get("payload")
    if not isinstance(meta, dict):
        raise TypeError("Canonical Codex header invalid")
    return meta


def parent_identity(
    event: Mapping[str, object], environment: Mapping[str, str]
) -> tuple[str, Path]:
    root = (
        Path(environment.get("CODEX_HOME", str(Path.home() / ".codex"))) / "sessions"
    ).resolve()
    transcript = event.get("transcript_path")
    if not isinstance(transcript, str):
        raise TypeError("Parent transcript path missing")
    path = Path(transcript).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Parent transcript outside session root")
    meta = _header(path)
    identity = meta.get("id")
    if not isinstance(identity, str) or not identity:
        raise ValueError("Parent native identity missing")
    if (meta.get("session_id") or identity) != event.get("session_id"):
        raise ValueError("Hook root does not match parent header")
    return identity, root


def child_identity(root: Path, parent: str, task_path: object) -> str:
    if not isinstance(task_path, str) or not task_path.startswith("/root/"):
        raise ValueError("Invalid native child task path")
    found: set[str] = set()
    inspected = 0
    for directory, directories, files in os.walk(root, followlinks=False):
        inspected += len(directories) + len(files)
        if inspected > MAX_SCAN_ENTRIES:
            raise ValueError("Codex session scan exceeds limit")
        for name in files:
            path = Path(directory) / name
            if path.suffix != ".jsonl" or path.is_symlink():
                continue
            meta = _header(path)
            if (
                meta.get("multi_agent_version") != "v2"
                or meta.get("agent_path") != task_path
            ):
                continue
            if meta.get("parent_thread_id") != parent:
                continue
            identity = meta.get("id")
            if not isinstance(identity, str) or not identity or identity == parent:
                raise ValueError("Invalid child native identity")
            found.add(identity)
    if len(found) != 1:
        raise ValueError("Child native identity missing or ambiguous")
    return found.pop()
