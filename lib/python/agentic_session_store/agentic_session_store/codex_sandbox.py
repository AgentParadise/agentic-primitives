"""Codex sandbox policy for delegated runs: which mode, and whether it works.

Codex exits 0 even when every shell tool call fails inside a sandbox that
cannot start, so a delegate that did nothing would be recorded as completed.
syn-delegate therefore probes the sandbox itself, live, with the exact mode,
working directory and environment the delegate will use, and refuses to
launch when the probe fails. There is no status file to trust or forge.

This is a reliability guard, not a security boundary: an agent can always run
``codex`` directly. The boundary is the container's seccomp and AppArmor
policy, which the probe only observes.

Modes that disable Codex's own sandbox are rejected, never passed through.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

SANDBOX_MODE_ENV = "AGENTIC_DELEGATE_CODEX_SANDBOX"
PROBE_TIMEOUT_SECONDS = 30.0


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
    """Probe verdict. Anything but a clean exit means unavailable."""

    available: bool
    detail: str


def probe(
    mode: CodexSandboxMode,
    *,
    environment: Mapping[str, str],
    cwd: str | None = None,
    timeout: float = PROBE_TIMEOUT_SECONDS,
) -> CodexSandboxStatus:
    """Run ``codex sandbox`` in ``mode`` exactly as the delegate will run."""
    command = ["codex", "sandbox", "-c", f'sandbox_mode="{mode.value}"', "--", "true"]
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            env=dict(environment),
            cwd=cwd,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return CodexSandboxStatus(False, "codex is not installed")
    except subprocess.TimeoutExpired:
        return CodexSandboxStatus(
            False, f"codex sandbox probe timed out after {timeout:g}s"
        )
    except OSError as error:
        return CodexSandboxStatus(
            False, f"codex sandbox probe could not start: {error.strerror}"
        )
    if result.returncode == 0:
        return CodexSandboxStatus(True, f"codex sandbox {mode.value} probe passed")
    lines = [line for line in result.stderr.splitlines() if line.strip()]
    cause = next((line for line in lines if "bwrap" in line or "rror" in line), None)
    detail = (cause or (lines[-1] if lines else "no output")).strip()[:300]
    return CodexSandboxStatus(False, f"probe exit {result.returncode}: {detail}")
