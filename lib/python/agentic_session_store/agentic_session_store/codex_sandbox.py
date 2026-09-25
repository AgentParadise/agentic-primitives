"""Codex sandbox policy for delegated runs: which mode, and whether it can work.

The workspace entrypoint probes ``codex sandbox`` once at startup and writes
the verdict to a status file. A delegate reads that verdict instead of
launching Codex into a sandbox that cannot start: Codex exits 0 even when
every shell tool call fails inside a broken sandbox, so a run that would
record "completed" having done nothing is refused up front instead.

Modes that disable Codex's own sandbox are rejected, never passed through.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

SANDBOX_MODE_ENV = "AGENTIC_DELEGATE_CODEX_SANDBOX"
STATUS_PATH_ENV = "AGENTIC_CODEX_SANDBOX_STATUS"
DEFAULT_STATUS_PATH = Path("/var/agentic/codex-sandbox.json")
STATUS_SCHEMA_VERSION = 1
MAX_STATUS_BYTES = 64 * 1024


class CodexSandboxMode(StrEnum):
    """Codex ``--sandbox`` values a delegate may request."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"


DEFAULT_SANDBOX_MODE = CodexSandboxMode.WORKSPACE_WRITE

# Values that turn Codex's sandbox off. Named so the refusal is explicit
# rather than an "unknown value" that invites someone to add it.
FORBIDDEN_SANDBOX_MODES = frozenset({"danger-full-access", "external-sandbox"})


def parse_sandbox_mode(value: str | None) -> CodexSandboxMode:
    """Validate a requested sandbox mode; empty or absent means the default."""
    if value is None or not value.strip():
        return DEFAULT_SANDBOX_MODE
    candidate = value.strip()
    if candidate in FORBIDDEN_SANDBOX_MODES:
        raise ValueError(
            f"Codex sandbox mode {candidate!r} disables the sandbox and is not allowed"
        )
    try:
        return CodexSandboxMode(candidate)
    except ValueError:
        allowed = ", ".join(mode.value for mode in CodexSandboxMode)
        raise ValueError(
            f"Unknown Codex sandbox mode {candidate!r}; expected one of: {allowed}"
        ) from None


def resolve_sandbox_mode(
    requested: str | None, environment: Mapping[str, str]
) -> CodexSandboxMode:
    """Command-line value wins over ``AGENTIC_DELEGATE_CODEX_SANDBOX``."""
    return parse_sandbox_mode(
        requested if requested is not None else environment.get(SANDBOX_MODE_ENV)
    )


@dataclass(frozen=True)
class CodexSandboxStatus:
    """Startup probe verdict. Absent or unreadable means unavailable."""

    available: bool
    detail: str


def status_path(environment: Mapping[str, str]) -> Path:
    configured = environment.get(STATUS_PATH_ENV)
    return Path(configured) if configured else DEFAULT_STATUS_PATH


def read_status(path: Path) -> CodexSandboxStatus:
    """Read the entrypoint's probe record, failing closed on anything odd."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_STATUS_BYTES + 1)
    except FileNotFoundError:
        return CodexSandboxStatus(False, f"no sandbox probe record at {path}")
    except OSError as error:
        return CodexSandboxStatus(
            False, f"sandbox probe record unreadable: {error.strerror}"
        )
    if len(raw) > MAX_STATUS_BYTES:
        return CodexSandboxStatus(False, "sandbox probe record is too large")
    try:
        document: object = json.loads(raw)
    except (ValueError, UnicodeError):
        return CodexSandboxStatus(False, "sandbox probe record is not valid JSON")
    if not isinstance(document, dict):
        return CodexSandboxStatus(False, "sandbox probe record is not an object")
    version = document.get("schema_version")
    available = document.get("available")
    detail = document.get("detail")
    if version != STATUS_SCHEMA_VERSION or not isinstance(available, bool):
        return CodexSandboxStatus(False, "sandbox probe record has an unknown shape")
    text = detail if isinstance(detail, str) else ""
    return CodexSandboxStatus(available, text[:500])
