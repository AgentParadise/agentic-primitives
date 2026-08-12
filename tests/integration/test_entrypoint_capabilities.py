"""Integration tests for the generic capability registry entrypoint sections
5.6 + 5.7 (ADR-038).

Mirrors the pattern in test_entrypoint_memory.py — runs the real workspace
container with varying AGENTIC_CAPABILITIES / AGENTIC_<CAP>_* env vars and
asserts the entrypoint's loop behavior end-to-end.

See ADR-038 and docs/superpowers/sdd/2026-08-12-workspace-capability-modules/.
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

# The seshmagic adapter tests need a reachable live store (the doctor's
# store_reachable check hard-fails otherwise). STORE_URL is what the
# CONTAINER uses (host.docker.internal); the _FROM_HOST variant is what
# the test process itself uses to probe reachability before running any
# container, mirroring test_entrypoint_memory.py's hindsight-reachable
# pattern.
STORE_URL = os.getenv("SESSION_STORE_URL", "http://host.docker.internal:18091")
STORE_URL_FROM_HOST = os.getenv("SESSION_STORE_URL_FROM_HOST", "http://127.0.0.1:18091")


def _store_reachable() -> bool:
    """True if the live session-store's /healthz responds 200 from the host."""
    try:
        with urllib.request.urlopen(  # noqa: S310
            f"{STORE_URL_FROM_HOST}/healthz",
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
def test_capability_name_with_invalid_characters_is_skipped_not_fatal():
    """A malformed AGENTIC_CAPABILITIES entry (containing a dot) must be
    skipped like an unregistered one, not crash the entrypoint.

    __capability_provider_safe's charset (a-zA-Z0-9._-) is too wide for a
    *capability name*: "a.b" survives it, gets uppercased into a prefix
    like AGENTIC_A.B, and evaluating that as a shell parameter expansion is
    a bash bad substitution that kills the whole entrypoint under `set -e`.
    __capability_name_safe uses a narrower [a-z0-9-] charset to prevent this.
    """
    result = _run(
        ["echo", "agent reached"],
        env={"AGENTIC_CAPABILITIES": "memory a.b session-store"},
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "agent reached" in result.stdout
    assert "bad substitution" not in result.stderr


@pytest.mark.integration
def test_provider_set_for_unregistered_capability_warns_but_does_not_fail():
    """AGENTIC_MEMORY_PROVIDER set while AGENTIC_CAPABILITIES excludes
    "memory" must not silently vanish with no signal at all — warn to
    stderr. Not a hard fail: the operator may have deliberately narrowed
    AGENTIC_CAPABILITIES and left a stale *_PROVIDER var set.
    """
    result = _run(
        ["echo", "agent reached"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_MEMORY_PROVIDER": "hindsight",
        },
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "agent reached" in result.stdout
    assert "AGENTIC_MEMORY_PROVIDER" in result.stderr
    assert "warning" in result.stderr.lower()


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


@pytest.mark.integration
def test_exporter_absent_is_a_specific_doctor_failure():
    """A missing exporter must fail exporter_present ONLY, with a clear detail.

    AGENTIC_CAPABILITIES deliberately excludes "session-store" here. The
    default registry includes it, and once a seshmagic adapter exists
    (Task 6), setting AGENTIC_SESSION_STORE_PROVIDER makes the entrypoint's
    own section 5.7 preflight run this exact doctor invocation BEFORE the
    CMD below ever executes — and hard-exit on its failure, so the CMD
    (and its stdout, which this test needs to inspect) would never run.
    Excluding "session-store" from the registry skips that automatic
    preflight while still letting the doctor binary read
    AGENTIC_SESSION_STORE_* directly (the contract doesn't care whether its
    capability is registered — only the entrypoint's loop does), so this
    test's own CMD invocation is the only one and its JSON lands on stdout.
    """
    result = _run(
        ["/opt/agentic/capabilities/session-store/doctor", "--json"],
        env={
            "AGENTIC_CAPABILITIES": "memory",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": "http://unreachable.invalid",
        },
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    checks = {c["name"]: c for c in payload["checks"]}
    assert len(checks) == 5, "all five checks must run even when the binary is absent"
    assert checks["exporter_present"]["passed"] is False
    assert "SeshMagicSessionExporter" in checks["exporter_present"]["detail"]


@pytest.mark.integration
def test_mounted_exporter_satisfies_the_check(tmp_path: Path):
    """A binary provided at deploy time satisfies exporter_present.

    See test_exporter_absent_is_a_specific_doctor_failure for why
    AGENTIC_CAPABILITIES excludes "session-store": store_reachable still
    fails here (unreachable.invalid), so without this exclusion the
    entrypoint's own 5.7 preflight would hard-exit before the CMD below
    (whose stdout this test inspects) ever ran.
    """
    stub = Path("tests/integration/fixtures/stub-exporter").resolve()
    result = _run(
        ["/opt/agentic/capabilities/session-store/doctor", "--json"],
        env={
            "AGENTIC_CAPABILITIES": "memory",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": "http://unreachable.invalid",
        },
        extra_mounts=[f"{stub}:/usr/local/bin/SeshMagicSessionExporter:ro"],
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    checks = {c["name"]: c for c in payload["checks"]}
    assert checks["exporter_present"]["passed"] is True


# --- Task 6: the seshmagic adapter ------------------------------------------
#
# These tests need a reachable live store (the doctor's store_reachable
# check hard-fails otherwise), so they skip cleanly when one isn't
# available, exactly as test_entrypoint_memory.py skips on hindsight.

# Set from the host shell to a real, cross-built Linux exporter binary to
# exercise exporter_present with the real thing instead of the stub. Never
# hardcode a path to it here — it lives outside this repo and is not
# committed. Tests needing it skip cleanly when unset.
EXPORTER_BINARY_FROM_HOST = os.getenv("SESSION_STORE_EXPORTER_BINARY_FROM_HOST", "")

# Bearer token for the live store, read from the host shell's environment
# only — never hardcoded, never logged, never written to a file by this
# test. Tests needing it skip cleanly when unset.
STORE_AUTH_TOKEN = os.getenv("SESSION_STORE_AUTH_TOKEN_FROM_HOST", "")


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_adapter_translates_contract_and_creates_symlinks(tmp_path: Path):
    """Contract vars -> exporter env, and the ~/.claude|.codex symlinks land."""
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        [
            "bash", "-c",
            "echo CLAUDE_PROJECTS_ROOT=$CLAUDE_PROJECTS_ROOT; "
            "echo CODEX_SESSIONS_ROOT=$CODEX_SESSIONS_ROOT; "
            "echo EXPORTER_STATE_FILE=$EXPORTER_STATE_FILE; "
            "echo SESSION_STORE_TAGS=$SESSION_STORE_TAGS; "
            "echo ORIGIN_HOST_SET=${SESSION_STORE_ORIGIN_HOST:-unset}; "
            "readlink -f ~/.claude/projects; "
            "readlink -f ~/.codex/sessions",
        ],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_TAGS": "workflow:w1,phase:p2",
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "w1/p2",
        },
        # session-store stays registered here (unlike the exporter tests
        # above) because this test needs the adapter's init.sh (5.6) to
        # actually run. That means the entrypoint's own 5.7 doctor
        # preflight also runs and must fully pass or it hard-exits before
        # CMD; mount the stub so exporter_present passes too.
        extra_mounts=[
            f"{spool}:/spool",
            f"{Path('tests/integration/fixtures/stub-exporter').resolve()}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    out = result.stdout
    assert "CLAUDE_PROJECTS_ROOT=/spool/w1/p2/claude" in out
    assert "CODEX_SESSIONS_ROOT=/spool/w1/p2/codex" in out
    assert "EXPORTER_STATE_FILE=/spool/w1/p2/state.json" in out
    assert "SESSION_STORE_TAGS=workflow:w1,phase:p2" in out
    assert "ORIGIN_HOST_SET=unset" in out, "origin_host must never be set by the adapter"
    assert "/spool/w1/p2/claude" in out
    assert "/spool/w1/p2/codex" in out


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_symlink_replaces_preexisting_real_directory(tmp_path: Path):
    """A persisted $HOME with ~/.claude/projects as a REAL directory (e.g.
    Claude Code already ran there, or the volume survived a restart) must
    not break the adapter.

    Regression test for an IMPORTANT review finding: `ln -sfn` onto an
    existing real directory nests the symlink inside it instead of
    replacing it (~/.claude/projects/claude -> ...), and symlinks_correct
    then hard-fails the workspace with a confusing error. Every other test
    in this file uses the shared _run() helper's fresh --tmpfs HOME, which
    never exercises this path — this test deliberately bind-mounts a
    pre-populated $HOME instead, so it does not use _run().
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    (home / ".claude" / "projects" / "sentinel.txt").write_text("pre-existing real directory\n")
    (home / ".codex" / "sessions").mkdir(parents=True)
    # Docker Desktop's bind-mount layer does not reliably preserve host
    # uid/gid semantics the way a native Linux bind mount would; open the
    # perms up so the container's non-root agent user can rm/mkdir/symlink
    # here regardless of host uid. The behavior under test is the adapter's
    # own replace-don't-nest logic, not filesystem permission handling.
    os.chmod(home, 0o777)
    for p in home.rglob("*"):
        os.chmod(p, 0o777)

    stub = Path("tests/integration/fixtures/stub-exporter").resolve()
    cmd = [
        "docker", "run", "--rm",
        "--add-host=host.docker.internal:host-gateway",
        "-v", f"{home}:/home/agent",
        "-v", f"{spool}:/spool",
        "-v", f"{stub}:/usr/local/bin/SeshMagicSessionExporter:ro",
        "-e", "AGENTIC_CAPABILITIES=session-store",
        "-e", "AGENTIC_SESSION_STORE_PROVIDER=seshmagic",
        "-e", f"AGENTIC_SESSION_STORE_URL={STORE_URL}",
        "-e", "AGENTIC_SESSION_STORE_SPOOL=/spool",
        "-e", "AGENTIC_SESSION_STORE_PARTITION=w1/p2",
        IMAGE,
        "bash", "-c", "readlink -f ~/.claude/projects; readlink -f ~/.codex/sessions",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "/spool/w1/p2/claude" in result.stdout
    assert "/spool/w1/p2/codex" in result.stdout


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_capture_env_persisted_with_correct_mode(tmp_path: Path):
    """init.sh must persist tags to .capture-env (mode 600) for crash recovery.

    EXP-08 arm A5: a container SIGKILLed mid-capture leaves its partitioned
    spool on disk, but the environment (and SESSION_STORE_TAGS with it) dies
    with the process. A recovery sweep with no tags in its environment
    uploads the session unattributable. This test verifies the adapter's
    half of the fix: the opaque tag string lands next to the transcripts,
    mode 600, so a later sweep (Task 7's finalize.sh) can recover it.

    This does NOT exercise finalize.sh sourcing the file back in — that
    mechanism does not exist yet (Task 7). It verifies the artifact Task 7
    depends on is produced correctly.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        [
            "bash", "-c",
            "stat -c '%a' /spool/w1/p2/.capture-env; "
            "cat /spool/w1/p2/.capture-env",
        ],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_TAGS": "workflow:w1,phase:p2",
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "w1/p2",
        },
        # See test_adapter_translates_contract_and_creates_symlinks: the
        # adapter (5.6) must actually run, which means 5.7's doctor
        # preflight runs too and must fully pass (stub satisfies
        # exporter_present) or CMD never executes.
        extra_mounts=[
            f"{spool}:/spool",
            f"{Path('tests/integration/fixtures/stub-exporter').resolve()}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    # Equality, not substring: "600" in "1600" is also true, and would pass
    # on a mode this check must reject.
    assert result.stdout.splitlines()[0].strip() == "600"
    assert "SESSION_STORE_TAGS=workflow:w1,phase:p2" in result.stdout


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
@pytest.mark.parametrize(
    "tags",
    [
        pytest.param("workflow:w1,phase:p2", id="plain"),
        pytest.param("workflow:a b,phase:c", id="space"),
        pytest.param("workflow:$(touch /tmp/PWNED),phase:c", id="command-substitution"),
        pytest.param("workflow:it's,phase:c", id="single-quote"),
    ],
)
def test_capture_env_round_trips_tags_safely(tmp_path: Path, tags: str):
    """.capture-env must round-trip arbitrary opaque tag strings intact,
    with no shell execution, per the README's parse contract.

    Regression test for two Critical review findings:
    - sourcing .capture-env was arbitrary command execution on any tag
      string containing shell syntax, and silently truncated (and lost
      attribution for) any tag containing a space;
    - even sourced correctly, SESSION_STORE_TAGS was a bare shell
      variable that a CHILD process (the exporter) would never see.

    This exercises the documented safe consumer pattern directly (parse
    with `cut`, then `export`) rather than sourcing, and asserts a child
    process (not just the current shell) receives the exact original
    string, and that a command-substitution payload never executes.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        [
            "bash", "-c",
            # The documented parse contract: cut, never source.
            "export SESSION_STORE_TAGS=\"$(cut -d= -f2- < /spool/w1/p2/.capture-env)\"; "
            # Assert a CHILD process sees it (C2) — not just this shell.
            "sh -c 'printf \"CHILD_SAW=%s\\n\" \"$SESSION_STORE_TAGS\"'; "
            "env | grep -q '^SESSION_STORE_TAGS=' && echo IN_CHILD_ENV=yes; "
            "test -e /tmp/PWNED && echo INJECTION_OCCURRED || echo NO_INJECTION",
        ],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_TAGS": tags,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "w1/p2",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{Path('tests/integration/fixtures/stub-exporter').resolve()}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert f"CHILD_SAW={tags}" in result.stdout, result.stdout
    assert "IN_CHILD_ENV=yes" in result.stdout
    assert "NO_INJECTION" in result.stdout
    assert "INJECTION_OCCURRED" not in result.stdout


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
@pytest.mark.skipif(
    not EXPORTER_BINARY_FROM_HOST or not os.path.isfile(EXPORTER_BINARY_FROM_HOST),
    reason="SESSION_STORE_EXPORTER_BINARY_FROM_HOST not set to a real exporter binary",
)
@pytest.mark.skipif(not STORE_AUTH_TOKEN, reason="SESSION_STORE_AUTH_TOKEN_FROM_HOST not set")
def test_full_doctor_passes_with_real_exporter_and_live_store(tmp_path: Path):
    """End-to-end: real exporter binary + real reachable store + seshmagic
    adapter -> every doctor check passes. No stub, no mock.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        ["/opt/agentic/capabilities/session-store/doctor", "--json"],
        env={
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_AUTH": STORE_AUTH_TOKEN,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "e2e-test",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{EXPORTER_BINARY_FROM_HOST}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"doctor failed: {result.stdout} {result.stderr}"
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    checks = {c["name"]: c for c in payload["checks"]}
    assert len(checks) == 5
    for name, check in checks.items():
        assert check["passed"] is True, f"{name} failed: {check['detail']}"
