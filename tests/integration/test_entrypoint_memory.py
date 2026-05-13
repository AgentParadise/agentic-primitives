"""Integration tests for the memory primitive entrypoint sections 5.6 + 5.7.

Mirrors the pattern in test_entrypoint_workspace_injection.py — runs the
real workspace container with varying AGENTIC_MEMORY_* env vars and
asserts the doctor behavior end-to-end.

Some tests require a running hindsight backend reachable at
host.docker.internal:9077. They are skipped when the backend is
unreachable; you can spin one up via either:

    uvx hindsight-embed@latest daemon --profile claude-code start

Or via the agentic-memory repo's docker compose stack.

See ADR-036 + spec 2026-05-13-memory-primitive-and-doctor-design.md.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

IMAGE = os.getenv("AGENTIC_WORKSPACE_IMAGE", "agentic-workspace-claude-cli:latest")
HINDSIGHT_BACKEND_URL = os.getenv(
    "HINDSIGHT_BACKEND_URL_FROM_HOST",
    "http://127.0.0.1:9077",
)


def _hindsight_reachable() -> bool:
    """True if the hindsight backend's /health responds 200 from the host."""
    try:
        with urllib.request.urlopen(  # noqa: S310
            f"{HINDSIGHT_BACKEND_URL}/health",
            timeout=2,
        ) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _run(
    args: list[str],
    env: dict[str, str] | None = None,
    extra_mounts: list[str] | None = None,
    add_host_gateway: bool = False,
) -> subprocess.CompletedProcess:
    """Run the workspace image with tmpfs home, optional env / mounts."""
    cmd = [
        "docker", "run", "--rm",
        "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000",
    ]
    if add_host_gateway:
        cmd.extend(["--add-host=host.docker.internal:host-gateway"])
    for m in extra_mounts or []:
        cmd.extend(["-v", m])
    for k, v in (env or {}).items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.append(IMAGE)
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


@pytest.mark.integration
def test_no_provider_is_noop():
    """When AGENTIC_MEMORY_PROVIDER is unset, sections 5.6 + 5.7 do nothing."""
    result = _run(["echo", "agent reached"])
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "agent reached" in result.stdout
    assert "memory doctor" not in result.stderr
    assert "memory adapter" not in result.stderr


