"""Integration tests for the generic capability registry entrypoint sections
5.6 + 5.7 (ADR-038).

Mirrors the pattern in test_entrypoint_memory.py — runs the real workspace
container with varying AGENTIC_CAPABILITIES / AGENTIC_<CAP>_* env vars and
asserts the entrypoint's loop behavior end-to-end.

See ADR-038 and docs/superpowers/sdd/2026-08-12-workspace-capability-modules/.
"""

from __future__ import annotations

import os
import subprocess

import pytest

IMAGE = os.getenv("AGENTIC_WORKSPACE_IMAGE", "agentic-workspace-claude-cli:latest")


def _run(
    args: list[str],
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run the workspace image with tmpfs home and optional env."""
    cmd = [
        "docker", "run", "--rm",
        "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000",
    ]
    for k, v in (env or {}).items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.append(IMAGE)
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


@pytest.mark.integration
def test_unknown_capability_in_registry_is_skipped_not_fatal():
    """A registry entry with no provider env set must be a silent no-op."""
    result = _run(
        ["echo", "agent reached"],
        env={"AGENTIC_CAPABILITIES": "memory session-store bogus"},
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "agent reached" in result.stdout


@pytest.mark.integration
def test_capability_provider_name_cannot_escape_capabilities_dir():
    """Path traversal in a provider name must be rejected, not sourced."""
    result = _run(
        ["echo", "agent reached"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "../../../workspace/evil",
            "AGENTIC_SESSION_STORE_URL": "http://unused.invalid",
        },
    )
    assert "invalid" in result.stderr.lower()
    assert "/workspace/evil" not in result.stderr


@pytest.mark.integration
def test_memory_still_works_at_new_path():
    """The migration must not change memory's observable behavior.

    An unknown provider already hard-fails today (the 5.7 doctor's
    provider_known check). tests/integration/test_entrypoint_memory.py
    ::test_unknown_provider_hard_fails asserts exactly this. The
    capability loop must preserve it.
    """
    result = _run(
        ["echo", "should not reach here"],
        env={"AGENTIC_MEMORY_PROVIDER": "nonexistent-provider"},
    )
    assert result.returncode != 0
    assert "should not reach here" not in result.stdout
