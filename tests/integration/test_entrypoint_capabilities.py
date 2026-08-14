"""Integration tests for the generic capability registry entrypoint sections
5.6 + 5.7 (ADR-040).

Mirrors the pattern in test_entrypoint_memory.py — runs the real workspace
container with varying AGENTIC_CAPABILITIES / AGENTIC_<CAP>_* env vars and
asserts the entrypoint's loop behavior end-to-end.

See ADR-040 and docs/superpowers/sdd/2026-08-12-workspace-capability-modules/.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
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

# For the "provider set, finalize.sh missing" regression test, which needs a
# capability whose provider adapter genuinely has no finalize.sh: memory's
# hindsight adapter. Mirrors test_entrypoint_memory.py's own reachability
# check.
HINDSIGHT_BACKEND_URL = os.getenv("HINDSIGHT_BACKEND_URL_FROM_HOST", "http://127.0.0.1:9077")


def _hindsight_reachable() -> bool:
    """True if the hindsight backend's /health responds 200 from the host."""
    try:
        with urllib.request.urlopen(f"{HINDSIGHT_BACKEND_URL}/health", timeout=2) as resp:  # noqa: S310
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


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
    tmpfs_home: bool = True,
) -> subprocess.CompletedProcess:
    """Run the workspace image with tmpfs home, optional env / mounts.

    tmpfs_home defaults to True, which is what every pre-existing caller
    wants, but it is also why the ~/.claude/projects data-loss defect
    survived a full green suite: on a tmpfs home the directory never
    pre-exists, so the adapter's destructive branch was never reached.
    Pass tmpfs_home=False (and bind-mount a real /home/agent) to exercise
    a persisted home.
    """
    cmd = ["docker", "run", "--rm"]
    if tmpfs_home:
        cmd.append("--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000")
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