@pytest.mark.integration
@pytest.mark.skipif(not _hindsight_reachable(), reason="hindsight backend unreachable")
def test_provider_with_reachable_backend_passes(tmp_path: Path):
    """Reachable backend + valid env → doctor passes, adapter sets HINDSIGHT_*."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()

    result = _run(
        [
            "bash", "-c",
            "echo agent reached; "
            "echo HINDSIGHT_BANK_ID=$HINDSIGHT_BANK_ID; "
            "echo HINDSIGHT_API_URL=$HINDSIGHT_API_URL; "
            "echo HINDSIGHT_DYNAMIC_BANK_ID=$HINDSIGHT_DYNAMIC_BANK_ID; "
            "echo AGENTIC_MEMORY_READY=$AGENTIC_MEMORY_READY",
        ],
        env={
            "AGENTIC_MEMORY_PROVIDER": "hindsight",
            "AGENTIC_MEMORY_NAMESPACE": "integration-test-pass",
            "AGENTIC_MEMORY_URL": "http://host.docker.internal:9077",
        },
        extra_mounts=[f"{audit_dir}:/var/agentic/memory-doctor"],
        add_host_gateway=True,
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    combined = result.stdout + result.stderr
    assert "agent reached" in result.stdout
    assert "HINDSIGHT_BANK_ID=integration-test-pass" in result.stdout
    assert "HINDSIGHT_API_URL=http://host.docker.internal:9077" in result.stdout
    assert "HINDSIGHT_DYNAMIC_BANK_ID=false" in result.stdout
    assert "AGENTIC_MEMORY_READY=1" in result.stdout
    # Entrypoint log lines go to stdout (matches existing entrypoint convention)
    assert "memory doctor: pass" in combined
    assert "memory adapter: hindsight" in combined

    audit_files = list(audit_dir.glob("*.jsonl"))
    assert len(audit_files) == 1
    payload = json.loads(audit_files[0].read_text().splitlines()[-1])
    assert payload["status"] == "ok"
    assert payload["exit_code"] == 0
    assert payload["provider"] == "hindsight"


@pytest.mark.integration
def test_provider_with_unreachable_backend_hard_fails():
    """Backend unreachable → doctor exits 1; container does NOT reach CMD."""
    result = _run(
        ["echo", "should not reach here"],
        env={
            "AGENTIC_MEMORY_PROVIDER": "hindsight",
            "AGENTIC_MEMORY_NAMESPACE": "bad-backend-test",
            "AGENTIC_MEMORY_URL": "http://nonexistent.invalid:9999",
        },
    )

    assert result.returncode != 0
    assert "should not reach here" not in result.stdout
    # FAIL log message goes to stderr per the entrypoint section 5.7
    assert "memory doctor: FAIL" in result.stdout + result.stderr


@pytest.mark.integration
def test_provider_with_missing_namespace_hard_fails():
    """env_contract check catches missing required vars."""
    result = _run(
        ["echo", "should not reach here"],
        env={
            "AGENTIC_MEMORY_PROVIDER": "hindsight",
            "AGENTIC_MEMORY_URL": "http://host.docker.internal:9077",
        },
        add_host_gateway=True,
    )

    assert result.returncode != 0
    assert "should not reach here" not in result.stdout


@pytest.mark.integration
def test_unknown_provider_hard_fails():
    """provider_known check catches typo'd provider names."""
    result = _run(
        ["echo", "should not reach here"],
        env={
            "AGENTIC_MEMORY_PROVIDER": "nonexistent-provider",
            "AGENTIC_MEMORY_NAMESPACE": "x",
            "AGENTIC_MEMORY_URL": "http://host.docker.internal:9077",
        },
        add_host_gateway=True,
    )

    assert result.returncode != 0
    assert "should not reach here" not in result.stdout


@pytest.mark.integration
@pytest.mark.skipif(not _hindsight_reachable(), reason="hindsight backend unreachable")
def test_auto_fix_stale_dynamic_bank_id(tmp_path: Path):
    """Stale ~/.hindsight/claude-code.json with dynamicBankId:true is
    auto-rewritten to false. The HINDSIGHT_BANK_ID env var the adapter
    exports would otherwise be silently ignored by the hindsight plugin."""
    home = tmp_path / "agent-home"
    home.mkdir()
    config = home / "claude-code.json"
    config.write_text(json.dumps({
        "dynamicBankId": True,
        "dynamicBankGranularity": ["project"],
        "stale_marker": "should-be-preserved",
    }))

    result = _run(
        ["echo", "agent reached"],
        env={
            "AGENTIC_MEMORY_PROVIDER": "hindsight",
            "AGENTIC_MEMORY_NAMESPACE": "test-autofix",
            "AGENTIC_MEMORY_URL": "http://host.docker.internal:9077",
        },
        extra_mounts=[f"{home}:/home/agent/.hindsight"],
        add_host_gateway=True,
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "agent reached" in result.stdout

    rewritten = json.loads(config.read_text())
    assert rewritten["dynamicBankId"] is False
    assert rewritten["stale_marker"] == "should-be-preserved"


@pytest.mark.integration
def test_doctor_binary_runs_without_provider():
    """`/opt/agentic/memory/doctor` invoked with no provider is a no-op (exit 0)."""
    result = _run(["/opt/agentic/memory/doctor"])
    assert result.returncode == 0
    assert "not opted in" in result.stderr.lower() or "no checks run" in result.stderr.lower()


@pytest.mark.integration
def test_doctor_binary_json_output():
    """--json emits machine-readable output on stdout."""
    result = _run(
        [
            "/opt/agentic/memory/doctor",
            "--json",
            "--provider", "nonexistent-provider",
            "--namespace", "test",
            "--url", "http://nonexistent.invalid:9999",
        ],
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["status"] == "fail"
    assert payload["exit_code"] == 1
    assert any(c["name"] == "provider_known" and c["status"] == "fail" for c in payload["checks"])
