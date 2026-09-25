"""Prove an installed capture hook reaches its guard in this environment.

Run with ``python -m agentic_session_store.hook_probe``. A shell startup file
runs before the hook command, so the guard cannot protect against one that
exits or hangs: the harness would see a non-blocking failure and launch the
child. This probe runs the real guarded command through the same shells the
pinned harnesses use, with the caller's environment, and fails closed unless:

* a payload the recorder must reject returns exactly the guard's deny status
  and message (the guard ran; a startup file that exits 0 or prints fails);
* a capture probe payload returns 0 with no output (interpreter, package,
  active contract and journal schema all reachable).

Shells, verified against the pinned binaries (see
docs/native-child-hook-contract.md):

* Claude Code 2.1.281: ``/bin/sh -c``.
* Codex 0.156.1 ``codex exec``: the user's passwd shell with ``-c``, whatever
  ``$SHELL`` says. Codex only falls back to ``$SHELL -lc`` when a session has
  no turn environment; that path is not probed. The workspace images keep
  ``/opt/venv/bin`` on PATH for login shells (``/etc/profile.d``); without it
  the guard there finds no ``python3`` and denies every spawn (closed).
"""

from __future__ import annotations

import argparse
import json
import os
import pwd
import subprocess
import sys
from collections.abc import Mapping, Sequence

from agentic_session_store.hook_command import (
    DENY_STATUS,
    FAILURE_MESSAGE,
    HARNESS_TIMEOUT_SECONDS,
    HookHarness,
    guarded_command,
)

REJECTED_PAYLOAD = b"agentic-capture-probe: not a hook payload"
ACCEPTED_PAYLOAD = json.dumps({"hook_event_name": "AgenticCaptureProbe"}).encode()


class CaptureProbeError(RuntimeError):
    """The capture hook guard is not reachable in this environment."""


def hook_shells(harness: HookHarness) -> list[tuple[str, ...]]:
    if harness is HookHarness.CLAUDE:
        return [("/bin/sh", "-c")]
    return [(pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh", "-c")]


def _run(
    argv: Sequence[str],
    payload: bytes,
    environment: Mapping[str, str],
    timeout: float,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(argv),
            input=payload,
            env=dict(environment),
            capture_output=True,
            timeout=timeout,
            check=False,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CaptureProbeError("Capture hook shell did not complete") from error


def probe_guard(
    harness: HookHarness,
    environment: Mapping[str, str],
    *,
    shells: Sequence[tuple[str, ...]] | None = None,
    timeout: float = HARNESS_TIMEOUT_SECONDS,
) -> None:
    command = guarded_command(harness, deny=True)
    for shell in hook_shells(harness) if shells is None else shells:
        denied = _run((*shell, command), REJECTED_PAYLOAD, environment, timeout)
        if (denied.returncode, denied.stdout, denied.stderr) != (
            DENY_STATUS,
            b"",
            FAILURE_MESSAGE.encode() + b"\n",
        ):
            raise CaptureProbeError("Capture hook guard not reached")
        accepted = _run((*shell, command), ACCEPTED_PAYLOAD, environment, timeout)
        if (accepted.returncode, accepted.stdout, accepted.stderr) != (0, b"", b""):
            raise CaptureProbeError("Capture hook recorder unavailable")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--harness",
        action="append",
        choices=[h.value for h in HookHarness],
        help="Harness to probe (repeatable; default: all)",
    )
    args = parser.parse_args(argv)
    harnesses = [HookHarness(h) for h in args.harness or [h.value for h in HookHarness]]
    try:
        for harness in harnesses:
            probe_guard(harness, os.environ)
    except CaptureProbeError:
        print(
            "Capture hook probe failed: a child launch could proceed without a "
            "durable intent. Check the shell startup files and python3.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
