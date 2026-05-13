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
@pytest.mark.skipif(not _hindsight_reachable(), reason="hindsight backend unreachable")
def test_config_json_writes_claude_code_config(tmp_path: Path):
    """`AGENTIC_MEMORY_CONFIG_JSON` is written verbatim to
    ~/.hindsight/claude-code.json by the hindsight adapter. This is the
    contract path agentic-domain-runner relies on to ship per-domain
    `recallAdditionalBanks` (verified e2e in agentic-memory's
    multi-bank-task-plus-domain experiment)."""
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()

    payload = json.dumps({
        "llmProvider": "claude-code",
        "dynamicBankId": False,
        "bankId": "config-json-test",
        "recallAdditionalBanks": ["shared-domain-bank"],
    })

    result = _run(
        [
            "bash", "-c",
            "echo agent reached; "
            "echo CONFIG_FILE_CONTENTS=$(cat /home/agent/.hindsight/claude-code.json)",
        ],
        env={
            "AGENTIC_MEMORY_PROVIDER": "hindsight",
            "AGENTIC_MEMORY_NAMESPACE": "config-json-test",
            "AGENTIC_MEMORY_URL": "http://host.docker.internal:9077",
            "AGENTIC_MEMORY_CONFIG_JSON": payload,
        },
        extra_mounts=[f"{audit_dir}:/var/agentic/memory-doctor"],
        add_host_gateway=True,
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "agent reached" in result.stdout

    # Extract the contents and parse — the test passes only if the file's
    # JSON round-trips byte-for-byte through the adapter.
    line = next(
        ln for ln in result.stdout.splitlines()
        if ln.startswith("CONFIG_FILE_CONTENTS=")
    )
    written = json.loads(line.removeprefix("CONFIG_FILE_CONTENTS="))
    assert written == json.loads(payload), (
        "adapter must write AGENTIC_MEMORY_CONFIG_JSON verbatim to "
        f"~/.hindsight/claude-code.json; got: {written}"
    )


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


# -----------------------------------------------------------------------------
# CROSS-SESSION test (the headline).
#
# Two separate container starts share a bank through AGENTIC_MEMORY_NAMESPACE.
# Session 1 establishes a fact; session 2 (brand-new container) recalls it.
# Session 3 with a different namespace verifies isolation.
#
# Requires:
#   - hindsight backend reachable at host.docker.internal:9077
#   - CLAUDE_CODE_OAUTH_TOKEN env var set in the host shell (provides
#     auth for claude inside the container)
#   - The hindsight plugin source available at $HINDSIGHT_PLUGIN_SRC
#     (defaults to ../agentic-memory/lib/hindsight/hindsight-integrations/claude-code/)
#
# Skipped when any precondition is missing.
# -----------------------------------------------------------------------------


HINDSIGHT_PLUGIN_SRC = os.getenv(
    "HINDSIGHT_PLUGIN_SRC",
    "/Users/neural/Code/AgentParadise/agentic-memory/lib/hindsight/hindsight-integrations/claude-code",
)


def _claude_in_container_preconditions_met() -> tuple[bool, str]:
    """Return (ok, reason) for whether we can run the cross-session test."""
    if not _hindsight_reachable():
        return False, "hindsight backend unreachable"
    if not os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
        return False, "CLAUDE_CODE_OAUTH_TOKEN not set"
    if not Path(HINDSIGHT_PLUGIN_SRC, ".claude-plugin", "plugin.json").is_file():
        return False, f"hindsight plugin source not found at {HINDSIGHT_PLUGIN_SRC}"
    return True, ""


@pytest.mark.integration
def test_cross_session_recall_via_namespace(tmp_path: Path):
    """Two fresh containers share a bank via AGENTIC_MEMORY_NAMESPACE.

    Session 1 plants a verbatim, unguessable fact in the conversation
    (a fictional code-named DB on an unusual schema version). Session 2,
    in a brand-new container, asks claude what that fact was. The
    answer must contain the fictional name to prove cross-session
    memory retrieval — Claude has no way to know the name except via
    the hindsight bank we wrote to from session 1.

    Skipped when CLAUDE_CODE_OAUTH_TOKEN is missing or the hindsight
    backend is unreachable.
    """
    ok, reason = _claude_in_container_preconditions_met()
    if not ok:
        pytest.skip(reason)

    namespace = f"itest-cross-session-{os.urandom(4).hex()}"
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()

    # Stage the workspace injection: real copy (not symlink) so docker mount works.
    workspace_dir = tmp_path / "workspace"
    plugins_dir = workspace_dir / "plugins"
    plugins_dir.mkdir(parents=True)
    subprocess.run(
        ["cp", "-R", HINDSIGHT_PLUGIN_SRC, str(plugins_dir / "hindsight-memory")],
        check=True,
    )
    (workspace_dir / "CLAUDE.md").write_text("# Integration test workspace\n")

    def _run_claude_session(ns: str, prompt: str) -> subprocess.CompletedProcess:
        """Run one claude session in the workspace image with all the contract
        env vars wired up. Returns the completed process. Critically: NEVER
        embed the OAuth token in the args list — pass it through the parent
        env using `docker run -e CLAUDE_CODE_OAUTH_TOKEN` (no `=value`), so
        pytest assertion failures never leak it via CompletedProcess.args."""
        cmd = [
            "docker", "run", "--rm",
            "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000",
            "--add-host=host.docker.internal:host-gateway",
            "-v", f"{audit_dir}:/var/agentic/memory-doctor",
            "-v", f"{workspace_dir}:/etc/agentic/workspace:ro",
            # CRITICAL: no `=value` here. Docker pulls the value from the
            # parent process's env. The token is never in argv.
            "-e", "CLAUDE_CODE_OAUTH_TOKEN",
            "-e", "AGENTIC_WORKSPACE_PLUGINS=hindsight-memory",
            "-e", "AGENTIC_MEMORY_PROVIDER=hindsight",
            "-e", f"AGENTIC_MEMORY_NAMESPACE={ns}",
            "-e", "AGENTIC_MEMORY_URL=http://host.docker.internal:9077",
            "-e", f"HINDSIGHT_USER_ID=itest-{ns}",
            IMAGE,
            "sh", "-c",
            'exec claude -p --dangerously-skip-permissions $AGENTIC_PLUGIN_FLAGS "$@"',
            "_",  # sh -c $0 sentinel — required so $@ binds correctly
            prompt,
        ]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=180)

    # Session 1: plant a fact with an unguessable fictional name.
    seed = _run_claude_session(
        namespace,
        "Important context for this task: we use the database name "
        "'crimson-vault' on schema version '17.3.2-beta'. "
        "Acknowledge you'll remember this for future sessions.",
    )
    # Custom assertions — bare assert pre-formatted message so pytest's
    # auto-print of CompletedProcess fields doesn't expose anything sensitive.
    if seed.returncode != 0:
        # Don't print stderr in the failure message — it could contain secrets
        # if anything ever changes. Tail-only.
        pytest.fail(f"session 1 exited {seed.returncode}; stderr last line: {seed.stderr.strip().splitlines()[-1:] }")
    assert "crimson-vault" in seed.stdout

    # Allow async retain + consolidation to complete.
    import time as _time
    _time.sleep(30)

    # Session 2: fresh container, same namespace, recall question. The
    # fictional name must surface in the response — claude can only know it
    # via the hindsight bank.
    recall = _run_claude_session(
        namespace,
        "What database name and schema version are we using for this task? "
        "Answer concisely.",
    )
    if recall.returncode != 0:
        pytest.fail(f"session 2 exited {recall.returncode}")
    assert "crimson-vault" in recall.stdout, (
        "session 2 did not recall the fictional db name; "
        f"got: {recall.stdout[-200:]}"
    )

    # Session 3: different namespace — must NOT recall.
    different_namespace = f"itest-isolation-{os.urandom(4).hex()}"
    isolation = _run_claude_session(
        different_namespace,
        "What database name and schema version are we using for this task? "
        "Answer concisely.",
    )
    if isolation.returncode != 0:
        pytest.fail(f"session 3 exited {isolation.returncode}")
    assert "crimson-vault" not in isolation.stdout.lower(), (
        "isolation breach: different namespace recalled the fact; "
        f"got: {isolation.stdout[-200:]}"
    )

    # Cleanup: delete the banks so the daemon doesn't accumulate test banks.
    for ns in (namespace, different_namespace):
        bank_url = f"{HINDSIGHT_BACKEND_URL}/v1/default/banks/{ns}"
        try:
            req = urllib.request.Request(bank_url, method="DELETE")  # noqa: S310
            urllib.request.urlopen(req, timeout=5)  # noqa: S310
        except (urllib.error.URLError, OSError):
            pass
