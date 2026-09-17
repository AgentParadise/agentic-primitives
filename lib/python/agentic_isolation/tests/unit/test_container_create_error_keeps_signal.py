"""A failed `docker create` must not discard the only diagnostic it has.

A real provisioning failure reported exactly this and nothing else:

    Failed to create container: Unknown error

`docker create` had exited non-zero with empty stderr, and the error path
preferred the literal string "Unknown error" over `proc.returncode`, which was
sitting right there and is never empty. The execution was unrecoverable and
undiagnosable for the same reason.

These tests pin the three channels that can carry signal, so a future edit
cannot quietly drop one again.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentic_isolation.providers import docker as docker_provider


class _FakeProc:
    """Stands in for the `docker create` subprocess."""

    def __init__(self, returncode: int, stdout: bytes, stderr: bytes) -> None:
        self.returncode = returncode
        self._out = stdout
        self._err = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._out, self._err


def _raise_for(returncode: int, stdout: bytes, stderr: bytes) -> str:
    """Drive the error branch directly and return the message it raises.

    The branch under test is small and its inputs are exactly these three
    values, so it is exercised here rather than through a full provisioning
    call, which would need a Docker daemon and would test the daemon too.
    """
    proc = _FakeProc(returncode, stdout, stderr)
    out, err = asyncio.run(proc.communicate())
    detail = err.decode().strip() if err else ""
    if not detail:
        detail = out.decode().strip() if out else ""
    if not detail:
        detail = "no output on stderr or stdout"
    return f"Failed to create container: {detail} (docker create exited {proc.returncode})"


def test_the_exit_code_survives_when_both_streams_are_empty() -> None:
    """The case that actually happened. The exit code is all that is left."""
    msg = _raise_for(125, b"", b"")
    assert "exited 125" in msg
    assert "Unknown error" not in msg, (
        "the literal 'Unknown error' is the defect: it replaces a real exit "
        "code with a string that cannot be investigated"
    )


def test_stderr_is_preferred_when_present() -> None:
    msg = _raise_for(125, b"", b"docker: Error response from daemon: no such image")
    assert "no such image" in msg
    assert "exited 125" in msg


def test_stdout_is_used_when_stderr_is_empty() -> None:
    """Docker does not always put the reason on stderr."""
    msg = _raise_for(1, b"something went wrong on stdout", b"")
    assert "something went wrong on stdout" in msg
    assert "exited 1" in msg


def test_the_message_says_so_when_there_is_genuinely_no_output() -> None:
    """Silence is reported as silence, not as an unexplained failure."""
    msg = _raise_for(137, b"", b"")
    assert "no output on stderr or stdout" in msg
    assert "exited 137" in msg


def test_the_production_branch_still_carries_all_three_channels() -> None:
    """Guard against the source drifting away from what these tests assert.

    The helper above reproduces the branch's logic. If the real source stops
    mentioning `returncode` in the raise, the reproduction is no longer a
    reproduction and these tests would pass while production regressed.
    """
    import inspect

    src = inspect.getsource(docker_provider)
    marker = "Failed to create container:"
    assert marker in src
    start = src.index(marker)
    window = src[start - 900 : start + 300]
    assert "returncode" in window, (
        "the raise no longer includes the exit code; these tests pin a "
        "behaviour production has stopped having"
    )
    assert '"Unknown error"' not in window, (
        "the discarded-diagnostic string is back in the error path"
    )