def _open_perms(root: Path) -> None:
    """Open a fixture tree's perms for the container's non-root agent user.

    Docker Desktop's bind-mount layer does not reliably preserve host
    uid/gid semantics the way a native Linux bind mount would. The behavior
    under test is the adapter's own migrate-don't-delete logic, not
    filesystem permission handling.
    """
    os.chmod(root, 0o777)
    for p in root.rglob("*"):
        os.chmod(p, 0o777)


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_preexisting_transcripts_are_migrated_not_deleted(tmp_path: Path):
    """A persisted home's existing transcripts must end up IN the partition.

    This is the data-loss defect: the previous implementation rm -rf'd them
    at startup, before the exporter could ever see them. Migrating instead
    means a workspace that would have LOST its history gains it, because
    the moved transcripts are swept by this run's finalize.
    """
    spool = tmp_path / "spool"
    home = tmp_path / "home"
    proj = home / ".claude" / "projects" / "-workspace-old"
    proj.mkdir(parents=True)
    (proj / "old-session.jsonl").write_text(
        '{"type":"user","timestamp":"2026-08-14T10:00:00.000Z",'
        '"cwd":"/workspace","gitBranch":"main","message":{"role":"user","content":"pre-existing"}}\n'
    )
    spool.mkdir()
    _open_perms(home)
    os.chmod(spool, 0o777)

    result = _run(
        ["bash", "-c",
         "find /spool -name '*.jsonl' | sed 's|/spool|SPOOL|'; "
         "echo LINK=$(readlink -f ~/.claude/projects)"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "mig/test",
        },
        # NOTE: a real (non-tmpfs) home, which is what exposes the defect.
        # The stub exporter is mounted for the same reason as every other
        # adapter test here: 5.7's doctor must fully pass or CMD never runs.
        extra_mounts=[
            f"{spool}:/spool",
            f"{home}:/home/agent",
            f"{Path('tests/integration/fixtures/stub-exporter').resolve()}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
        tmpfs_home=False,
    )
    assert "old-session.jsonl" in result.stdout, (
        "pre-existing transcript was destroyed instead of migrated:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "SPOOL/mig/test/claude/" in result.stdout
    assert "LINK=/spool/mig/test/claude" in result.stdout


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_migration_failure_preserves_data_and_fails_loudly(tmp_path: Path):
    """If migration cannot complete, nothing is deleted and the doctor reports it.

    Refuse rather than guess: a workspace that will not start is
    recoverable, a deleted transcript is not.
    """
    spool = tmp_path / "spool"
    home = tmp_path / "home"
    proj = home / ".claude" / "projects"
    proj.mkdir(parents=True)
    (proj / "keepme.jsonl").write_text("{}\n")
    spool.mkdir()
    _open_perms(home)
    os.chmod(spool, 0o777)
    # Read-only partition target makes the move fail.
    (spool / "blocked").mkdir()
    (spool / "blocked").chmod(0o500)

    result = _run(
        ["bash", "-c", "ls ~/.claude/projects/"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "blocked",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{home}:/home/agent",
            f"{Path('tests/integration/fixtures/stub-exporter').resolve()}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
        tmpfs_home=False,
    )
    assert result.returncode != 0, (
        "a failed migration must not be silently ignored:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert (proj / "keepme.jsonl").exists(), "data was destroyed on a failed migration"
    # The failure must be attributable, not a generic non-zero exit: the
    # symlink was never created, so symlinks_correct is what fails.
    assert "symlinks_correct" in result.stderr
    assert "session-store doctor: FAIL" in result.stderr


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_name_collision_clobbers_neither_copy_and_fails_loudly(tmp_path: Path):
    """A name collision must preserve BOTH copies and refuse, not guess.

    This is the `mv -n` half of the safety property, and it is invisible to
    the migration loop's own exit status: GNU `mv -n` exits 0 and prints
    nothing when it skips a collision (verified against coreutils 9.1). The
    `rmdir` is what catches it, because a non-empty directory cannot be
    removed. Neither the home copy nor the partition copy may be clobbered.
    """
    spool = tmp_path / "spool"
    home = tmp_path / "home"
    proj = home / ".claude" / "projects"
    proj.mkdir(parents=True)
    (proj / "dup.jsonl").write_text("home-copy\n")
    part_claude = spool / "coll" / "claude"
    part_claude.mkdir(parents=True)
    (part_claude / "dup.jsonl").write_text("partition-copy\n")
    _open_perms(home)
    _open_perms(spool)

    result = _run(
        ["bash", "-c", "ls ~/.claude/projects/"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "coll",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{home}:/home/agent",
            f"{Path('tests/integration/fixtures/stub-exporter').resolve()}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
        tmpfs_home=False,
    )
    assert result.returncode != 0, (
        "a collision must refuse rather than guess:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    # Neither copy clobbered.
    assert (proj / "dup.jsonl").read_text() == "home-copy\n"
    assert (part_claude / "dup.jsonl").read_text() == "partition-copy\n"
    # The operator is told which file blocked the migration. mv says nothing
    # on a collision, so this listing is the only pointer to it.
    assert "still has contents after migration" in result.stderr
    assert "dup.jsonl" in result.stderr


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


# --- Task 7: the entrypoint wrapper + finalize hook --------------------------
#
# Section 6 is no longer a bare `exec "$@"`: it is a wrapper that runs the
# agent, then runs each registered capability's finalize.sh, then exits with
# the AGENT's own exit code (never finalize's). The session-store/seshmagic
# tests below need session-store fully registered (provider + URL), which
# means the entrypoint's own 5.7 doctor preflight runs too and must pass in
# full (including store_reachable) before CMD ever executes -- same
# constraint as the Task 6 tests above, so they skip the same way.

_STUB_EXPORTER = Path("tests/integration/fixtures/stub-exporter").resolve()


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_finalize_never_changes_agent_exit_code(tmp_path: Path):
    """A failing upload must not turn a successful phase into a failed one.

    (Here the agent itself fails with 7; the point is that the wrapper's
    post-agent finalize step must not stomp that 7 with its own status,
    whatever the sweep does.)
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        ["bash", "-c", "exit 7"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "exit-code-test",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 7, "wrapper must propagate the agent's exit code"


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_agent_success_exit_code_survives_finalize(tmp_path: Path):
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        ["bash", "-c", "echo done; exit 0"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "exit-zero-test",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0
    assert "done" in result.stdout


@pytest.mark.integration
@pytest.mark.skipif(not _hindsight_reachable(), reason="hindsight backend unreachable")
def test_missing_finalize_is_silent_skip():
    """The memory capability's hindsight adapter has no finalize.sh (only
    seshmagic/session-store does). The wrapper's finalize loop must treat a
    registered, doctor-passing capability with no finalize.sh as a silent
    no-op, not an error -- and must still propagate the agent's exit code.
    """
    result = _run(
        ["bash", "-c", "exit 5"],
        env={
            "AGENTIC_CAPABILITIES": "memory",
            "AGENTIC_MEMORY_PROVIDER": "hindsight",
            "AGENTIC_MEMORY_NAMESPACE": "finalize-skip-test",
            "AGENTIC_MEMORY_URL": "http://host.docker.internal:9077",
        },
        add_host_gateway=True,
    )
    assert result.returncode == 5, f"container failed: {result.stderr}"


@pytest.mark.integration
@pytest.mark.parametrize(
    "malicious_tag",
    [
        pytest.param(
            "workflow:$(touch /tmp/PWNED) it's,phase:c",
            id="quoted-parse-error-under-source",
        ),
        pytest.param(
            "workflow:$(touch /tmp/PWNED) safe,phase:c",
            id="unquoted-clean-under-source",
        ),
    ],
)
def test_finalize_parses_capture_env_never_sources_it(tmp_path: Path, malicious_tag: str):
    """Regression test for the Task 5/6 review finding, now that a real
    consumer of `.capture-env` (finalize.sh) exists to regress.

    Two payloads, both containing `$(touch /tmp/PWNED)` and a space:

    - "quoted-parse-error-under-source": also has an unbalanced single
      quote. Sourced as shell, that line is a *syntax error* -- bash never
      reaches expansion, so $(...) never runs even under a broken
      `source`-based implementation. The no-injection assertion is
      vacuous for this payload alone: it would pass whether the consumer
      parses correctly OR sources incorrectly.
    - "unquoted-clean-under-source": no unbalanced quote, so the line is
      syntactically valid shell. A `source`-based implementation WOULD
      execute the substitution and create /tmp/PWNED here. Only this
      payload makes the no-injection assertion load-bearing.

    Both must round-trip byte-identical (anchored, not substring -- so
    trailing corruption after the value can't slip through) and be visible
    to a CHILD process finalize.sh spawns (the exporter), not just
    finalize.sh's own shell.

    This calls finalize.sh directly (not through the full capability
    registration + doctor preflight) so it needs neither a reachable store
    nor the real exporter: SESSION_STORE_URL only has to be non-empty (the
    hook's early-exit guard), and the "exporter" here is a throwaway script
    written at container-run time (not a repo file) whose only job is to
    print the env var a real child process would see.
    """
    spool = tmp_path / "spool"
    part_dir = spool / "recovery-test"
    part_dir.mkdir(parents=True)
    capture_env = part_dir / ".capture-env"
    capture_env.write_text(f"SESSION_STORE_TAGS={malicious_tag}\n")
    os.chmod(capture_env, 0o600)

    fin = "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh"
    # Delimiters bracket the captured value exactly, so the Python-side
    # comparison is anchored (regex-extracted, then `==`) rather than a
    # substring check that a trailing-corruption bug could still satisfy.
    script = f"""
set -e
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
printf 'CHILD_SAW_START%sCHILD_SAW_END\\n' "$SESSION_STORE_TAGS"
exit 0
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export SESSION_STORE_URL=http://unused.invalid
export EXPORTER_STATE_FILE=/spool/recovery-test/state.json
unset SESSION_STORE_TAGS
{fin}
test -e /tmp/PWNED && echo INJECTION_OCCURRED || echo NO_INJECTION
"""
    result = _run(
        ["bash", "-c", script],
        extra_mounts=[f"{spool}:/spool"],
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    # The exporter's own stdout is intentionally routed to finalize.sh's
    # stderr (F3 fix: `SeshMagicSessionExporter >&2 2>&1`), so the fake
    # exporter's CHILD_SAW markers land in stderr here, not stdout.
    match = re.search(r"CHILD_SAW_START(.*?)CHILD_SAW_END", result.stderr, re.DOTALL)
    assert match is not None, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert match.group(1) == malicious_tag, (
        f"tag corrupted in round-trip: got {match.group(1)!r}, want {malicious_tag!r}"
    )
    assert "NO_INJECTION" in result.stdout
    assert "INJECTION_OCCURRED" not in result.stdout


@pytest.mark.integration
def test_finalize_survives_unset_exporter_state_file_on_failure():
    """Regression test: finalize.sh must not crash under `set -u` when
    EXPORTER_STATE_FILE is unset and the exporter fails.

    This is the standalone recovery-sweep shape .capture-env exists to
    serve (see the parse test above) -- SESSION_STORE_URL set, but no
    adapter env at all otherwise. finalize.sh's own failure-path log line
    used to reference `${EXPORTER_STATE_FILE%/*}` unguarded, unlike every
    other reference to that var in the file; under `set -u` that aborts
    the script with a nonzero exit, which breaks the one contract this
    hook cannot break ("finalize.sh must always exit 0").
    """
    fin = "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh"
    script = f"""
set -e
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
exit 1
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export SESSION_STORE_URL=http://unused.invalid
unset EXPORTER_STATE_FILE
{fin}
echo "FINALIZE_RC=$?"
"""
    result = _run(["bash", "-c", script])
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, result.stdout


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_prune_refuses_a_directory_it_did_not_create(tmp_path: Path):
    """The prune must never delete a directory this capability did not create.

    This is the reported defect, reproduced: with SPOOL=/workspace and
    PARTITION=repos the state file is /workspace/repos/state.json, whose
    dirname matched the old `/*/*` shape guard, and the sweep deleted an
    unrelated mounted directory. The victim here stands in for that mount.

    The stub exporter is mounted deliberately. The real SeshMagicSessionExporter
    is NOT installed in the workspace image, so without the stub the sweep
    fails, finalize returns early, and the prune block is never reached --
    the test would pass against the defect it is supposed to catch.
    """
    victim = tmp_path / "victim"
    (victim / "repos").mkdir(parents=True)
    (victim / "repos" / "precious.txt").write_text("do not delete me\n")

    result = _run(
        [
            "bash",
            "-c",
            "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh; "
            "echo FINALIZE_RC=$?",
        ],
        env={
            "SESSION_STORE_URL": STORE_URL,
            "EXPORTER_STATE_FILE": "/victim/repos/state.json",
        },
        extra_mounts=[
            f"{victim}:/victim",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert "FINALIZE_RC=0" in result.stdout, result.stdout
    assert (victim / "repos" / "precious.txt").exists(), "prune escaped its spool"


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_prune_refuses_a_pre_existing_partition_directory(tmp_path: Path):
    """The end-to-end form of the same defect, through the real adapter.

    The victim directory is mounted AS the partition, exactly as the
    reviewer's SPOOL=/workspace PARTITION=repos configuration produced it.
    init.sh runs over a directory it did not create, so it must not mark it
    as ours, and finalize must therefore leave it alone. Any containment
    check keyed on 'the adapter touched this path' rather than 'the adapter
    created this path' passes the test above and still fails this one.
    """
    spool = tmp_path / "workspace"
    (spool / "repos").mkdir(parents=True)
    (spool / "repos" / "precious.txt").write_text("do not delete me\n")

    result = _run(
        ["bash", "-c", "exit 0"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/workspace",
            "AGENTIC_SESSION_STORE_PARTITION": "repos",
        },
        extra_mounts=[
            f"{spool}:/workspace",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert (spool / "repos" / "precious.txt").exists(), "prune destroyed a mounted directory"


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_finalize_prunes_partition_on_success(tmp_path: Path):
    """On a successful sweep, finalize.sh must remove the partition
    directory so a persistent spool volume doesn't grow one directory per
    container run forever.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        ["bash", "-c", "exit 0"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "prune-test",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert not (spool / "prune-test").exists(), "successful sweep must prune its partition"


@pytest.mark.integration
def test_finalize_keeps_spool_on_upload_failure(tmp_path: Path):
    """On a failed sweep, the spool must be left intact for a later
    recovery sweep -- and the wrapper's own exit code must still be the
    agent's, not finalize's.
    """
    spool = tmp_path / "spool"
    part_dir = spool / "fail-test"
    part_dir.mkdir(parents=True)
    (part_dir / "state.json").write_text("{}")

    fin = "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh"
    script = f"""
set -e
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
exit 1
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export SESSION_STORE_URL=http://unused.invalid
export EXPORTER_STATE_FILE=/spool/fail-test/state.json
{fin}
echo "FINALIZE_RC=$?"
"""
    result = _run(
        ["bash", "-c", script],
        extra_mounts=[f"{spool}:/spool"],
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert (part_dir / "state.json").exists(), "spool must be retained on upload failure"


# --- Task 3 (M1 defect closure): a clean EXIT is not a clean SWEEP -------
#
# The exporter documents in its own source that "a completed sweep exits 0
# even with per-item skips/failures; only a hard RunError (store unreachable,
# source scan failure) is non-zero." So rc=0 is consistent with failed=3
# skipped_oversize=2, and finalize.sh used to prune the whole partition on
# rc=0 alone. Since the adapter now MIGRATES a pre-existing ~/.claude/projects
# into the partition, that partition can hold a user's entire accumulated
# transcript history, so pruning it on an incomplete sweep is data loss.
#
# These tests drive finalize.sh directly with a stub exporter that exits 0 and
# prints a chosen summary line, and assert on whether the spool survived.

_FINALIZE_SH = "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh"


def _finalize_with_stub_exporter(
    tmp_path: Path,
    stub_body: str,
    part_name: str,
) -> tuple[subprocess.CompletedProcess, Path, float]:
    """Run finalize.sh against a partition with a stubbed exporter.

    The partition gets the .agentic-partition marker Task 2's containment
    check requires, so the ONLY thing that can keep the spool in these tests
    is the sweep-completeness gate under test.

    Returns (result, transcript_path, elapsed_seconds). The transcript file
    still existing means the spool was retained.
    """
    part_dir = tmp_path / "spool" / part_name
    (part_dir / "claude").mkdir(parents=True)
    (part_dir / "state.json").write_text("{}\n")
    (part_dir / ".agentic-partition").write_text("")
    (part_dir / "claude" / "s.jsonl").write_text("{}\n")

    script = f"""
set -e
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
{stub_body}
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export SESSION_STORE_URL=http://unused.invalid
export EXPORTER_STATE_FILE=/spool/{part_name}/state.json
{_FINALIZE_SH}
echo "FINALIZE_RC=$?"
"""
    start = time.monotonic()
    result = _run(
        ["bash", "-c", script],
        extra_mounts=[f"{tmp_path / 'spool'}:/spool"],
    )
    elapsed = time.monotonic() - start
    return result, part_dir / "claude" / "s.jsonl", elapsed


@pytest.mark.integration
@pytest.mark.parametrize(
    ("counter", "summary"),
    [
        (
            "failed",
            "run: discovered=4 skipped_unchanged=0 uploaded=3 accepted=3 "
            "duplicate=0 rejected=0 skipped_oversize=0 failed=1",
        ),
        (
            "skipped_oversize",
            "run: discovered=4 skipped_unchanged=0 uploaded=3 accepted=3 "
            "duplicate=0 rejected=0 skipped_oversize=1 failed=0",
        ),
        (
            "rejected",
            "run: discovered=4 skipped_unchanged=0 uploaded=3 accepted=3 "
            "duplicate=0 rejected=1 skipped_oversize=0 failed=0",
        ),
    ],
)
def test_finalize_keeps_spool_when_a_sweep_counter_is_nonzero(
    tmp_path: Path, counter: str, summary: str
):
    """rc=0 with failed / skipped_oversize / rejected nonzero means at least
    one transcript never reached the store. The partition is the only
    remaining copy, so it must survive, and the log must name the counter
    that blocked the prune so an operator can act.
    """
    result, transcript, _ = _finalize_with_stub_exporter(
        tmp_path,
        f'echo "{summary}"\nexit 0\n',
        f"nonzero-{counter}",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert transcript.exists(), (
        f"an incomplete sweep ({counter} nonzero) must not prune the partition"
    )
    assert "INCOMPLETE" in result.stderr, "finalize must report the incomplete sweep"
    assert f"{counter}=1" in result.stderr, (
        f"finalize must name {counter} as the counter that blocked the prune"
    )


@pytest.mark.integration
def test_finalize_prunes_when_only_duplicate_and_unchanged_are_nonzero(tmp_path: Path):
    """duplicate and skipped_unchanged are confirmations, not losses:
    duplicate means the store already holds that content (it dedups on
    content_hash) and skipped_unchanged means a prior sweep uploaded it.
    Neither may block the prune, or the spool grows forever on any repeat
    sweep.
    """
    summary = (
        "run: discovered=5 skipped_unchanged=3 uploaded=2 accepted=0 "
        "duplicate=2 rejected=0 skipped_oversize=0 failed=0"
    )
    result, transcript, _ = _finalize_with_stub_exporter(
        tmp_path,
        f'echo "{summary}"\nexit 0\n',
        "clean-with-dupes",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert not transcript.exists(), (
        "duplicate/skipped_unchanged are not failures and must not block the prune"
    )


@pytest.mark.integration
def test_finalize_keeps_spool_when_no_summary_line_is_printed(tmp_path: Path):
    """An unreadable summary is not evidence of success. Absent the line, the
    sweep's outcome is unknown, and unknown must never authorize a delete.
    """
    result, transcript, _ = _finalize_with_stub_exporter(
        tmp_path,
        'echo "uploading things"\nexit 0\n',
        "no-summary",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert transcript.exists(), "an unparseable summary must not prune the partition"
    assert "no parseable summary" in result.stderr


@pytest.mark.integration
def test_finalize_bounds_a_hanging_exporter_and_keeps_the_spool(tmp_path: Path):
    """A wedged upload must not hang the run, and must not prune.

    Unbounded, a stuck DNS lookup or hung connection turns a completed agent
    run into a hang; during `docker stop` it burns the grace until SIGKILL,
    so the run reports 137 instead of the agent's real exit code. finalize.sh
    bounds the exporter at __UPLOAD_TIMEOUT_S and treats a timeout as an
    upload failure. A killed exporter also prints no summary line, so the
    completeness gate above independently refuses the prune.
    """
    result, transcript, elapsed = _finalize_with_stub_exporter(
        tmp_path,
        "sleep 600\n",
        "hang",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert elapsed < 60, f"finalize did not bound the exporter: {elapsed:.1f}s"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert transcript.exists(), "a timed-out upload must keep the spool"
    assert "TIMED OUT" in result.stderr, "finalize must report the timeout"


# --- Task 7: docker-stop signal behavior --------------------------------
#
# EXP-08 (a1-a2-wrapper-signal-matrix) measured that a naive single `wait`
# loses the agent's real exit code, and a plain double `wait` burns the
# entire stop grace and never runs finalize at all. These two tests exercise
# the actual failure mode `docker stop` produces (SIGTERM, then SIGKILL
# after a grace period) against both a cooperative agent (traps TERM, exits
# with its own code) and a stubborn one (`trap "" TERM`, must be escalated
# to SIGKILL). Both must still run finalize.

# entrypoint.sh's __TERM_GRACE_TICKS (15 x 0.1s = 1.5s) is coupled to this
# repo's OWN orchestrator teardown value -- docker.py's `docker stop -t 5`
# (lib/python/agentic_isolation/agentic_isolation/providers/docker.py) --
# not to "Docker's 10s default", which is merely the bare-CLI default and
# is NOT what this repo actually uses in production. Getting that coupling
# wrong is exactly the failure this review caught: with `-t 5` and the
# escalation window at 5s (half of the *wrong* 10s reference), the
# wrapper's own SIGKILL and docker's outer SIGKILL land in the same
# instant and finalize never runs. `-t 10` alone can't catch this, because
# 10s gives so much slack that almost any escalation window looks fine;
# `-t 5` is what actually exercises the constraint entrypoint.sh depends
# on. Test both: `-t 5` because it's the repo's real value, `-t 10` because
# it's the more forgiving/traditional one and a useful sanity check.
_DOCKER_STOP_GRACES_S = (5, 10)
_DOCKER_STOP_TIMEOUT_S = max(_DOCKER_STOP_GRACES_S) + 20


def _docker_stop_scenario(
    agent_script: str,
    container_name: str,
    grace_s: int,
    env: dict[str, str] | None = None,
    extra_mounts: list[str] | None = None,
    add_host_gateway: bool = False,
) -> tuple[int, float, str]:
    """Start the workspace image detached running agent_script as CMD,
    `docker stop -t grace_s` it, and return (exit_code, elapsed_seconds,
    combined logs).
    """
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)
    run_cmd = [
        "docker", "run", "-d", "--name", container_name,
        "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000",
    ]
    if add_host_gateway:
        run_cmd.append("--add-host=host.docker.internal:host-gateway")
    for m in extra_mounts or []:
        run_cmd.extend(["-v", m])
    for k, v in (env or {}).items():
        run_cmd.extend(["-e", f"{k}={v}"])
    run_cmd.extend([IMAGE, "bash", "-c", agent_script])
    try:
        subprocess.run(run_cmd, check=True, capture_output=True, text=True, timeout=30)

        # Give the entrypoint time to run sections 1-5.7 and reach CMD
        # before stopping, so the signal actually lands on the agent
        # process rather than mid-preflight.
        time.sleep(1.5)

        start = time.monotonic()
        subprocess.run(
            ["docker", "stop", "-t", str(grace_s), container_name],
            capture_output=True, text=True, timeout=_DOCKER_STOP_TIMEOUT_S,
        )
        elapsed = time.monotonic() - start

        inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}", container_name],
            capture_output=True, text=True, check=True,
        )
        exit_code = int(inspect.stdout.strip())
        logs = subprocess.run(
            ["docker", "logs", container_name], capture_output=True, text=True,
        )
        combined = logs.stdout + logs.stderr
        return exit_code, elapsed, combined
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True)


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
@pytest.mark.parametrize("grace_s", _DOCKER_STOP_GRACES_S)
def test_docker_stop_cooperative_agent_exits_with_own_code_and_runs_finalize(
    tmp_path: Path, grace_s: int
):
    """Agent traps TERM and exits 3 promptly. The wrapper must NOT wait for
    docker's own SIGKILL: it should return the agent's real exit code
    quickly (EXP-08 measured ~0.32s), and finalize must still have run.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    exit_code, elapsed, logs = _docker_stop_scenario(
        'trap "exit 3" TERM; while true; do :; done',
        f"wrapper-sigterm-cooperative-test-{grace_s}",
        grace_s,
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": f"docker-stop-cooperative-{grace_s}",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert exit_code == 3, f"expected the agent's own exit code; logs=\n{logs}"
    assert elapsed < grace_s, (
        f"cooperative agent should not burn the grace window, took {elapsed:.2f}s"
    )
    assert "[finalize] session-store upload complete" in logs, logs


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
@pytest.mark.parametrize("grace_s", _DOCKER_STOP_GRACES_S)
def test_docker_stop_stubborn_agent_is_killed_and_still_runs_finalize(
    tmp_path: Path, grace_s: int
):
    """Agent ignores TERM outright. The wrapper must escalate to SIGKILL
    itself -- strictly inside `grace_s`, including this repo's real `-t 5`
    teardown value, not just the more forgiving `-t 10` -- rather than
    block forever on a naive second `wait`. Finalize must still run
    afterward.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    exit_code, elapsed, logs = _docker_stop_scenario(
        'trap "" TERM; while true; do :; done',
        f"wrapper-sigterm-stubborn-test-{grace_s}",
        grace_s,
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": f"docker-stop-stubborn-{grace_s}",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert exit_code == 137, f"expected SIGKILL exit status; logs=\n{logs}"
    # The wrapper's own escalation window (__TERM_GRACE_TICKS = 1.5s) must
    # fire with headroom to spare inside `grace_s`, or docker's own
    # SIGKILL can land at the same instant as (or before) the wrapper's,
    # and finalize never gets its post-agent moment. This is the exact
    # coupling that broke when the window was sized against the wrong
    # ("Docker's 10s default") reference instead of docker.py's real `-t 5`.
    assert elapsed < grace_s, (
        f"wrapper must self-escalate before docker's own grace expires, took {elapsed:.2f}s"
    )
    assert "[finalize] session-store upload complete" in logs, logs
