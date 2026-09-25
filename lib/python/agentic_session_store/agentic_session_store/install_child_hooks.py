"""Atomically install native child capture hooks in an explicitly selected config."""

from __future__ import annotations

import argparse
import fcntl
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

from agentic_session_store.child_journal import ChildJournal
from agentic_session_store.claude_hook_config import (
    merge_capture_hooks as merge_claude_hooks,
)
from agentic_session_store.codex_hook_config import merge_capture_hooks
from agentic_session_store.contract import SessionStoreContract

MAX_CONFIG_BYTES = 1024 * 1024


def _read(path: Path) -> tuple[bytes, int]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return b"", 0o600
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Configuration must be a regular file")
        content = stream.read(MAX_CONFIG_BYTES + 1)
        if len(content) > MAX_CONFIG_BYTES:
            raise ValueError("Configuration exceeds byte limit")
        return content, stat.S_IMODE(metadata.st_mode)


def install(path: Path, *, harness: str = "codex") -> bool:
    """Serialize cooperating installers; replace only a fully validated config.

    Existing invalid configuration remains untouched. An unchanged installation
    keeps the file's inode and timestamp. Config symlinks are never followed.
    """
    if harness not in {"codex", "claude"}:
        raise ValueError("Unsupported capture harness")
    if path.parent.is_symlink():
        raise ValueError("Configuration directory must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = os.open(
        path.with_name(path.name + ".capture.lock"),
        os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
        0o600,
    )
    temporary: str | None = None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        original, mode = _read(path)
        content = original.decode("utf-8")
        updated = (
            merge_claude_hooks(content)
            if harness == "claude"
            else merge_capture_hooks(content, config_path=path)
        ).encode("utf-8")
        if original == updated:
            return False
        descriptor, temporary = tempfile.mkstemp(
            prefix=".capture-config-", dir=path.parent
        )
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        # Detect non-cooperating edits observed before replacement.
        if _read(path) != (original, mode):
            raise ValueError("Configuration changed during installation")
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return True
    finally:
        if temporary is not None:
            os.unlink(temporary)
        os.close(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--harness", choices=("codex", "claude"), default="codex")
    args = parser.parse_args()
    try:
        # Installed hooks deny every launch without an active contract, so
        # installing them with capture disabled would block all children.
        if SessionStoreContract.from_env(os.environ) is None:
            raise ValueError("Capture hooks require an active session-store contract")
        if args.journal is not None:
            if args.journal.is_symlink():
                raise ValueError("Journal must not be a symlink")
            ChildJournal(args.journal)
        install(args.config, harness=args.harness)
    except (ValueError, TypeError, OSError, sqlite3.Error):
        print(
            "Child capture hook installation failed; check configuration and storage.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
