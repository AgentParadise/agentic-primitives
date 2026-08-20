"""Integration tests for the generic capability registry entrypoint sections
5.6 + 5.7 (ADR-040).

Mirrors the pattern in test_entrypoint_memory.py — runs the real workspace
container with varying AGENTIC_CAPABILITIES / AGENTIC_<CAP>_* env vars and
asserts the entrypoint's loop behavior end-to-end.

See ADR-040 and docs/superpowers/sdd/2026-08-12-workspace-capability-modules/.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

IMAGE = os.getenv("AGENTIC_WORKSPACE_IMAGE", "agentic-workspace-claude-cli:latest")

# Resolved against THIS file, never against the process cwd: CI runs pytest
# from build/workspaces/<image>/ with a relative path to this suite, so a
# cwd-relative fixture path resolves to nothing, and `docker run -v` silently
# creates an empty DIRECTORY at a missing mount source. A directory at
# /usr/local/bin/SeshMagicSessionExporter still satisfies shutil.which (it is
# +x), so exporter_present failed on CI for a reason that had nothing to do
# with the exporter.
_STUB_EXPORTER = Path(__file__).parent / "fixtures" / "stub-exporter"

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
HINDSIGHT_BACKEND_URL = os.getenv(
    "HINDSIGHT_BACKEND_URL_FROM_HOST", "http://127.0.0.1:9077"
)


def _capability_contract_module(package: str):
    """Load a capability package's contract module straight from its source file.

    Each capability declares every env var name it reads exactly once, in its
    contract module. Those packages are not installed in the repo-root test
    environment, so the module is executed by path rather than the names being
    restated here: a rename then breaks at collection instead of at runtime in
    a container. The contract modules import stdlib only, so loading one has
    no side effects.
    """
    contract = (
        Path(__file__).parents[2] / "lib" / "python" / package / package / "contract.py"
    )
    spec = importlib.util.spec_from_file_location(f"_{package}_contract", contract)
    module = importlib.util.module_from_spec(spec)
    # Registered before execution because @dataclass resolves its own module
    # out of sys.modules while the class body is being processed, and raises
    # if it is not there yet.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _capability_env_enum(package: str):
    """That module's `Env` StrEnum: every env var name the capability reads."""
    return _capability_contract_module(package).Env


SessionStoreContract = _capability_contract_module("agentic_session_store")
MemoryContract = _capability_contract_module("agentic_memory")
SessionStoreEnv = SessionStoreContract.Env
MemoryEnv = MemoryContract.Env
# The names the seshmagic adapter EXPORTS for the exporter to read, spelled
# once in the same contract module for the same reason.
ExporterEnv = SessionStoreContract.ExporterEnv


def _hindsight_reachable() -> bool:
    """True if the hindsight backend's /health responds 200 from the host."""
    try:
        with urllib.request.urlopen(
            f"{HINDSIGHT_BACKEND_URL}/health", timeout=2
        ) as resp:  # noqa: S310
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


def _host_spool(tmp_path: Path) -> Path:
    """Create the host directory that backs the container's /spool.

    Only the mount point itself is made on the host, and it is opened to
    0777 so the container's non-root agent user can create the partition
    inside it. Everything the tests then assert on is created BY the agent
    user, in the container: see _stage_partition_sh for why.
    """
    spool = tmp_path / "spool"
    spool.mkdir(parents=True, exist_ok=True)
    os.chmod(spool, 0o777)
    return spool


def _stage_partition_sh(
    part_name: str,
    files: dict[str, str],
    modes: dict[str, int] | None = None,
) -> str:
    """Shell that builds a spool partition IN the container, as the agent user.

    These fixtures cannot be written on the host. A Linux bind mount passes
    host uid/gid through literally, while Docker Desktop on macOS remaps
    them to the container user. The container runs as uid 1000 (agent) and
    GitHub Actions runners are uid 1001, so a host-written 0600
    `.capture-env` is readable by the agent on a developer's Mac and
    unreadable on CI, and a host-owned partition directory cannot be
    written into at all, so finalize.sh's `[ -r ... ]` guard takes its else
    branch. That looks like a production defect and is not.

    Creating the files in the container reproduces production ownership,
    where init.sh makes the partition and `.capture-env` as the agent user,
    so the uid boundary never exists in the first place.

    Content is passed base64-encoded so arbitrary bytes (newlines, quotes,
    command substitutions, the empty string) survive the trip into the
    shell verbatim. `modes` is applied after the write, which is how
    `.capture-env` keeps its 0600 semantics: the agent chmods its own file.
    """
    lines = [f"mkdir -p /spool/{part_name}"]
    for rel, content in files.items():
        path = f"/spool/{part_name}/{rel}"
        parent = path.rsplit("/", 1)[0]
        b64 = base64.b64encode(content.encode()).decode()
        lines.append(f"mkdir -p {parent}")
        lines.append(f"printf %s '{b64}' | base64 -d > {path}")
        mode = (modes or {}).get(rel)
        if mode is not None:
            lines.append(f"chmod {mode:04o} {path}")
    return "\n".join(lines)


@pytest.mark.integration
def test_capability_runtime_is_staged_from_the_shared_tree():
    """The in-container capability layout and the entrypoint's exec bit (ADR-040 s12).

    Asserts only what a prebuilt image tag can show from inside a container:
    /opt/agentic/capabilities/ holds both registered capabilities, and
    /opt/agentic/entrypoint.sh is executable. It runs `docker run` against an
    image tag and cannot see the source tree, so it says nothing about WHERE
    the image staged that tree from. Staging from the shared workspace/ tree
    is a build-time property, checked by review against ADR-040 s12.1.
    """
    result = _run(
        [
            "bash",
            "-c",
            "ls /opt/agentic/capabilities/; "
            "test -x /opt/agentic/entrypoint.sh && echo ENTRYPOINT_OK",
        ]
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "memory" in result.stdout
    assert "session-store" in result.stdout
    assert "ENTRYPOINT_OK" in result.stdout


OMNI_IMAGE = os.getenv("AGENTIC_OMNI_IMAGE", "omni-agent-workspace:latest")


def _omni_available() -> bool:
    r = subprocess.run(
        ["docker", "image", "inspect", OMNI_IMAGE],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


@pytest.mark.integration
@pytest.mark.skipif(not _omni_available(), reason="omni image not built")
def test_omni_hosts_the_shared_capability_runtime():
    """The second image must satisfy ADR-040 section 12 with no change to workspace/.

    This is the only real test of whether section 12 is a contract or a
    description of claude-cli.
    """
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            OMNI_IMAGE,
            "-c",
            "ls /opt/agentic/capabilities/; "
            "test -x /opt/agentic/entrypoint.sh && echo ENTRYPOINT_EXEC; "
            "test -x /opt/agentic/capabilities/memory/doctor && echo MEMORY_DOCTOR_EXEC; "
            "test -x /opt/agentic/capabilities/session-store/doctor && echo STORE_DOCTOR_EXEC; "
            "echo CAPS=$AGENTIC_CAPABILITIES; "
            "command -v claude >/dev/null && echo CLAUDE_PRESENT; "
            "command -v codex >/dev/null && echo CODEX_PRESENT",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    out = result.stdout
    assert "memory" in out and "session-store" in out
    assert "ENTRYPOINT_EXEC" in out
    assert "MEMORY_DOCTOR_EXEC" in out
    assert "STORE_DOCTOR_EXEC" in out
    assert "CAPS=memory session-store" in out
    assert "CLAUDE_PRESENT" in out
    assert "CODEX_PRESENT" in out


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
    assert len(checks) == 6, "every check must run even when the binary is absent"
    assert checks["exporter_present"]["passed"] is False
    # Names the binary it looked for, so the operator knows what to install.
    # This is the standard-anchored primary name; the vendor-branded legacy name
    # is still ACCEPTED (the mount tests below prove it) but is no longer what a
    # not-found message advertises, because telling someone to install a
    # deprecated name is how the deprecation never completes.
    assert "apss-session-exporter" in checks["exporter_present"]["detail"]


@pytest.mark.integration
def test_mounted_exporter_satisfies_the_check(tmp_path: Path):
    """A binary provided at deploy time satisfies exporter_present.

    See test_exporter_absent_is_a_specific_doctor_failure for why
    AGENTIC_CAPABILITIES excludes "session-store": store_reachable still
    fails here (unreachable.invalid), so without this exclusion the
    entrypoint's own 5.7 preflight would hard-exit before the CMD below
    (whose stdout this test inspects) ever ran.
    """
    result = _run(
        ["/opt/agentic/capabilities/session-store/doctor", "--json"],
        env={
            "AGENTIC_CAPABILITIES": "memory",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": "http://unreachable.invalid",
        },
        extra_mounts=[f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro"],
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
            "bash",
            "-c",
            "echo CLAUDE_PROJECTS_ROOT=$CLAUDE_PROJECTS_ROOT; "
            "echo CODEX_SESSIONS_ROOT=$CODEX_SESSIONS_ROOT; "
            "echo EXPORTER_STATE_FILE=$EXPORTER_STATE_FILE; "
            "echo SESSION_STORE_TAGS=$SESSION_STORE_TAGS; "
            "echo ORIGIN_HOST_SET=${SESSION_STORE_ORIGIN_HOST:-unset}; "
            "echo ORIGIN_DEPLOYMENT=${SESSION_STORE_ORIGIN_DEPLOYMENT:-unset}; "
            "readlink -f ~/.claude/projects; "
            "readlink -f ~/.codex/sessions",
        ],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_TAGS": "workflow:w1,phase:p2",
            "AGENTIC_SESSION_STORE_DEPLOYMENT": "syntropic137__beta",
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
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    out = result.stdout
    assert "CLAUDE_PROJECTS_ROOT=/spool/w1/p2/claude" in out
    assert "CODEX_SESSIONS_ROOT=/spool/w1/p2/codex" in out
    assert "EXPORTER_STATE_FILE=/spool/.agentic-session-store/w1/p2/state.json" in out
    assert "SESSION_STORE_TAGS=workflow:w1,phase:p2" in out
    assert "ORIGIN_HOST_SET=unset" in out, (
        "origin_host must never be set by the adapter"
    )
    # The translation this capability exists to perform. Without an assertion
    # here, deleting the three lines in init.sh or misspelling either variable
    # loses deployment attribution silently: capture keeps working, and every
    # session becomes unattributable to the deployment that produced it.
    assert "ORIGIN_DEPLOYMENT=syntropic137__beta" in out, (
        "AGENTIC_SESSION_STORE_DEPLOYMENT must reach the exporter as "
        "SESSION_STORE_ORIGIN_DEPLOYMENT"
    )
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
    (home / ".claude" / "projects" / "sentinel.txt").write_text(
        "pre-existing real directory\n"
    )
    (home / ".codex" / "sessions").mkdir(parents=True)
    # Docker Desktop's bind-mount layer does not reliably preserve host
    # uid/gid semantics the way a native Linux bind mount would; open the
    # perms up so the container's non-root agent user can rm/mkdir/symlink
    # here regardless of host uid. The behavior under test is the adapter's
    # own replace-don't-nest logic, not filesystem permission handling.
    os.chmod(home, 0o777)
    for p in home.rglob("*"):
        os.chmod(p, 0o777)

    stub = _STUB_EXPORTER
    cmd = [
        "docker",
        "run",
        "--rm",
        "--add-host=host.docker.internal:host-gateway",
        "-v",
        f"{home}:/home/agent",
        "-v",
        f"{spool}:/spool",
        "-v",
        f"{stub}:/usr/local/bin/SeshMagicSessionExporter:ro",
        "-e",
        "AGENTIC_CAPABILITIES=session-store",
        "-e",
        "AGENTIC_SESSION_STORE_PROVIDER=seshmagic",
        "-e",
        f"AGENTIC_SESSION_STORE_URL={STORE_URL}",
        "-e",
        "AGENTIC_SESSION_STORE_SPOOL=/spool",
        "-e",
        "AGENTIC_SESSION_STORE_PARTITION=w1/p2",
        IMAGE,
        "bash",
        "-c",
        "readlink -f ~/.claude/projects; readlink -f ~/.codex/sessions",
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
        [
            "bash",
            "-c",
            "find /spool -name '*.jsonl' | sed 's|/spool|SPOOL|'; "
            "echo LINK=$(readlink -f ~/.claude/projects)",
        ],
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
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
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
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
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
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
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
    half of the fix: the opaque tag string lands in the adapter's reserved
    metadata namespace (NOT in the transcript partition, which the operator
    may own), mode 600, so a later sweep (Task 7's finalize.sh) can recover
    it.

    This does NOT exercise finalize.sh sourcing the file back in — that
    mechanism does not exist yet (Task 7). It verifies the artifact Task 7
    depends on is produced correctly.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        [
            "bash",
            "-c",
            "stat -c '%a' /spool/.agentic-session-store/w1/p2/.capture-env; "
            "cat /spool/.agentic-session-store/w1/p2/.capture-env; "
            # Decode separately so a failure distinguishes "wrong record
            # name" from "right record, wrong bytes".
            "printf 'DECODED=%s\\n' "
            "\"$(sed -n 's/^SESSION_STORE_TAGS_B64=//p' /spool/.agentic-session-store/w1/p2/.capture-env "
            '| head -1 | base64 -d)"',
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
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    # Equality, not substring: "600" in "1600" is also true, and would pass
    # on a mode this check must reject.
    assert result.stdout.splitlines()[0].strip() == "600"
    # The value is base64-encoded (so a tag containing a newline survives a
    # line-oriented record). Assert the shipped record name, that the raw
    # file does NOT carry the plaintext, and that it decodes back.
    assert "SESSION_STORE_TAGS_B64=" in result.stdout
    assert "SESSION_STORE_TAGS=workflow:w1,phase:p2" not in result.stdout
    assert "DECODED=workflow:w1,phase:p2" in result.stdout


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
    the record, base64-decode, then `export`) rather than sourcing, and
    asserts a child process (not just the current shell) receives the
    exact original string, and that a command-substitution payload never
    executes.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        [
            "bash",
            "-c",
            # The documented parse contract: sed the record, base64 -d,
            # export. Never source.
            "export SESSION_STORE_TAGS=\"$(sed -n 's/^SESSION_STORE_TAGS_B64=//p' "
            '/spool/.agentic-session-store/w1/p2/.capture-env | head -1 | base64 -d)"; '
            # Assert a CHILD process sees it (C2) — not just this shell.
            'sh -c \'printf "CHILD_SAW=%s\\n" "$SESSION_STORE_TAGS"\'; '
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
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
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
@pytest.mark.skipif(
    not STORE_AUTH_TOKEN, reason="SESSION_STORE_AUTH_TOKEN_FROM_HOST not set"
)
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
    assert len(checks) == 6
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
def test_finalize_parses_capture_env_never_sources_it(
    tmp_path: Path, malicious_tag: str
):
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
    spool = _host_spool(tmp_path)
    # The 0600 `.capture-env` is written in the container, by the agent user
    # that finalize.sh then runs as. See _stage_partition_sh.
    stage = _stage_partition_sh(
        "recovery-test",
        {".capture-env": f"SESSION_STORE_TAGS={malicious_tag}\n"},
        modes={".capture-env": 0o600},
    )

    fin = "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh"
    # Delimiters bracket the captured value exactly, so the Python-side
    # comparison is anchored (regex-extracted, then `==`) rather than a
    # substring check that a trailing-corruption bug could still satisfy.
    script = f"""
set -e
{stage}
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
printf 'CHILD_SAW_START%sCHILD_SAW_END\\n' "$SESSION_STORE_TAGS" > /tmp/exporter-observed
exit 0
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export SESSION_STORE_URL=http://unused.invalid
export EXPORTER_STATE_FILE=/spool/recovery-test/state.json
unset SESSION_STORE_TAGS
{fin}
cat /tmp/exporter-observed
test -e /tmp/PWNED && echo INJECTION_OCCURRED || echo NO_INJECTION
"""
    result = _run(
        ["bash", "-c", script],
        extra_mounts=[f"{spool}:/spool"],
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    # The fake exporter records what it saw in a FILE, which the script
    # cats back out after finalize.sh has returned. finalize.sh captures the
    # exporter's streams and deliberately never replays them (an exporter is
    # an operator-supplied binary and its output is not trusted in a durable
    # log), so a marker printed to either stream reaches nobody. Observing
    # through a file is also the stronger claim: it says the CHILD PROCESS
    # received the value, independently of anything finalize.sh chooses to
    # log.
    match = re.search(r"CHILD_SAW_START(.*?)CHILD_SAW_END", result.stdout, re.DOTALL)
    assert match is not None, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert match.group(1) == malicious_tag, (
        f"tag corrupted in round-trip: got {match.group(1)!r}, want {malicious_tag!r}"
    )
    assert "NO_INJECTION" in result.stdout
    assert "INJECTION_OCCURRED" not in result.stdout


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_capture_env_round_trips_a_newline_tag(tmp_path: Path):
    """Tags are opaque. A newline must survive the write/read round trip.

    `.capture-env` is a line-oriented record and the recovery parse read one
    line back, so a tag of "workflow:w1\\nphase:p2" was silently truncated to
    "workflow:w1" -- attribution lost with no error anywhere. base64 is the
    fix: the encoded value is a single line by construction.

    This drives BOTH halves through the shipped code, which is the point --
    init.sh does the real write (via the entrypoint's 5.6 adapter sourcing,
    so the doctor preflight must pass, hence the stub exporter and the live
    store), and finalize.sh does the real recovery read. Nothing here
    re-implements the parse.

    The recovered value is read by a CHILD process finalize.sh spawns (the
    fake exporter), not by the shell that recovered it: an `export` that
    never reaches the exporter is the failure mode this capability already
    shipped once.
    """
    nasty = "workflow:w1\nphase:p2 with space\tand-tab\nquote:it's,subst:$(touch /tmp/PWNED)"

    spool = tmp_path / "spool"
    spool.mkdir()

    # Runs as CMD, i.e. after 5.6 sourced init.sh (which wrote .capture-env
    # from the env) and after 5.7's doctor passed. EXPORTER_STATE_FILE is
    # already exported by the adapter, so unsetting SESSION_STORE_TAGS is
    # enough to put finalize.sh on its recovery path -- the same shape as a
    # sweep of a partition left behind by a SIGKILLed container.
    script = """
set -e
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
printf 'ROUNDTRIP_START%sROUNDTRIP_END\\n' "$SESSION_STORE_TAGS" > /tmp/exporter-observed
exit 0
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
unset SESSION_STORE_TAGS
/opt/agentic/capabilities/session-store/seshmagic/finalize.sh
cat /tmp/exporter-observed
test -e /tmp/PWNED && echo INJECTION_OCCURRED || echo NO_INJECTION
"""
    result = _run(
        ["bash", "-c", script],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_TAGS": nasty,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "nl/test",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    # Via a file, not a stream: finalize.sh captures the exporter's output
    # and never replays it. See the parse test above.
    match = re.search(r"ROUNDTRIP_START(.*?)ROUNDTRIP_END", result.stdout, re.DOTALL)
    assert match is not None, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert match.group(1) == nasty, (
        f"tags did not round-trip: got {match.group(1)!r}, want {nasty!r}"
    )
    # base64 must not have become a way back in: the payload above carries a
    # command substitution too, and it must still be inert.
    assert "NO_INJECTION" in result.stdout
    assert "INJECTION_OCCURRED" not in result.stdout
    # A current-format record must NOT trip the legacy-migration notice,
    # or the notice is noise and stops meaning "you still have old
    # partitions in circulation".
    assert "legacy pre-base64" not in result.stderr


@pytest.mark.integration
def test_legacy_capture_env_is_recovered_and_announced(tmp_path: Path):
    """The pre-base64 record must still be readable, and say so out loud.

    The fallback is a migration affordance, not a supported format: the
    spool volume outlives the image, so a partition written by an older
    init.sh and orphaned by a SIGKILLed container can be swept by this
    finalize. Refusing to read it would upload those sessions
    unattributed, which is the exact failure .capture-env exists to
    prevent.

    The stderr notice is the removal condition's only observable signal.
    Once it stops appearing across a fleet, no pre-_B64 partition is left
    and the fallback can be deleted. A silent fallback would mean nobody
    ever learns that, so the notice is asserted here as behavior, not
    treated as incidental logging.
    """
    legacy_tag = "workflow:w1,phase:p2"

    spool = _host_spool(tmp_path)
    # Deliberately the OLD record name, written the way the old init.sh did:
    # in the container, as the agent user, mode 0600.
    stage = _stage_partition_sh(
        "legacy-test",
        {".capture-env": f"SESSION_STORE_TAGS={legacy_tag}\n"},
        modes={".capture-env": 0o600},
    )

    fin = "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh"
    script = f"""
set -e
{stage}
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
printf 'LEGACY_SAW_START%sLEGACY_SAW_END\\n' "$SESSION_STORE_TAGS" > /tmp/exporter-observed
exit 0
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export SESSION_STORE_URL=http://unused.invalid
export EXPORTER_STATE_FILE=/spool/legacy-test/state.json
unset SESSION_STORE_TAGS
{fin}
cat /tmp/exporter-observed
"""
    result = _run(["bash", "-c", script], extra_mounts=[f"{spool}:/spool"])
    assert result.returncode == 0, f"container failed: {result.stderr}"
    match = re.search(r"LEGACY_SAW_START(.*?)LEGACY_SAW_END", result.stdout, re.DOTALL)
    assert match is not None, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert match.group(1) == legacy_tag
    assert "legacy pre-base64" in result.stderr, (
        "the fallback must announce itself, or the removal condition is unobservable"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "content",
    [
        pytest.param("", id="empty-file"),
        pytest.param("TRUNCATED", id="foreign-content"),
        pytest.param("SESSION_STORE_TAGS_B64=\n", id="current-record-empty-value"),
        pytest.param("SESSION_STORE_TAGS=\n", id="legacy-record-empty-value"),
    ],
)
def test_unrecognised_capture_env_claims_no_recovery(tmp_path: Path, content: str):
    """A readable .capture-env with no usable record must recover nothing
    and say nothing that is not true.

    The recovery used to branch on "no _B64 record present" rather than on
    "a legacy record actually matched", so every case below took the legacy
    path: it printed the legacy-migration notice AND "recovered tags from
    ...", having recovered nothing. Two false signals on one path. The
    second one lies about this sweep; the first one lies about the fleet,
    telling an operator they still have pre-_B64 partitions in circulation
    when they may have none, which is precisely the judgement that notice
    exists to inform.

    These are not hypothetical shapes. A spool volume outliving the image is
    the case this whole branch exists to serve, and a truncated or foreign
    file is what such a volume produces.

    A record that IS present but fails to decode is a different case with a
    report of its own, and lives in
    test_undecodable_capture_env_reports_the_decode_failure.
    """
    spool = _host_spool(tmp_path)
    # Written in the container, as the agent user, mode 0600: the file has
    # to be READABLE for these cases to be about the record's content at
    # all. See _stage_partition_sh.
    stage = _stage_partition_sh(
        "garbage-test",
        {".capture-env": content},
        modes={".capture-env": 0o600},
    )

    fin = "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh"
    script = f"""
set -e
{stage}
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
printf 'TAGS_SEEN_START%sTAGS_SEEN_END\\n' "${{SESSION_STORE_TAGS-<unset>}}" > /tmp/exporter-observed
exit 0
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export SESSION_STORE_URL=http://unused.invalid
export EXPORTER_STATE_FILE=/spool/garbage-test/state.json
unset SESSION_STORE_TAGS
{fin}
cat /tmp/exporter-observed
"""
    result = _run(["bash", "-c", script], extra_mounts=[f"{spool}:/spool"])
    assert result.returncode == 0, f"finalize.sh must always exit 0: {result.stderr}"
    assert "legacy pre-base64" not in result.stderr, (
        "claimed a legacy partition that is not there; the notice must stay trustworthy"
    )
    assert "recovered tags from" not in result.stderr, (
        "claimed a recovery that did not happen"
    )
    # The operator is told, and the exporter is left genuinely untagged
    # rather than handed an empty string that looks like a real value.
    #
    # The probe uses ${SESSION_STORE_TAGS-<unset>}, WITHOUT the colon, on
    # purpose: `:-` substitutes for empty as well as unset, so it would
    # report "<unset>" for the old behavior (which exported an empty
    # string) and the assertion below would pass against the bug it exists
    # to catch.
    assert "no usable tag record" in result.stderr, result.stderr
    match = re.search(r"TAGS_SEEN_START(.*?)TAGS_SEEN_END", result.stdout, re.DOTALL)
    assert match is not None, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert match.group(1) == "<unset>", (
        f"SESSION_STORE_TAGS must stay unset, got {match.group(1)!r}"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    "content",
    [
        pytest.param("SESSION_STORE_TAGS_B64=!!!not!!!base64!!!\n", id="not-base64"),
        # A real record with its payload cut short: base64.b64encode of
        # "workflow:w1 phase:p2" with the tail removed, which is what a
        # partial write of .capture-env leaves behind.
        pytest.param(
            "SESSION_STORE_TAGS_B64="
            + base64.b64encode(b"workflow:w1 phase:p2").decode()[:-3]
            + "\n",
            id="truncated-payload",
        ),
    ],
)
def test_undecodable_capture_env_reports_the_decode_failure(
    tmp_path: Path, content: str
):
    """A _B64 record that does not decode must be reported as a DECODE
    failure, not swallowed into an untagged upload that looks routine.

    `base64 -d` ran inside a process substitution feeding `read`, and a
    process substitution's exit status is not the status of the enclosing
    command. Nothing looked at it, so a corrupt or truncated payload
    produced empty or partial tags and the sweep uploaded anyway. That is
    silent misattribution, which is the failure this recovery path exists
    to prevent: a session stored with the wrong tags is worse than one that
    failed loudly, because nobody learns it is wrong.

    The contract asserted here: finalize.sh still exits 0 and still sweeps
    (a skipped upload would trade an unattributable session for a lost
    one), but it names the decode failure on stderr, claims no recovery,
    and leaves SESSION_STORE_TAGS unset so nothing downstream can mistake
    an empty string for a real value.
    """
    spool = _host_spool(tmp_path)
    # In the container, as the agent user, mode 0600: see _stage_partition_sh.
    stage = _stage_partition_sh(
        "undecodable-test",
        {".capture-env": content},
        modes={".capture-env": 0o600},
    )

    fin = "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh"
    script = f"""
set -e
{stage}
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
printf 'TAGS_SEEN_START%sTAGS_SEEN_END\\n' "${{SESSION_STORE_TAGS-<unset>}}" > /tmp/exporter-observed
exit 0
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export SESSION_STORE_URL=http://unused.invalid
export EXPORTER_STATE_FILE=/spool/undecodable-test/state.json
unset SESSION_STORE_TAGS
{fin}
cat /tmp/exporter-observed
"""
    result = _run(["bash", "-c", script], extra_mounts=[f"{spool}:/spool"])
    assert result.returncode == 0, f"finalize.sh must always exit 0: {result.stderr}"
    # The decode failure is named, and named as a decode failure: "no
    # usable tag record" would describe a file with no record at all and
    # send the operator looking for the wrong thing.
    assert "does not decode as base64" in result.stderr, (
        f"a decode failure must be visible on stderr: {result.stderr!r}"
    )
    assert "unattributable" in result.stderr, result.stderr
    assert "recovered tags from" not in result.stderr, (
        "claimed a recovery that did not happen"
    )
    assert "legacy pre-base64" not in result.stderr, (
        "a present-but-corrupt record is not a legacy record"
    )
    # ${SESSION_STORE_TAGS-<unset>}, without the colon, on purpose: `:-`
    # would report "<unset>" for an exported empty string too, and pass
    # against the bug this exists to catch.
    match = re.search(r"TAGS_SEEN_START(.*?)TAGS_SEEN_END", result.stdout, re.DOTALL)
    assert match is not None, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert match.group(1) == "<unset>", (
        f"SESSION_STORE_TAGS must stay unset, got {match.group(1)!r}"
    )


@pytest.mark.integration
def test_finalize_survives_unset_exporter_state_file_on_failure():
    """Regression test: finalize.sh must not crash under `set -u` when
    EXPORTER_STATE_FILE is unset and the exporter fails.

    This is what section 6 produces when an adapter's init FAILED: 5.6 warns
    and continues, so the finalizer still runs, with a store URL in the
    environment and none of init.sh's exports. finalize.sh's own failure-path
    log line used to reference `${EXPORTER_STATE_FILE%/*}` unguarded, unlike
    every other reference to that var in the file; under `set -u` that aborts
    the script with a nonzero exit, which breaks the one contract this hook
    cannot break ("finalize.sh must always exit 0").
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
def test_finalize_warns_when_it_runs_without_the_adapters_environment():
    """Surviving the missing environment is not enough; it has to be reported.

    finalize.sh's header documented a standalone recovery path: invoke the
    hook by hand over a spool a SIGKILLed container left behind. Nothing
    implemented it. Without the adapter's environment the hook has no store
    URL, no credential, no spool and no transcript roots, so it returned 0
    having uploaded nothing and warned nothing, and an operator following the
    documented procedure got a success status and silence.

    The claim is gone from the file and the capability README. The case that
    is real -- section 5.6's init failed, 5.6 warned and continued, and
    section 6 ran the finalizer anyway -- now warns, because "always exit 0"
    means a warning on stderr is the only report this hook can make.

    The warning must name what is actually degraded (no spool path in the
    report, no .capture-env tag recovery, a state file that is not this
    partition's), or it is just another line to scroll past.
    """
    script = f"""
set -e
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
echo "run: discovered=0 skipped_unchanged=0 uploaded=0 accepted=0 duplicate=0 rejected=0 skipped_oversize=0 failed=0"
exit 0
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export {ExporterEnv.URL}=http://unused.invalid
unset {ExporterEnv.STATE_FILE}
{_FINALIZE_SH}
echo "FINALIZE_RC=$?"
"""
    result = _run(["bash", "-c", script])
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert "WARNING" in result.stderr and ExporterEnv.STATE_FILE in result.stderr, (
        "a sweep without the adapter's environment must not be silent"
    )
    assert "not a standalone recovery tool" in result.stderr, (
        "the removed claim must be contradicted where an operator would act on it"
    )
    assert ".capture-env" in result.stderr, (
        "the warning must say tag recovery is unavailable, since the upload "
        "may then be unattributable"
    )


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_finalize_leaves_a_directory_it_did_not_create_intact(tmp_path: Path):
    """finalize.sh must never delete anything, least of all a directory this
    capability did not create.

    This is the reported defect, reproduced: with SPOOL=/workspace and
    PARTITION=repos the state file is /workspace/repos/state.json, whose
    dirname matched the old `/*/*` shape guard, and the sweep deleted an
    unrelated mounted directory. The victim here stands in for that mount.
    The prune that did it has since been removed outright, so this now guards
    against reintroducing any delete at all on this path.

    The stub exporter is mounted deliberately. The real SeshMagicSessionExporter
    is NOT installed in the workspace image, so without the stub the sweep
    fails and finalize returns early, well before the point where the old
    prune ran -- the test would pass against the defect it is supposed to
    catch.
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
    assert (victim / "repos" / "precious.txt").exists(), "finalize deleted user data"


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_finalize_leaves_a_pre_existing_partition_directory_intact(tmp_path: Path):
    """The end-to-end form of the same defect, through the real adapter.

    The victim directory is mounted AS the partition, exactly as the
    reviewer's SPOOL=/workspace PARTITION=repos configuration produced it.
    The adapter sweeps and uploads from it and must leave every byte of it
    where it was.
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
    assert (spool / "repos" / "precious.txt").exists(), (
        "finalize destroyed a mounted directory"
    )


# --- Adapter metadata lives in a reserved, marked namespace -----------------
#
# The transcript partition may be a directory the operator already owned
# (SPOOL=/workspace PARTITION=repos points at an existing mount). Adapter
# metadata therefore goes to ${SPOOL}/.agentic-session-store/${PARTITION}/,
# which carries an ownership marker, and a namespace that is foreign or
# occupied is refused rather than emptied or overwritten.

_RESERVED = ".agentic-session-store"


def _operator_owned_spool(tmp_path: Path, partition: str) -> Path:
    """A spool root whose partition directory already belongs to somebody else."""
    spool = tmp_path / "workspace"
    (spool / partition).mkdir(parents=True)
    os.chmod(spool, 0o777)
    os.chmod(spool / partition, 0o777)
    return spool


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_init_never_writes_or_deletes_inside_the_transcript_partition(tmp_path: Path):
    """init.sh must not destroy or overwrite operator files in the partition.

    The reported blocker, reproduced: with SPOOL=/workspace PARTITION=repos
    the adapter did `rm -f ${PART_DIR}/.capture-env` and wrote its own
    state.json path into a directory the operator already had, two lines
    below a comment asserting it only ever mkdir -ps and symlinks in there.
    An operator `.capture-env` was destroyed before the doctor ran.

    Both names are staged, because both are adapter metadata names that
    collide by construction, and only the first was ever reported.
    """
    spool = _operator_owned_spool(tmp_path, "repos")
    (spool / "repos" / ".capture-env").write_text("operator's own file\n")
    (spool / "repos" / "state.json").write_text('{"operator": "own file"}\n')

    result = _run(
        ["bash", "-c", "echo STATE=$EXPORTER_STATE_FILE"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_TAGS": "workflow:w1,phase:p2",
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
    assert (spool / "repos" / ".capture-env").read_text() == "operator's own file\n", (
        "the adapter destroyed an operator file in the transcript partition"
    )
    assert (spool / "repos" / "state.json").read_text() == '{"operator": "own file"}\n'
    # And the adapter's own metadata went to the reserved namespace instead.
    assert f"STATE=/workspace/{_RESERVED}/repos/state.json" in result.stdout, (
        result.stdout
    )
    assert (spool / _RESERVED / "repos" / ".capture-env").exists()
    assert (spool / _RESERVED / ".owner").exists(), "the namespace must be marked"


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
@pytest.mark.parametrize(
    ("marker", "label"),
    [
        pytest.param(None, "no marker, occupied", id="occupied-unmarked"),
        pytest.param("some-other-tool-v9\n", "foreign marker", id="foreign-marker"),
    ],
)
def test_init_refuses_a_namespace_it_does_not_own(
    tmp_path: Path, marker: str | None, label: str
):
    """A reserved-name collision must refuse loudly, never delete or overwrite.

    The pre-existing data-loss test only ever protected a file called
    precious.txt, so a collision on the reserved namespace itself was
    untested by construction. Both shapes are exercised: a directory of
    somebody else's under the reserved name with no marker at all, and one
    carrying a marker this adapter does not recognise.
    """
    spool = _operator_owned_spool(tmp_path, "repos")
    reserved = spool / _RESERVED
    reserved.mkdir()
    (reserved / "not-ours.txt").write_text("somebody else's data\n")
    if marker is not None:
        (reserved / ".owner").write_text(marker)
    os.chmod(reserved, 0o777)

    result = _run(
        ["bash", "-c", "echo AGENT_RAN"],
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
    assert result.returncode != 0, f"{label}: the workspace started anyway"
    assert "AGENT_RAN" not in result.stdout, f"{label}: the agent ran anyway"
    assert "refusing" in result.stderr.lower(), result.stderr
    assert (reserved / "not-ours.txt").read_text() == "somebody else's data\n", (
        f"{label}: the adapter modified a namespace it does not own"
    )
    if marker is not None:
        assert (reserved / ".owner").read_text() == marker, (
            f"{label}: the adapter overwrote a foreign ownership marker"
        )
    else:
        assert not (reserved / ".owner").exists(), (
            f"{label}: the adapter claimed an occupied namespace"
        )


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_init_refuses_when_the_reserved_name_is_not_a_directory(tmp_path: Path):
    """The reserved name taken by a regular file is the same refusal.

    `mkdir -p` on a path held by a file fails, and a fix that "handled" that
    by removing the file would be the deletion this whole design exists to
    remove.
    """
    spool = _operator_owned_spool(tmp_path, "repos")
    (spool / _RESERVED).write_text("an operator file that happens to share the name\n")

    result = _run(
        ["bash", "-c", "echo AGENT_RAN"],
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
    assert result.returncode != 0
    assert "AGENT_RAN" not in result.stdout
    assert "refusing" in result.stderr.lower() or "not a directory" in result.stderr
    assert (spool / _RESERVED).read_text() == (
        "an operator file that happens to share the name\n"
    ), "the adapter replaced an operator file holding the reserved name"


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_init_refuses_to_retarget_a_transcript_symlink_outside_the_spool(
    tmp_path: Path,
):
    """`ln -sfn` replaces a symlink silently. An operator's link is not ours.

    Retargeting deletes nothing, but it silently stops capture happening
    where the operator pointed it, with nothing in the doctor output saying
    so. A link into the spool (this adapter's own, from a previous run) is
    still replaced, which is what keeps a persisted $HOME working.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    os.chmod(spool, 0o777)
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir(parents=True)
    elsewhere = tmp_path / "operator-transcripts"
    elsewhere.mkdir()
    (home / ".claude" / "projects").symlink_to("/operator-transcripts")
    os.chmod(home, 0o777)
    os.chmod(home / ".claude", 0o777)
    os.chmod(home / ".codex", 0o777)

    cmd = ["docker", "run", "--rm"]
    for k, v in {
        "AGENTIC_CAPABILITIES": "session-store",
        "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
        "AGENTIC_SESSION_STORE_URL": STORE_URL,
        "AGENTIC_SESSION_STORE_SPOOL": "/spool",
        "AGENTIC_SESSION_STORE_PARTITION": "symlink-test",
    }.items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.extend(["--add-host=host.docker.internal:host-gateway"])
    cmd.extend(["-v", f"{spool}:/spool"])
    cmd.extend(["-v", f"{home}:/home/agent"])
    cmd.extend(["-v", f"{elsewhere}:/operator-transcripts"])
    cmd.extend(["-v", f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro"])
    cmd.extend([IMAGE, "bash", "-c", "echo AGENT_RAN"])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    assert result.returncode != 0, "the adapter retargeted an operator's symlink"
    assert "AGENT_RAN" not in result.stdout
    assert "refusing to retarget" in result.stderr, result.stderr
    assert os.readlink(home / ".claude" / "projects") == "/operator-transcripts", (
        "the operator's symlink was replaced"
    )


def _run_with_persisted_home(
    spool: Path, home: Path, partition: str, extra_mounts: list[str] | None = None
) -> subprocess.CompletedProcess:
    """Start the workspace against a real (bind-mounted) $HOME and spool.

    A persisted home is what makes the transcript-root branches reachable at
    all: on the tmpfs home every other test uses, ~/.claude/projects never
    pre-exists, which is why the original data-loss defect there survived a
    green suite.
    """
    cmd = ["docker", "run", "--rm"]
    for k, v in {
        # The registry variable belongs to the lifecycle, not to this
        # capability, so it has no member in SessionStoreEnv; every other
        # test in this file spells it the same way.
        "AGENTIC_CAPABILITIES": SessionStoreContract.CAPABILITY,
        SessionStoreEnv.PROVIDER: "seshmagic",
        SessionStoreEnv.URL: STORE_URL,
        SessionStoreEnv.SPOOL: "/spool",
        SessionStoreEnv.PARTITION: partition,
    }.items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.append("--add-host=host.docker.internal:host-gateway")
    cmd.extend(["-v", f"{spool}:/spool"])
    cmd.extend(["-v", f"{home}:/home/agent"])
    cmd.extend(["-v", f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro"])
    for m in extra_mounts or []:
        cmd.extend(["-v", m])
    cmd.extend([IMAGE, "bash", "-c", "echo AGENT_RAN"])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
@pytest.mark.parametrize(
    ("partition", "link_target", "refused", "why"),
    [
        pytest.param(
            "retarget-sibling",
            "/spool/another-partition/claude",
            True,
            "a live link into a DIFFERENT partition of the same spool",
            id="sibling-partition",
        ),
        pytest.param(
            "retarget-dangling",
            "/spool/no-such-partition/claude",
            True,
            "a dangling link, which proves nothing about who made it",
            id="dangling",
        ),
        pytest.param(
            "retarget-own",
            "/spool/retarget-own/claude",
            False,
            "this run's own link, which must keep working on a re-run",
            id="own-link",
        ),
    ],
)
def test_transcript_symlink_ownership_is_the_target_not_the_spool_prefix(
    tmp_path: Path, partition: str, link_target: str, refused: bool, why: str
):
    """Under the spool is not a proof of ownership; the target is.

    The spool is a directory the operator owns, so a link into it says
    neither that this adapter created it nor that it points at the partition
    this run captures into. The first case is the one the prefix test got
    wrong and the one that costs data attention: a link into a sibling
    partition was silently repointed, so whatever was still writing through
    it stopped being captured, and the destination that had been in force was
    not even named in the log.

    The third case is here so the fix cannot be "refuse everything": a
    persisted $HOME whose link this adapter wrote on a previous run must
    still start.
    """
    spool = _host_spool(tmp_path)
    (spool / "another-partition" / "claude").mkdir(parents=True)
    os.chmod(spool / "another-partition", 0o777)
    os.chmod(spool / "another-partition" / "claude", 0o777)

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".codex").mkdir(parents=True)
    (home / ".claude" / "projects").symlink_to(link_target)
    for d in (home, home / ".claude", home / ".codex"):
        os.chmod(d, 0o777)

    result = _run_with_persisted_home(spool, home, partition)

    if refused:
        assert result.returncode != 0, f"the adapter retargeted {why}: {result.stdout}"
        assert "AGENT_RAN" not in result.stdout
        assert "refusing to retarget" in result.stderr, result.stderr
        assert os.readlink(home / ".claude" / "projects") == link_target, (
            f"the adapter replaced {why}"
        )
    else:
        assert result.returncode == 0, f"the adapter refused {why}: {result.stderr}"
        assert "AGENT_RAN" in result.stdout, result.stderr
        assert os.readlink(home / ".claude" / "projects") == link_target


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_finalize_keeps_the_partition_on_success(tmp_path: Path):
    """A successful sweep must leave the partition in place.

    The spool is an append-only local cache and the store is the durable
    copy, so nothing on this path reclaims anything. finalize.sh used to
    prune the partition here; every data-loss path found on this branch
    reached destruction through that delete, so it was removed rather than
    hardened again, and this is the end-to-end lock on it staying gone.
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
            "AGENTIC_SESSION_STORE_PARTITION": "keep-test",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    part_dir = spool / "keep-test"
    assert part_dir.is_dir(), "a successful sweep must keep its partition"
    assert (part_dir / "claude").is_dir(), "the transcript root must survive the sweep"


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
    assert (part_dir / "state.json").exists(), (
        "spool must be retained on upload failure"
    )


# --- A clean EXIT is not a clean SWEEP, and the spool is append-only ------
#
# The exporter documents in its own source that "a completed sweep exits 0
# even with per-item skips/failures; only a hard RunError (store unreachable,
# source scan failure) is non-zero." So rc=0 is consistent with failed=3
# skipped_oversize=2, i.e. five transcripts that never reached the store.
#
# finalize.sh no longer deletes anything on any path, so these tests assert
# two things: the partition survives every outcome, and the report an operator
# reads names the counters that mean "this transcript is not in the store".
#
# They drive finalize.sh directly with a stub exporter that exits 0 and prints
# a chosen summary line.

_FINALIZE_SH = "/opt/agentic/capabilities/session-store/seshmagic/finalize.sh"


def _finalize_with_stub_exporter(
    tmp_path: Path,
    stub_body: str | list[str],
    part_name: str,
    budget_s: int = 2,
    reserved_namespace: bool = False,
) -> tuple[subprocess.CompletedProcess, Path, float]:
    """Run finalize.sh against a partition with a stubbed exporter.

    The partition is built inside the container, as the agent user, so it is
    writable by the process under test: a host-built partition is owned by
    the host uid, which the agent cannot write into on Linux, and a partition
    the hook cannot touch would pass a survives-the-sweep assertion for the
    wrong reason. See _stage_partition_sh.

    Pass a LIST of stub bodies to run several sequential sweeps against the
    same partition, each with its own exporter output. That is what exercises
    state carried between sweeps, which a single sweep cannot see.

    budget_s is exported as AGENTIC_FINALIZE_BUDGET_S, standing in for what
    entrypoint.sh passes per exit path. It is kept small here so a hung stub
    fails fast rather than sitting on finalize.sh's generous no-budget
    default.

    reserved_namespace puts EXPORTER_STATE_FILE inside
    ${SPOOL}/.agentic-session-store/${PARTITION}, which finalize.sh requires
    before it will write its `.sweep-rejected` record. The default is the
    legacy layout, where the hook can only warn that it has nowhere to record a
    rejection, so a test meaning to exercise the RECORD must opt in or it
    silently exercises the warning instead.

    Returns (result, transcript_path, elapsed_seconds). The transcript file
    still existing means the spool was retained.
    """
    bodies = [stub_body] if isinstance(stub_body, str) else stub_body

    spool = _host_spool(tmp_path)
    part_dir = spool / part_name
    stage = _stage_partition_sh(
        part_name,
        {
            "state.json": "{}\n",
            "claude/s.jsonl": "{}\n",
        },
    )

    sweeps = ""
    for i, body in enumerate(bodies):
        sweeps += f"""
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
{body}
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
echo "=== SWEEP {i} ===" >&2
{_FINALIZE_SH}
echo "FINALIZE_RC_{i}=$?"
"""

    state_file = (
        f"/spool/.agentic-session-store/{part_name}/state.json"
        if reserved_namespace
        else f"/spool/{part_name}/state.json"
    )
    reserved_mkdir = (
        f"mkdir -p /spool/.agentic-session-store/{part_name}"
        if reserved_namespace
        else ""
    )

    script = f"""
set -e
{stage}
{reserved_mkdir}
mkdir -p /tmp/fakebin
export PATH=/tmp/fakebin:$PATH
export SESSION_STORE_URL=http://unused.invalid
export EXPORTER_STATE_FILE={state_file}
export AGENTIC_FINALIZE_BUDGET_S={budget_s}
{sweeps}
echo "FINALIZE_RC=$?"
"""
    start = time.monotonic()
    result = _run(
        ["bash", "-c", script],
        extra_mounts=[f"{spool}:/spool"],
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
    that made the sweep incomplete so an operator can act.
    """
    result, transcript, _ = _finalize_with_stub_exporter(
        tmp_path,
        f'echo "{summary}"\nexit 0\n',
        f"nonzero-{counter}",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert transcript.exists(), (
        f"an incomplete sweep ({counter} nonzero) must keep the partition"
    )
    assert "INCOMPLETE" in result.stderr, "finalize must report the incomplete sweep"
    assert f"{counter}=1" in result.stderr, (
        f"finalize must name {counter} as the counter that made the sweep incomplete"
    )


@pytest.mark.integration
def test_finalize_keeps_partition_and_transcripts_on_a_clean_sweep(tmp_path: Path):
    """THE contract, stated positively: a clean, fully successful sweep
    leaves the partition and every transcript in it exactly where they are.

    This is what replaced the prune. finalize.sh used to delete the partition
    right here, and every data-loss path found on this branch reached
    destruction through that one line, so the delete was removed rather than
    re-gated. The spool is now an append-only local cache and the store is
    the durable copy.

    The report must also stay honest about it: an operator reading this run
    must not be left thinking the successful path reclaimed anything.
    """
    summary = (
        "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=1 "
        "duplicate=0 rejected=0 skipped_oversize=0 failed=0"
    )
    result, transcript, _ = _finalize_with_stub_exporter(
        tmp_path,
        f'echo "{summary}"\nexit 0\n',
        "clean-sweep",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert transcript.exists(), "a clean sweep must leave its transcripts in place"
    assert transcript.parent.parent.is_dir(), (
        "a clean sweep must leave the partition directory in place"
    )
    assert "upload complete" in result.stderr, "finalize must report the clean sweep"
    assert "spool retained" in result.stderr, (
        "the report must say the spool was retained, since nothing is ever deleted"
    )


@pytest.mark.integration
def test_finalize_treats_exit_3_as_a_completed_sweep_not_a_failure(tmp_path: Path):
    """Exit 3 means "the sweep RAN but did not capture everything it found".

    agentic-session-exporter reserves it for a partial capture: the summary
    line is present and accurate, and something was rejected, oversize,
    unconfirmed or failed. It is deliberately distinct from the hard-failure 1.

    Before this was handled, any non-zero status took the "upload FAILED"
    branch and returned early. That would be a regression twice over once a
    consuming image picks up an exporter that emits 3: a partial capture is
    reported as a TOTAL upload failure, and the early return skips the
    rejection record, which is the only thing stopping a LATER sweep printing
    a false completion claim about the same partition.
    """
    summary = (
        "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=0 "
        "duplicate=0 rejected=1 skipped_oversize=0 failed=0"
    )
    result, transcript, _ = _finalize_with_stub_exporter(
        tmp_path,
        f'echo "{summary}"\nexit 3\n',
        "exit-3-partial",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert "upload FAILED" not in result.stderr, (
        "exit 3 is a completed sweep, not a failed one; reporting it as a "
        f"total failure hides the counters. stderr={result.stderr}"
    )
    # The counter path ran, so the report names what was actually refused.
    assert "rejected=1" in result.stderr or "REFUSED" in result.stderr, (
        f"the counter report must survive exit 3. stderr={result.stderr}"
    )
    assert transcript.exists(), "nothing is ever deleted on any path"


@pytest.mark.integration
def test_exit_3_rejection_is_recorded_and_survives_into_the_next_sweep(
    tmp_path: Path,
):
    """The reason preventing the early return mattered, asserted directly.

    An earlier version of the exit-3 test only checked that the counters were
    reported. A regression that parsed counters but returned before writing
    `.sweep-rejected` would have passed it, and that file is the entire point:
    the exporter forgets a rejection after the sweep that hit it, so without
    the record a LATER sweep prints "upload complete" about a partition holding
    a transcript the store refused.

    Two sweeps, the second deliberately clean, which is what a later run looks
    like once the rejected transcript is marked done in exporter state.
    """
    rejected = (
        "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=0 "
        "duplicate=0 rejected=1 skipped_oversize=0 failed=0"
    )
    clean = (
        "run: discovered=1 skipped_unchanged=1 uploaded=0 accepted=0 "
        "duplicate=0 rejected=0 skipped_oversize=0 failed=0"
    )
    result, _, _ = _finalize_with_stub_exporter(
        tmp_path,
        [f'echo "{rejected}"\nexit 3\n', f'echo "{clean}"\nexit 0\n'],
        "exit-3-recorded",
        reserved_namespace=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"

    marker = (
        _host_spool(tmp_path)
        / ".agentic-session-store"
        / "exit-3-recorded"
        / ".sweep-rejected"
    )
    assert marker.exists(), (
        "exit 3 must still reach the rejection record; without it a later "
        f"sweep claims completeness. stderr={result.stderr}"
    )
    assert "agentic-session-store-rejection-v1" in marker.read_text(), (
        "the record must carry its format id"
    )
    assert "upload complete" not in result.stderr, (
        "the SECOND sweep looks clean to the counters, and must still not be "
        f"reported as complete. stderr={result.stderr}"
    )


@pytest.mark.integration
def test_finalize_believes_an_unconfirmed_counter_even_on_exit_zero(tmp_path: Path):
    """The older-exporter door into the same false completion claim.

    This hook reads counters even from an exporter that exited 0, precisely so
    an old binary reporting loss is still believed. An old-contract exporter
    that emits `unconfirmed=1` and exits 0 would, without parsing that counter,
    be reported as a complete upload. Trusting only the new exit status would
    have left that door open.
    """
    summary = (
        "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=0 "
        "duplicate=0 rejected=0 skipped_oversize=0 failed=0 unconfirmed=1"
    )
    result, _, _ = _finalize_with_stub_exporter(
        tmp_path,
        f'echo "{summary}"\nexit 0\n',
        "unconfirmed-rc0",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "upload complete" not in result.stderr, (
        f"unconfirmed=1 is not a complete upload. stderr={result.stderr}"
    )
    assert "unconfirmed=1" in result.stderr, (
        f"the report must name what was unconfirmed. stderr={result.stderr}"
    )


@pytest.mark.integration
def test_finalize_still_accepts_a_summary_without_the_unconfirmed_counter(
    tmp_path: Path,
):
    """`unconfirmed` is optional, and must stay optional.

    The exporter binary is operator-supplied and older builds do not emit this
    counter. Requiring it would make this hook reject every summary line they
    produce, turning a compatibility feature into a hard failure.
    """
    summary = (
        "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=1 "
        "duplicate=0 rejected=0 skipped_oversize=0 failed=0"
    )
    result, _, _ = _finalize_with_stub_exporter(
        tmp_path,
        f'echo "{summary}"\nexit 0\n',
        "no-unconfirmed-field",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "upload complete" in result.stderr, (
        "a clean sweep from an older exporter must still report complete; "
        f"stderr={result.stderr}"
    )
    assert "no parseable summary" not in result.stderr, (
        "a missing optional counter must not invalidate the summary line"
    )


@pytest.mark.integration
def test_finalize_trusts_exit_3_when_every_counter_it_parses_reads_zero(
    tmp_path: Path,
):
    """The false-completion case, and the reason rc=3 is preserved.

    This hook decides completeness from failed, skipped_oversize and rejected.
    Those are not the only ways a sweep can come up short: the exporter also
    counts `unconfirmed`, envelopes it SENT for which the store returned no
    matching outcome. A sweep whose only loss is unconfirmed reports
    failed=0 skipped_oversize=0 rejected=0 and still exits 3.

    An earlier version of this fix normalised rc=3 to 0, so that sweep reached
    the completion path and printed "upload complete" while its own exit status
    said the opposite. A hook written to prevent false completion claims would
    have been making one.
    """
    summary = (
        "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=0 "
        "duplicate=0 rejected=0 skipped_oversize=0 failed=0 unconfirmed=1"
    )
    result, _, _ = _finalize_with_stub_exporter(
        tmp_path,
        f'echo "{summary}"\nexit 3\n',
        "exit-3-unconfirmed",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert "upload complete" not in result.stderr, (
        "a sweep the exporter called incomplete must never be reported as "
        f"complete, whatever the parsed counters say. stderr={result.stderr}"
    )
    assert "INCOMPLETE" in result.stderr, (
        f"the report must say the sweep was incomplete. stderr={result.stderr}"
    )


@pytest.mark.integration
def test_finalize_reports_a_sweep_with_only_duplicate_and_unchanged_as_complete(
    tmp_path: Path,
):
    """Neither duplicate nor skipped_unchanged is a per-sweep loss, so
    neither may be reported as an incomplete sweep, or every repeat sweep
    cries wolf and the INCOMPLETE signal stops meaning anything.

    They are not equally strong, though, and only one of them is evidence
    of an upload. duplicate means the store already holds that content,
    which it knows because it dedups on content_hash. skipped_unchanged
    means only that the exporter's state file marks the item done, and the
    exporter marks rejected items done too, so it is equally consistent
    with a transcript the store refused. What covers that case is the
    persisted rejection record, not this counter: see
    test_finalize_never_reports_complete_after_a_recorded_rejection.
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
    assert transcript.exists(), "the partition must survive a clean sweep"
    assert "upload complete" in result.stderr, (
        "duplicate/skipped_unchanged are not failures and must not read as INCOMPLETE"
    )
    assert "INCOMPLETE" not in result.stderr, result.stderr


# The exporter is a binary DEPLOYMENT supplies (see the capability README's
# provisioning contract), not one this image builds, so finalize.sh cannot
# know what a given build prints. It used to replay the captured combined
# output to stderr verbatim so the summary line was visible, which put
# whatever that build chose to print into durable container logs. This canary
# stands in for the thing that costs the most: the store write credential the
# adapter withholds from the agent precisely so it reaches nothing but the
# exporter.
_EXPORTER_CANARY = "Authorization: Bearer sk-store-write-CANARY123"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("part_name", "stub_body", "expected_report"),
    [
        pytest.param(
            "canary-clean",
            f'echo "{_EXPORTER_CANARY}" >&2\n'
            'echo "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=1 '
            'duplicate=0 rejected=0 skipped_oversize=0 failed=0"\n'
            "exit 0\n",
            "upload complete",
            id="clean-sweep",
        ),
        pytest.param(
            "canary-failed",
            f'echo "{_EXPORTER_CANARY}" >&2\nexit 9\n',
            "rc=9",
            id="failed-sweep",
        ),
    ],
)
def test_finalize_never_replays_the_exporters_own_output(
    tmp_path: Path, part_name: str, stub_body: str, expected_report: str
):
    """No byte the exporter chose may reach this hook's log, on any path.

    Both paths are covered because the failure path is the one with a reason
    to relent: the exporter's diagnostic is the only thing that says why a
    sweep failed, so "just this once, so the operator can debug it" is exactly
    how the replay would come back. It must still report enough to act on --
    the failure class, the status, the retained spool, and the procedure that
    recovers the missing diagnostic -- without reproducing the stream.
    """
    result, transcript, _ = _finalize_with_stub_exporter(tmp_path, stub_body, part_name)
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert transcript.exists(), "the spool is retained on every path"
    assert "CANARY123" not in result.stderr, (
        "the exporter's output was replayed into the container log; a build "
        "that prints an auth header leaks the store write credential"
    )
    assert "CANARY123" not in result.stdout, result.stdout
    assert expected_report in result.stderr, result.stderr


@pytest.mark.integration
def test_finalize_reports_a_failed_sweep_without_the_exporters_diagnostic(
    tmp_path: Path,
):
    """A failure an operator cannot act on is not an acceptable trade for the
    leak. Withholding the exporter's own diagnostic is only defensible if the
    report names the procedure that recovers it, so that is asserted here
    rather than left to the reviewer's memory of the comment.
    """
    result, _, _ = _finalize_with_stub_exporter(
        tmp_path,
        'echo "boom" >&2\nexit 9\n',
        "failure-is-diagnosable",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FAILED (rc=9)" in result.stderr, result.stderr
    assert "spool retained" in result.stderr, result.stderr
    assert "re-run" in result.stderr and "SeshMagicSessionExporter" in result.stderr, (
        "a withheld diagnostic must come with the way to get it back"
    )


@pytest.mark.integration
def test_finalize_reconstructs_the_summary_rather_than_quoting_it(tmp_path: Path):
    """The clean-sweep report is rebuilt from the parsed counters.

    A stub whose summary line carries trailing junk after the last counter
    proves it: quoting the matched line would carry that junk into the log,
    reconstructing from `[0-9][0-9]*` matches cannot.
    """
    result, _, _ = _finalize_with_stub_exporter(
        tmp_path,
        'echo "run: discovered=2 skipped_unchanged=0 uploaded=2 accepted=2 '
        "duplicate=0 rejected=0 skipped_oversize=0 failed=0 "
        'token=sk-store-write-CANARY123"\nexit 0\n',
        "reconstructed-summary",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "upload complete" in result.stderr, result.stderr
    assert "discovered=2" in result.stderr and "uploaded=2" in result.stderr, (
        "the reconstructed report must still carry the counters"
    )
    assert "CANARY123" not in result.stderr, (
        "the summary line was quoted rather than rebuilt from its counters"
    )


@pytest.mark.integration
def test_finalize_keeps_spool_when_no_summary_line_is_printed(tmp_path: Path):
    """An unreadable summary is not evidence of success. Absent the line, the
    sweep's outcome is unknown, and unknown must be reported as unknown
    rather than as a completed upload.
    """
    result, transcript, _ = _finalize_with_stub_exporter(
        tmp_path,
        'echo "uploading things"\nexit 0\n',
        "no-summary",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert transcript.exists(), "an unparseable summary must keep the partition"
    assert "no parseable summary" in result.stderr


@pytest.mark.integration
def test_finalize_keeps_a_rejected_transcript_across_the_next_sweep(tmp_path: Path):
    """A transcript the store REFUSED must still be on disk after the next
    sweep reports itself clean.

    The exporter marks state for every item the store returned a result for,
    including per-item rejected (lib.rs:202-204), because "the store processed
    it and a re-send would be wasted". But rejected means the store REFUSED
    it: processed, not stored. So the divergence is invisible one sweep later:

      Sweep 1: rejected=1        -> reported INCOMPLETE, naming the counter.
      Sweep 2: skipped_unchanged=1, all three counters zero -> reads clean,
               even though that transcript is still not in the store.

    Sweep 2 needs no recovery scenario: it happens on any run where the
    orchestrator passes a stable AGENTIC_SESSION_STORE_PARTITION, since only
    the ${HOSTNAME} default is per-container.

    This used to be a data-loss path, because sweep 2's clean reading
    authorized a prune. It is not one any more for the reason that closes the
    whole class: no sweep, clean or otherwise, deletes anything. Sweep 1's
    report is still the operator's signal, and it must name the counter.

    This partition is in the LEGACY layout (the state file sits in the
    transcript partition, which is what the shared helper stages), so no
    rejection record can be written for it: that would put a file of this
    adapter's into a directory the operator may own. The current-layout
    behaviour, where sweep 2 does not read clean, is
    test_finalize_never_reports_complete_after_a_recorded_rejection.
    """
    rejected_sweep = (
        'echo "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=0 '
        'duplicate=0 rejected=1 skipped_oversize=0 failed=0"\nexit 0\n'
    )
    # Exactly what the exporter reports next time: the rejected item is now
    # marked, so it is no longer even offered for upload.
    clean_looking_sweep = (
        'echo "run: discovered=1 skipped_unchanged=1 uploaded=0 accepted=0 '
        'duplicate=0 rejected=0 skipped_oversize=0 failed=0"\nexit 0\n'
    )

    result, transcript, _ = _finalize_with_stub_exporter(
        tmp_path,
        [rejected_sweep, clean_looking_sweep],
        "rejected-then-clean",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC_0=0" in result.stdout, "finalize.sh must always exit 0"
    assert "FINALIZE_RC_1=0" in result.stdout, "finalize.sh must always exit 0"
    assert transcript.exists(), (
        "a transcript the store REJECTED was deleted by the following sweep, "
        "which sees only skipped_unchanged and reads as clean"
    )
    assert "INCOMPLETE" in result.stderr, "sweep 1 must report the incomplete sweep"
    assert "rejected=1" in result.stderr, "sweep 1 must name the rejecting counter"


# --- A rejection outlives the container that saw it ---------------------------
#
# The counters of a LATER sweep cannot see a rejection: the exporter marks a
# rejected item done, so it is counted as skipped_unchanged from then on and
# every loss counter reads zero. Without a persisted record, that later sweep
# prints "session-store upload complete" about a partition holding a transcript
# the store refused. Nothing is deleted, so this is a false completion claim
# rather than data loss, which for a corpus feeding learning loops is the
# expensive failure: an absent session is what nothing downstream can notice.
#
# These tests drive finalize.sh in SEPARATE CONTAINERS over one host-backed
# spool, because "a later sweep in a different container" is the case the
# record has to survive and a second call inside one container would not test
# it. The partition is staged in the CURRENT layout, with the metadata in the
# reserved namespace, since that is the only layout where a record may be
# written at all.

_META_SEGMENT = ".agentic-session-store"


def _stage_namespaced_partition_sh(part_name: str) -> str:
    """Shell staging a current-layout partition: transcripts and metadata split.

    Both halves are built in the container as the agent user, for the reason
    _stage_partition_sh gives: a host-written fixture carries the host's uid,
    and a metadata directory finalize.sh cannot write into would pass a
    "no record was written" assertion for entirely the wrong reason.
    """
    return "\n".join(
        [
            _stage_partition_sh(part_name, {"claude/s.jsonl": "{}\n"}),
            _stage_partition_sh(f"{_META_SEGMENT}/{part_name}", {"state.json": "{}\n"}),
        ]
    )


def _finalize_in_its_own_container(
    spool: Path,
    part_name: str,
    stub_body: str,
    stage: str = "",
    legacy_layout: bool = False,
) -> subprocess.CompletedProcess:
    """One finalize.sh run, in a container of its own, over a shared spool."""
    meta = (
        f"/spool/{part_name}"
        if legacy_layout
        else f"/spool/{_META_SEGMENT}/{part_name}"
    )
    script = f"""
set -e
{stage}
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/SeshMagicSessionExporter << 'FAKE_EXPORTER_EOF'
#!/usr/bin/env bash
{stub_body}
FAKE_EXPORTER_EOF
chmod +x /tmp/fakebin/SeshMagicSessionExporter
export PATH=/tmp/fakebin:$PATH
export {ExporterEnv.URL}=http://unused.invalid
export {ExporterEnv.STATE_FILE}={meta}/state.json
{_FINALIZE_SH}
echo "FINALIZE_RC=$?"
"""
    return _run(["bash", "-c", script], extra_mounts=[f"{spool}:/spool"])


_REJECTED_SWEEP = (
    'echo "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=0 '
    'duplicate=0 rejected=1 skipped_oversize=0 failed=0"\nexit 0\n'
)
# Exactly what the exporter reports next time: the rejected item is marked in
# its state file, so it is counted as unchanged and never offered again.
_CLEAN_LOOKING_SWEEP = (
    'echo "run: discovered=1 skipped_unchanged=1 uploaded=0 accepted=0 '
    'duplicate=0 rejected=0 skipped_oversize=0 failed=0"\nexit 0\n'
)


@pytest.mark.integration
def test_finalize_never_reports_complete_after_a_recorded_rejection(tmp_path: Path):
    """A partition that has ever had a rejection may never afterwards report
    a complete upload, no matter how clean a later sweep's counters read.

    Sweep 1 (container A) hits rejected=1. Sweep 2 (container B, same spool)
    sees only skipped_unchanged, so all three loss counters are zero and the
    counters alone would say "upload complete" about a transcript the store
    refused and will never hold.

    The report must also be actionable: it names the record and says the
    transcript is in the spool and not in the store, because a warning an
    operator cannot act on decays into one they scroll past.
    """
    spool = _host_spool(tmp_path)
    part = "rejected-sticky"

    first = _finalize_in_its_own_container(
        spool, part, _REJECTED_SWEEP, stage=_stage_namespaced_partition_sh(part)
    )
    assert first.returncode == 0, f"container failed: {first.stderr}"
    assert "FINALIZE_RC=0" in first.stdout, "finalize.sh must always exit 0"
    assert "INCOMPLETE" in first.stderr and "rejected=1" in first.stderr, first.stderr

    record = spool / _META_SEGMENT / part / ".sweep-rejected"
    assert record.exists(), (
        "the rejection was recorded nowhere, so nothing outlives this container"
    )

    second = _finalize_in_its_own_container(spool, part, _CLEAN_LOOKING_SWEEP)
    assert second.returncode == 0, f"container failed: {second.stderr}"
    assert "FINALIZE_RC=0" in second.stdout, "finalize.sh must always exit 0"
    assert "upload complete" not in second.stderr, (
        "a sweep whose counters read clean reported a COMPLETE upload for a "
        "partition holding a transcript the store refused"
    )
    assert "INCOMPLETE" in second.stderr, second.stderr
    assert ".sweep-rejected" in second.stderr, (
        "the report must name the record so an operator can find and clear it"
    )
    assert (spool / part / "claude" / "s.jsonl").exists(), (
        "nothing on this path may delete a transcript"
    )
    assert record.exists(), "the record must not be cleared by the hook itself"


@pytest.mark.integration
def test_finalize_still_reports_completion_on_a_partition_that_never_rejected(
    tmp_path: Path,
):
    """The rejection record must not make every sweep report a problem.

    A signal that fires on partitions with nothing wrong is the failure this
    fix is supposed to prevent, one step removed: an operator who learns to
    ignore INCOMPLETE cannot be told about the real one. Two sweeps, two
    containers, one spool, no rejection anywhere: both report completion and
    no record is written.
    """
    spool = _host_spool(tmp_path)
    part = "never-rejected"
    clean = (
        'echo "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=1 '
        'duplicate=0 rejected=0 skipped_oversize=0 failed=0"\nexit 0\n'
    )

    first = _finalize_in_its_own_container(
        spool, part, clean, stage=_stage_namespaced_partition_sh(part)
    )
    assert first.returncode == 0, f"container failed: {first.stderr}"
    assert "upload complete" in first.stderr, first.stderr

    second = _finalize_in_its_own_container(spool, part, _CLEAN_LOOKING_SWEEP)
    assert second.returncode == 0, f"container failed: {second.stderr}"
    assert "upload complete" in second.stderr, second.stderr
    assert "INCOMPLETE" not in second.stderr, second.stderr
    assert not (spool / _META_SEGMENT / part / ".sweep-rejected").exists(), (
        "a partition that never had a rejection must carry no record"
    )


@pytest.mark.integration
def test_finalize_refuses_to_record_a_rejection_in_a_legacy_partition(tmp_path: Path):
    """On the legacy layout the metadata directory IS the transcript
    partition, which the operator may own, and this adapter writes no file of
    its own there. So the record is refused rather than written outside the
    reserved namespace: a health signal is not worth the unnamespaced-write
    defect that the namespace exists to close.

    Refusing silently would be its own false claim, so the sweep that hits the
    rejection must say that it could not record it and that a later sweep will
    read clean. That is the gap, stated where an operator sees it.
    """
    spool = _host_spool(tmp_path)
    part = "legacy-rejected"

    result = _finalize_in_its_own_container(
        spool,
        part,
        _REJECTED_SWEEP,
        stage=_stage_partition_sh(
            part, {"state.json": "{}\n", "claude/s.jsonl": "{}\n"}
        ),
        legacy_layout=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "FINALIZE_RC=0" in result.stdout, "finalize.sh must always exit 0"
    assert "INCOMPLETE" in result.stderr and "rejected=1" in result.stderr, (
        result.stderr
    )
    assert "WARNING" in result.stderr and "skipped_unchanged" in result.stderr, (
        "a rejection that cannot be recorded must be reported as such"
    )
    written = sorted(p.name for p in (spool / part).iterdir())
    assert ".sweep-rejected" not in written, (
        f"finalize.sh wrote into the operator-owned transcript partition: {written}"
    )
    assert not (spool / _META_SEGMENT).exists(), (
        "a legacy partition must not gain a metadata namespace from a finalize run"
    )


@pytest.mark.integration
def test_finalize_reports_a_retried_failure_as_complete(tmp_path: Path):
    """A transient failure that later succeeds must stop being reported.

    Failed items are left unmarked in exporter state, so the next sweep
    genuinely retries them and, on success, they really are stored. A sticky
    report here would turn every transient network blip into a partition that
    reads INCOMPLETE forever, and an operator would stop believing the signal.
    """
    failed_sweep = (
        'echo "run: discovered=1 skipped_unchanged=0 uploaded=0 accepted=0 '
        'duplicate=0 rejected=0 skipped_oversize=0 failed=1"\nexit 0\n'
    )
    retry_succeeded = (
        'echo "run: discovered=1 skipped_unchanged=0 uploaded=1 accepted=1 '
        'duplicate=0 rejected=0 skipped_oversize=0 failed=0"\nexit 0\n'
    )

    result, transcript, _ = _finalize_with_stub_exporter(
        tmp_path,
        [failed_sweep, retry_succeeded],
        "failed-then-ok",
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert transcript.exists(), "the partition must survive both sweeps"
    # The stub harness prints "=== SWEEP n ===" before each run, so the two
    # reports can be told apart. Asserting on the whole stderr would let the
    # first sweep's INCOMPLETE satisfy an assertion about the second.
    sweeps = result.stderr.split("=== SWEEP ")
    assert len(sweeps) == 3, result.stderr
    assert "failed=1" in sweeps[1] and "INCOMPLETE" in sweeps[1], sweeps[1]
    assert "upload complete" in sweeps[2], sweeps[2]
    assert "INCOMPLETE" not in sweeps[2], (
        "a retried failure that succeeded must stop reading as INCOMPLETE"
    )


@pytest.mark.integration
def test_finalize_bounds_a_hanging_exporter_and_keeps_the_spool(tmp_path: Path):
    """A wedged upload must not hang the run, and must keep the spool.

    Unbounded, a stuck DNS lookup or hung connection turns a completed agent
    run into a hang; during `docker stop` it burns the grace until SIGKILL,
    so the run reports 137 instead of the agent's real exit code. finalize.sh
    bounds the exporter at __UPLOAD_TIMEOUT_S and reports a timeout as an
    upload failure, naming the spool it left behind.
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
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
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
            capture_output=True,
            text=True,
            timeout=_DOCKER_STOP_TIMEOUT_S,
        )
        elapsed = time.monotonic() - start

        inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.ExitCode}}", container_name],
            capture_output=True,
            text=True,
            check=True,
        )
        exit_code = int(inspect.stdout.strip())
        logs = subprocess.run(
            ["docker", "logs", container_name],
            capture_output=True,
            text=True,
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


# --- No finalizer to run means no wrapper at all ------------------------
#
# Every other test in this file enables a capability, which is exactly why the
# unconditional wrapper shipped: a consumer who opted into nothing still got
# it, lost PID 1, and lost the substrate's stop grace to the wrapper's own
# 1.5s window. These cover the shape nothing else did.

_NOFINALIZE_CAPABILITY = Path(__file__).parent / "fixtures" / "nofinalize-capability"

# A command that traps TERM and needs longer than the wrapper's
# __TERM_GRACE_TICKS (1.5s) to finish flushing. Under the unconditional
# wrapper this was SIGKILLed mid-flush: FLUSH_COMPLETE never printed and the
# container exited 137 instead of the command's own 0.
_PID_1_COMM = 'echo "PID1_COMM=$(cat /proc/1/comm)"'

_FLUSHING_AGENT = (
    'trap "echo CAUGHT_TERM; sleep 3; echo FLUSH_COMPLETE; exit 0" TERM; '
    "echo READY; while true; do sleep 0.2; done"
)


@pytest.mark.integration
def test_no_capability_keeps_the_substrates_full_stop_grace():
    """`docker stop -t 10` on a container that enabled no capability must give
    the command the full grace, not the wrapper's 1.5s.

    This is the regression, verbatim: a 10s grace, a 3s flush, and before the
    fix a SIGKILL at 1.5s that cost both the flush and the exit code.
    """
    grace_s = 10
    exit_code, elapsed, logs = _docker_stop_scenario(
        _FLUSHING_AGENT,
        "no-capability-grace-test",
        grace_s,
        env={"AGENTIC_CAPABILITIES": ""},
    )
    assert "CAUGHT_TERM" in logs, f"the command never received SIGTERM; logs=\n{logs}"
    assert "FLUSH_COMPLETE" in logs, (
        f"the command was killed mid-flush inside the grace; logs=\n{logs}"
    )
    assert exit_code == 0, (
        f"expected the command's own exit code, not 137; logs=\n{logs}"
    )
    # It really used the grace rather than exiting early for some other
    # reason: the flush alone is 3s, well past the 1.5s wrapper window.
    assert elapsed >= 3, f"the 3s flush cannot have run in {elapsed:.2f}s"
    assert elapsed < grace_s, (
        f"the command exited on its own, before docker's SIGKILL, took {elapsed:.2f}s"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("case", "env", "mounts"),
    [
        # Nothing registered at all: the consumer opted into nothing.
        ("no-capabilities", {"AGENTIC_CAPABILITIES": ""}, []),
        # Registered but never given a provider. 5.6 skips its adapter, so
        # there is no finalizer and no reason to wrap.
        ("registered-unset", {"AGENTIC_CAPABILITIES": "session-store memory"}, []),
        # Explicitly disabled with the "none" sentinel, same reasoning.
        (
            "provider-none",
            {
                "AGENTIC_CAPABILITIES": "session-store",
                "AGENTIC_SESSION_STORE_PROVIDER": "none",
            },
            [],
        ),
        # Genuinely active -- registered, provider set, doctor passing,
        # adapter sourced -- but the adapter ships no finalize.sh, so there
        # is still no post-agent work to stay alive for.
        (
            "active-without-finalize",
            {
                "AGENTIC_CAPABILITIES": "nofinalize",
                "AGENTIC_NOFINALIZE_PROVIDER": "plain",
            },
            [f"{_NOFINALIZE_CAPABILITY}:/opt/agentic/capabilities/nofinalize:ro"],
        ),
    ],
)
def test_command_is_pid_1_when_no_finalizer_would_run(
    case: str, env: dict[str, str], mounts: list[str]
):
    """With nothing to finalize, the entrypoint must `exec`, so the command is
    PID 1 and the substrate's signal and grace semantics reach it directly.

    PID 1 is the observable that distinguishes exec from the wrapper, and it
    is the property the grace test above depends on.

    The command is written so that bash stays PID 1: given a single external
    command, `bash -c` execs it in place, and the answer would then be that
    program's name rather than the shell the substrate was handed.
    """
    result = _run(["bash", "-c", _PID_1_COMM], env=env, extra_mounts=mounts)
    assert result.returncode == 0, f"container failed [{case}]: {result.stderr}"
    assert "PID1_COMM=bash" in result.stdout, (
        f"[{case}] expected the command at PID 1, got {result.stdout.strip()!r}"
    )


@pytest.mark.integration
def test_an_active_finalizer_still_gets_the_wrapper():
    """The other half of the decision: one real finalizer and the wrapper is
    back, command not PID 1, finalize running after the command exits.

    Uses the probe fixture rather than session-store so this holds with no
    backend reachable, and asserts on the fixture's own finalize output.
    """
    result = _run(
        ["bash", "-c", _PID_1_COMM],
        env={
            "AGENTIC_CAPABILITIES": "probe",
            "AGENTIC_PROBE_PROVIDER": "probe",
        },
        extra_mounts=[f"{_PROBE_CAPABILITY}:/opt/agentic/capabilities/probe:ro"],
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "PID1_COMM=entrypoint.sh" in result.stdout, (
        f"expected the wrapper at PID 1, got {result.stdout.strip()!r}"
    )
    assert "PROBE_FINALIZE PROBE_SECRET=probe-owns-this" in result.stderr, result.stderr


@pytest.mark.integration
def test_an_active_finalizer_still_runs_on_docker_stop():
    """And the wrapper's post-agent moment survives `docker stop`, which is
    the behaviour the exec branch must not be allowed to cost.
    """
    grace_s = 10
    exit_code, _elapsed, logs = _docker_stop_scenario(
        'trap "exit 3" TERM; while true; do :; done',
        "probe-capability-stop-test",
        grace_s,
        env={
            "AGENTIC_CAPABILITIES": "probe",
            "AGENTIC_PROBE_PROVIDER": "probe",
        },
        extra_mounts=[f"{_PROBE_CAPABILITY}:/opt/agentic/capabilities/probe:ro"],
    )
    assert exit_code == 3, f"expected the agent's own exit code; logs=\n{logs}"
    assert "PROBE_FINALIZE PROBE_SECRET=probe-owns-this" in logs, logs


# --- The escalation window's set -e race --------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENTRYPOINT_SH = _REPO_ROOT / "workspace" / "entrypoint.sh"

# The whole classification -- `__signaled=0` and the escalation window it
# gates -- lifted verbatim out of entrypoint.sh. Extracted rather than
# restated so the test exercises the shipped code: a restatement would only
# test the test. The `__signaled=0` line is included because the clean path's
# whole observable behavior is that the block leaves it alone.
#
# Deliberately tolerant of the condition's tail, so this extraction still
# matches the pre-fix shape (`-gt 128` alone) as well as the shipped one
# (`-gt 128` AND a signal actually received). A test that could only extract
# the fixed block could not be run against the commit it was written for.
_ESCALATION_BLOCK = re.compile(
    r'^__signaled=0$\n^if \[ "\$\{__rc\}" -gt 128 \][^\n]*; then$.*?^fi$',
    re.MULTILINE | re.DOTALL,
)


def _escalation_block() -> str:
    match = _ESCALATION_BLOCK.search(_ENTRYPOINT_SH.read_text())
    assert match, f"escalation block not found in {_ENTRYPOINT_SH}"
    return match.group(0)


@pytest.mark.integration
def test_escalation_survives_the_child_dying_mid_kill(tmp_path: Path):
    """The child dying BETWEEN `kill -0` and `kill -KILL` must not abort the
    wrapper before finalizers run.

    This is the race itself, made deterministic. The window's two calls have
    exactly three possible outcomes, and a stub `kill` can produce any of
    them on demand:

      child already gone  -> `kill -0` fails, the guard short-circuits.
      child still alive   -> both calls succeed.
      child dies BETWEEN  -> `kill -0` succeeds, `kill -KILL` fails (ESRCH).

    Only the third is the defect, and it is invisible to the obvious test by
    construction: the other two pass either way, so hand-testing exercises
    precisely the cases that cannot fail. Under `set -e`, the pre-fix
    `kill -0 ... && kill -KILL ...` AND-list returns non-zero as a whole in
    the third case, and a non-zero simple list is fatal, so the entrypoint
    exits before __run_finalizers is ever called: capture silently skipped,
    container exit non-zero, no explanation.

    Runs the shipped block in a local bash with `set -e` in force, the same
    discipline entrypoint.sh runs it under (line 30). Reaching the line after
    the block is the whole assertion.
    """
    script = tmp_path / "race.sh"
    script.write_text(
        "set -e\n"
        "__TERM_GRACE_TICKS=2\n"
        "__child=424242\n"
        "__rc=143\n"
        # A signal really did reach the wrapper in each of these: rc=143 is
        # what `wait` reports when the TERM trap interrupts it.
        "__signal_received=1\n"
        # The stub IS the race: alive when probed, gone when signalled.
        "kill() {\n"
        '    case "$1" in\n'
        "        -0) return 0 ;;\n"
        "        -KILL) return 1 ;;\n"
        "    esac\n"
        "    return 0\n"
        "}\n"
        # `wait` on a pid that was never our child would fail immediately and
        # mask what is being measured; stub it to the SIGKILL status the real
        # one reports here.
        "wait() { return 137; }\n"
        f"{_escalation_block()}\n"
        'echo "REACHED signaled=${__signaled} rc=${__rc}"\n'
    )
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=30
    )
    assert "REACHED" in result.stdout, (
        "the wrapper aborted inside the escalation window, so finalizers "
        f"never ran; rc={result.returncode} stderr={result.stderr}"
    )
    assert result.returncode == 0, result.stderr
    # The escalation still happened: __rc came from the second wait.
    assert "signaled=1" in result.stdout and "rc=137" in result.stdout, result.stdout


@pytest.mark.integration
@pytest.mark.parametrize(
    ("kill0_rc", "killkill_rc", "label"),
    [(1, 0, "child already gone"), (0, 0, "child still alive")],
)
def test_escalation_survives_the_two_non_race_outcomes(
    tmp_path: Path, kill0_rc: int, killkill_rc: int, label: str
):
    """The other two outcomes must keep working. These pass against the
    pre-fix code too, and are here so the fix is pinned on all three paths
    rather than only the one that was broken.
    """
    script = tmp_path / "no-race.sh"
    script.write_text(
        "set -e\n"
        "__TERM_GRACE_TICKS=2\n"
        "__child=424242\n"
        "__rc=143\n"
        # A signal really did reach the wrapper in each of these: rc=143 is
        # what `wait` reports when the TERM trap interrupts it.
        "__signal_received=1\n"
        "kill() {\n"
        '    case "$1" in\n'
        f"        -0) return {kill0_rc} ;;\n"
        f"        -KILL) return {killkill_rc} ;;\n"
        "    esac\n"
        "    return 0\n"
        "}\n"
        "wait() { return 137; }\n"
        f"{_escalation_block()}\n"
        'echo "REACHED signaled=${__signaled} rc=${__rc}"\n'
    )
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=30
    )
    assert "REACHED" in result.stdout, f"{label}: {result.stderr}"
    assert result.returncode == 0, result.stderr


# --- An exit status above 128 is not the same thing as a signal ---------


@pytest.mark.integration
@pytest.mark.parametrize(
    ("rc", "signal_received", "want_signaled", "want_rc", "label"),
    [
        pytest.param(
            200, 0, 0, 200, "an ordinary exit with a status above 128", id="exit-200"
        ),
        pytest.param(143, 1, 1, 137, "a real SIGTERM teardown", id="signalled"),
        pytest.param(
            137,
            0,
            0,
            137,
            "a child killed by something outside this wrapper",
            id="external-kill",
        ),
    ],
)
def test_only_a_signal_this_wrapper_received_takes_the_signal_path(
    tmp_path: Path,
    rc: int,
    signal_received: int,
    want_signaled: int,
    want_rc: int,
    label: str,
):
    """`wait` returning above 128 does not mean the agent was signalled.

    128+signum is how `wait` reports a signalled child, but a process may also
    just exit with a status in that range. `exit 200` is an ordinary exit, and
    the classification tested `-gt 128` alone, so it took the signal path:
    the tight signal-path finalize budget (measured against `docker stop -t 5`)
    plus a kill escalation, on a run with no stop deadline anywhere in it. The
    budgets are asymmetric by measurement, so that is not a mislabel, it is a
    truncated sweep and transcripts that never reach the store.

    The evidence used instead is direct: the traps record that a signal
    actually reached this wrapper, which is the only way `docker stop` or a
    Ctrl-C can. The third case pins the other direction -- a child killed by
    something that never signalled PID 1 has no stop grace running and is
    already dead, so it belongs on the clean path too.

    Runs the SHIPPED block under `set -e`, the discipline entrypoint.sh runs
    it under, with `wait` stubbed to the status the second wait would report.
    """
    script = tmp_path / f"classify-{rc}-{signal_received}.sh"
    script.write_text(
        "set -e\n"
        "__TERM_GRACE_TICKS=2\n"
        "__child=424242\n"
        f"__rc={rc}\n"
        f"__signal_received={signal_received}\n"
        # Child already gone in every case: the escalation must be skipped
        # entirely on the clean path, not merely be a no-op.
        "kill() { return 1; }\n"
        # What the second wait would report. Reaching it at all on a clean
        # exit is the defect: it replaces the agent's real status.
        "wait() { return 137; }\n"
        f"{_escalation_block()}\n"
        'echo "REACHED signaled=${__signaled} rc=${__rc}"\n'
    )
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=30
    )
    assert "REACHED" in result.stdout, f"{label}: {result.stderr}"
    assert result.returncode == 0, result.stderr
    assert f"signaled={want_signaled}" in result.stdout, (
        f"{label} was classified wrongly, so the wrong finalize budget applies: "
        f"{result.stdout}"
    )
    assert f"rc={want_rc}" in result.stdout, (
        f"{label}: the agent's exit code must survive the classification: "
        f"{result.stdout}"
    )


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_an_exit_above_128_gets_the_clean_finalize_budget(tmp_path: Path):
    """The consequence, end to end: an agent exiting 200 must get a sweep.

    The classification is only interesting because of what it selects. A stub
    exporter that takes 5s completes inside the clean budget (120s) and is cut
    off by the signal budget (2s), so the report an operator reads says which
    path the run took -- and the agent's exit code must still come out
    unchanged either way.
    """
    spool = _host_spool(tmp_path)
    slow_exporter = tmp_path / "slow-exporter"
    slow_exporter.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "${1:-}" = "--version" ]; then echo "stub 0.0.0-slow"; exit 0; fi\n'
        "sleep 5\n"
        'echo "run: discovered=0 skipped_unchanged=0 uploaded=0 accepted=0 '
        'duplicate=0 rejected=0 skipped_oversize=0 failed=0"\n'
        "exit 0\n"
    )
    os.chmod(slow_exporter, 0o755)

    result = _run(
        ["bash", "-c", "exit 200"],
        env={
            "AGENTIC_CAPABILITIES": SessionStoreContract.CAPABILITY,
            SessionStoreEnv.PROVIDER: "seshmagic",
            SessionStoreEnv.URL: STORE_URL,
            SessionStoreEnv.SPOOL: "/spool",
            SessionStoreEnv.PARTITION: "exit-above-128",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{slow_exporter}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 200, "the agent's exit code must survive finalize"
    assert "upload complete" in result.stderr, (
        "an ordinary exit above 128 was given the signal-path budget, so the "
        f"sweep was cut short: {result.stderr}"
    )
    assert "TIMED OUT" not in result.stderr, result.stderr


# --- The same `set -e` class in the trap bodies and the grace loop -------

_TRAP_LINE = re.compile(r"^trap '.*\$\{__child\}.*' (?P<sig>TERM|INT)$", re.MULTILINE)


def _trap_lines() -> dict[str, str]:
    lines = {
        m.group("sig"): m.group(0)
        for m in _TRAP_LINE.finditer(_ENTRYPOINT_SH.read_text())
    }
    assert set(lines) == {"TERM", "INT"}, f"trap lines not found in {_ENTRYPOINT_SH}"
    return lines


@pytest.mark.integration
@pytest.mark.parametrize("signal", ["TERM", "INT"])
def test_signal_trap_survives_a_child_that_already_exited(tmp_path: Path, signal: str):
    """A trap body whose `kill` fails must not exit the wrapper from inside it.

    `set -e` is in force INSIDE a trap. If the child exits in the instant
    before the forwarded signal lands, `kill` returns ESRCH and the shell
    exits at PID 1 from within the handler, skipping every finalizer -- the
    same failure mode the escalation block was fixed for, in the two sibling
    sites the fix did not touch.

    The `2>/dev/null` on those lines hides the diagnostic only; it does not
    change the exit status, which is why it never protected anything.

    Runs the SHIPPED trap line, lifted verbatim, against a pid that is
    guaranteed not to exist.
    """
    script = tmp_path / f"trap-{signal}.sh"
    script.write_text(
        "set -e\n"
        # A pid that cannot be ours, so the kill inside the trap fails ESRCH.
        "__child=999999\n"
        f"{_trap_lines()[signal]}\n"
        f"kill -{signal} $$\n"
        "sleep 0.05\n"
        "echo TRAP_SURVIVED\n"
    )
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=30
    )
    assert "TRAP_SURVIVED" in result.stdout, (
        f"the {signal} trap aborted the wrapper, so no finalizer would run; "
        f"rc={result.returncode} stderr={result.stderr}"
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.integration
def test_grace_loop_survives_an_interrupted_sleep(tmp_path: Path):
    """An interrupted `sleep` in the TERM-grace loop must not abort the wrapper.

    Under `docker run -it` the container shares a process group with the tty,
    so a Ctrl-C reaches `sleep` as well as PID 1. An interrupted `sleep`
    returns non-zero, and as the loop body's last command that is fatal under
    `set -e` -- on the exact path where the agent is already being torn down
    and finalizers still have to run.
    """
    script = tmp_path / "interrupted-sleep.sh"
    script.write_text(
        "set -e\n"
        "__TERM_GRACE_TICKS=2\n"
        "__child=424242\n"
        "__rc=143\n"
        # A signal really did reach the wrapper in each of these: rc=143 is
        # what `wait` reports when the TERM trap interrupts it.
        "__signal_received=1\n"
        # Alive throughout, so the loop actually runs its body.
        "kill() { return 0; }\n"
        # What an interrupted sleep reports.
        "sleep() { return 130; }\n"
        "wait() { return 137; }\n"
        f"{_escalation_block()}\n"
        'echo "REACHED signaled=${__signaled} rc=${__rc}"\n'
    )
    result = subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=30
    )
    assert "REACHED" in result.stdout, (
        "an interrupted sleep aborted the wrapper before finalizers ran; "
        f"rc={result.returncode} stderr={result.stderr}"
    )
    assert result.returncode == 0, result.stderr


# --- The store write credential is withheld from the agent (ADR-040 s2) ---

_STUB_EXPORTER_REPORTS_TOKEN = (
    Path(__file__).parent / "fixtures" / "stub-exporter-reports-token"
)


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_store_credential_is_withheld_from_the_agent_but_reaches_finalize(
    tmp_path: Path,
):
    """The agent must not inherit the store write credential; finalize must.

    init.sh is SOURCED, so before AGENTIC_CAPABILITY_WITHHOLD existed both the
    orchestrator's AGENTIC_SESSION_STORE_AUTH and the derived
    SESSIONS_WRITE_TOKEN were exported into the environment of every command
    the agent ran. The agent has no use for either. Only the exporter does,
    and the exporter runs in finalize.sh after the agent has exited.

    Both halves are asserted, because either one alone is trivially
    satisfiable: withholding is easy if you also break the upload, and the
    upload is easy if you leak the credential. The CMD dumps its whole
    environment, so the secret is checked by value and not only by variable
    name, and it dumps a grandchild's environment too, since inheritance is
    the channel every subprocess, tool and MCP server picks up automatically.

    NOT covered here, deliberately: `docker run -e` also puts the value in
    /proc/1/environ, which the agent can read as the same uid. That residue
    belongs to the host-side half of the capability (ADR-040 s1 and s2) and no
    amount of unsetting inside the container closes it.
    """
    secret = "withhold-me-1a2b3c4d"  # a test fixture, not a real credential
    spool = _host_spool(tmp_path)
    agent = (
        'echo "AGENT_AUTH=${AGENTIC_SESSION_STORE_AUTH:-<unset>}"; '
        'echo "AGENT_TOKEN=${SESSIONS_WRITE_TOKEN:-<unset>}"; '
        'echo "AGENT_ENV_BEGIN"; env; echo "AGENT_ENV_END"; '
        'bash -c \'echo "CHILD_ENV_BEGIN"; env; echo "CHILD_ENV_END"\''
    )
    result = _run(
        ["bash", "-c", agent],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_AUTH": secret,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "withhold-credential",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER_REPORTS_TOKEN}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"

    assert "AGENT_AUTH=<unset>" in result.stdout, (
        "the agent inherited the orchestrator's copy of the store credential"
    )
    assert "AGENT_TOKEN=<unset>" in result.stdout, (
        "the agent inherited the exporter's copy of the store credential"
    )
    assert secret not in result.stdout, (
        "the credential's VALUE is somewhere in the agent's environment, under "
        "some name; the dumped env is what catches that"
    )

    # Finalize still uploads: the stub reports that the credential was in its
    # environment, and the sweep completed.
    assert (
        spool / _TOKEN_REPORT
    ).read_text().strip() == "STUB_EXPORTER_TOKEN=present", (
        "withholding broke the upload: the exporter ran without the credential"
    )
    assert "[finalize] session-store upload complete" in result.stderr, result.stderr


_PROBE_CAPABILITY = Path(__file__).parent / "fixtures" / "probe-capability"

# Where stub-exporter-reports-token records whether the credential reached it.
# A file, because finalize.sh captures the exporter's streams and never
# replays them; see that fixture's header.
_TOKEN_REPORT = ".stub-exporter-token-report"


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_withheld_values_reach_only_the_declaring_capabilitys_finalizer(
    tmp_path: Path,
):
    """A capability's finalizer must not receive another capability's secret.

    AGENTIC_CAPABILITY_WITHHOLD is one flat list, and the restore used to
    replay ALL of it before EVERY finalizer, so an unrelated capability's
    finalize hook ran with the session store's write credential in its
    environment. The subshell around the restore does not address this: it
    bounds how LONG a restored value lives, not WHO sees it.

    A second capability is mounted in for this, rather than reusing memory
    (whose adapter has no finalize.sh at all). It is a fixture, not a
    product capability, which is also the point: the entrypoint learns
    nothing about either name, exactly as ADR-040 s4 requires.
    """
    secret = "scope-me-9f8e7d6c"  # a test fixture, not a real credential
    spool = _host_spool(tmp_path)
    result = _run(
        ["bash", "-c", "echo AGENT_RAN"],
        env={
            "AGENTIC_CAPABILITIES": "session-store probe",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_AUTH": secret,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "withhold-scope",
            "AGENTIC_PROBE_PROVIDER": "probe",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_PROBE_CAPABILITY}:/opt/agentic/capabilities/probe:ro",
            f"{_STUB_EXPORTER_REPORTS_TOKEN}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "AGENT_RAN" in result.stdout

    # The probe's own declaration still comes back to its own finalizer, so
    # the scoping is not simply "restore nothing".
    assert "PROBE_FINALIZE PROBE_SECRET=probe-owns-this" in result.stderr, result.stderr
    # And the session store's credential does not, under either name.
    assert "PROBE_FINALIZE SESSIONS_WRITE_TOKEN=<unset>" in result.stderr, result.stderr
    assert "PROBE_FINALIZE AGENTIC_SESSION_STORE_AUTH=<unset>" in result.stderr, (
        result.stderr
    )
    assert secret not in result.stderr, (
        "the credential's value reached another finalizer"
    )
    # The declaring capability's own finalizer is unaffected: it still gets
    # the credential and still completes the upload.
    assert (
        spool / _TOKEN_REPORT
    ).read_text().strip() == "STUB_EXPORTER_TOKEN=present", (
        "the declaring capability's own finalizer lost its credential"
    )
    assert "[finalize] session-store upload complete" in result.stderr, result.stderr
    # And the agent never saw either.
    assert "probe-owns-this" not in result.stdout, result.stdout


@pytest.mark.integration
def test_withhold_ignores_a_name_that_is_not_a_shell_identifier():
    """A declared name is eval'd on both sides of the stash, so an invalid one
    is skipped with a warning rather than expanded.

    Same posture as the capability-name and provider-name validation in 5.6:
    reject before the name becomes part of an expansion, and do not echo the
    rejected value.
    """
    result = _run(
        [
            "bash",
            "-c",
            'echo "AGENT_SAW=${SAFE_ONE:-<unset>}"',
        ],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_CAPABILITY_WITHHOLD": "a-b;touch /tmp/PWNED SAFE_ONE",
            "SAFE_ONE": "kept-out-of-the-agent",
        },
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "AGENT_SAW=<unset>" in result.stdout, (
        "a validly named variable must still be withheld"
    )
    assert "kept-out-of-the-agent" not in result.stdout, result.stdout
    assert "invalid name in AGENTIC_CAPABILITY_WITHHOLD" in result.stderr


# The ownership marker init.sh writes into the reserved namespace. Restated
# here (not an env var, so it has no Env member) to build a namespace the
# adapter accepts as its own; see __META_MARKER_ID in the seshmagic init.sh.
_METADATA_OWNER_MARKER = "agentic-session-store-metadata-v1\n"


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_capture_env_write_failure_is_never_silent(tmp_path: Path):
    """A failed .capture-env write must fail the adapter, not pass quietly.

    init.sh carries `set -e`, but entrypoint.sh 5.6 sources it as the
    condition of an `if`, and bash disables errexit for a command evaluated
    as a condition. So every unchecked command in that file ran with no
    stop-on-failure at all, and a later successful command made the source
    return zero: the lifecycle recorded a successful init.

    For this write that is the expensive failure. The session still uploads,
    with the wrong tags or none, and nothing reports it, so the corpus gains
    rows nobody can tell are misattributed.

    The namespace is pre-built here with a VALID ownership marker, so the
    adapter's claim step succeeds and the only thing that fails is the write
    itself: the partition metadata directory is not writable by the agent.
    """
    spool = _host_spool(tmp_path)
    reserved = spool / _RESERVED
    reserved.mkdir()
    (reserved / ".owner").write_text(_METADATA_OWNER_MARKER)
    meta_dir = reserved / "w1" / "p2"
    meta_dir.mkdir(parents=True)
    os.chmod(reserved, 0o777)
    os.chmod(reserved / "w1", 0o777)
    # Readable and traversable, NOT writable: `mkdir -p` on it still succeeds,
    # so the adapter gets all the way to the write before anything fails.
    os.chmod(meta_dir, 0o555)

    result = _run(
        ["bash", "-c", "echo AGENT_RAN"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            SessionStoreEnv.PROVIDER: "seshmagic",
            SessionStoreEnv.URL: STORE_URL,
            SessionStoreEnv.TAGS: "workflow:w1,phase:p2",
            SessionStoreEnv.SPOOL: "/spool",
            SessionStoreEnv.PARTITION: "w1/p2",
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert not (meta_dir / ".capture-env").exists(), (
        "the fixture did not actually block the write"
    )
    # The adapter names the file and says what the consequence would be.
    assert "could not write" in result.stderr, result.stderr
    assert ".capture-env" in result.stderr, result.stderr
    # And the failure reaches the lifecycle rather than stopping at a message:
    # 5.6 reports the non-zero source, and because init returned before the
    # symlink work, 5.7's symlinks_correct fails and the agent never runs.
    assert "adapter init failed" in result.stderr, result.stderr
    assert result.returncode != 0, "the workspace started with wrong tags anyway"
    assert "AGENT_RAN" not in result.stdout, result.stdout


@pytest.mark.integration
def test_memory_config_write_failure_is_never_silent(tmp_path: Path):
    """The same inert-errexit defect in the sibling capability's adapter.

    memory/hindsight/init.sh is sourced through the same generic line, so its
    `set -e` is inert too. An unwritable ~/.hindsight meant the requested
    config (extra recall banks, for instance) was silently dropped and the run
    proceeded looking healthy.

    Only stderr is asserted: whether the container exits non-zero depends on
    the memory doctor and on backend reachability, and the property under test
    is that the failure is reported at all.
    """
    config_dir = tmp_path / "hindsight-config"
    config_dir.mkdir()
    os.chmod(config_dir, 0o555)

    result = _run(
        ["bash", "-c", "echo AGENT_RAN"],
        env={
            "AGENTIC_CAPABILITIES": "memory",
            MemoryEnv.PROVIDER: "hindsight",
            MemoryEnv.URL: HINDSIGHT_BACKEND_URL,
            MemoryEnv.NAMESPACE: "capability-init-audit",
            MemoryEnv.CONFIG_JSON: '{"recallAdditionalBanks": ["shared"]}',
        },
        extra_mounts=[f"{config_dir}:/home/agent/.hindsight:ro"],
    )
    assert "could not write" in result.stderr, result.stderr
    assert "claude-code.json" in result.stderr, result.stderr
    assert "adapter init failed" in result.stderr, result.stderr
    assert not (config_dir / "claude-code.json").exists()


def _stage_metadata_namespace_sh(link_at: str) -> str:
    """Shell that plants a symlinked component inside the reserved namespace.

    Built IN the container, as the agent user, for the reason given on
    _stage_partition_sh: a host-written fixture carries the host's uid, which
    differs on CI and is remapped by Docker Desktop, so the agent user would
    hit permission errors production never sees and the test would pass for
    the wrong reason.

    The namespace is marked with a VALID owner id, so the claim step succeeds
    and the only thing left to refuse is the path below the root, which is
    exactly the property under test. `link_at` is the component that becomes a
    symlink to /victim, relative to the namespace root.
    """
    parent = link_at.rsplit("/", 1)[0] if "/" in link_at else ""
    marker_b64 = base64.b64encode(_METADATA_OWNER_MARKER.encode()).decode()
    lines = [
        f"mkdir -p /spool/{_RESERVED}" + (f"/{parent}" if parent else ""),
        f"printf %s '{marker_b64}' | base64 -d > /spool/{_RESERVED}/.owner",
        f"ln -s /victim /spool/{_RESERVED}/{link_at}",
        'printf %s "operator\'s own data" > /victim/precious.txt',
    ]
    return "\n".join(lines)


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
@pytest.mark.parametrize(
    ("link_at", "label"),
    [
        pytest.param("w1", "an intermediate partition component", id="intermediate"),
        pytest.param("w1/p2", "the metadata directory itself", id="meta-dir"),
    ],
)
def test_init_refuses_a_symlinked_component_of_the_metadata_path(
    tmp_path: Path, link_at: str, label: str
):
    """The ownership marker proves the namespace ROOT, not the path written to.

    Metadata lands in ${SPOOL}/.agentic-session-store/${PARTITION}, and
    PARTITION is multi-component, so between the marked root and the file
    there are directories the marker says nothing about. `mkdir -p` walks a
    symlinked component without a word, so both writes (.capture-env, and the
    state file the exporter is handed) went straight through the link into a
    directory outside the namespace: truncating an operator file there, with
    the adapter reporting a successful init.

    Both positions are exercised, because a guard written for the last
    component only would leave the intermediate ones open, and vice versa.
    """
    spool = _host_spool(tmp_path)
    victim = tmp_path / "victim"
    victim.mkdir()
    os.chmod(victim, 0o777)
    mounts = [
        f"{spool}:/spool",
        f"{victim}:/victim",
        f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
    ]

    # Fixture run: no capability env, so no adapter runs and the container is
    # only being used for its uid.
    staged = _run(
        ["bash", "-c", _stage_metadata_namespace_sh(link_at)], extra_mounts=mounts
    )
    assert staged.returncode == 0, f"fixture staging failed: {staged.stderr}"

    result = _run(
        ["bash", "-c", "echo AGENT_RAN"],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            SessionStoreEnv.PROVIDER: "seshmagic",
            SessionStoreEnv.URL: STORE_URL,
            SessionStoreEnv.TAGS: "workflow:w1,phase:p2",
            SessionStoreEnv.SPOOL: "/spool",
            SessionStoreEnv.PARTITION: "w1/p2",
        },
        extra_mounts=mounts,
        add_host_gateway=True,
    )

    assert result.returncode != 0, f"{label}: the workspace started anyway"
    assert "AGENT_RAN" not in result.stdout, f"{label}: the agent ran anyway"
    assert "is a symlink" in result.stderr, result.stderr
    assert f"/spool/{_RESERVED}/{link_at}" in result.stderr, result.stderr

    # Nothing was written THROUGH the link, and nothing of the operator's was
    # touched or removed on the way to refusing.
    assert sorted(p.name for p in victim.iterdir()) == ["precious.txt"], (
        f"{label}: the adapter wrote through the symlink into {victim}"
    )
    assert (victim / "precious.txt").read_text() == "operator's own data"
    # The link itself is left exactly as it was found.
    link = spool / _RESERVED / link_at
    assert os.path.islink(link), f"{label}: the adapter replaced the symlink"
    assert os.readlink(link) == "/victim"


# The container-local spool the marker test below builds its fixture in, and
# the path outside the reserved namespace that the planted link points at.
_LOCAL_SPOOL = "/tmp/spool"
_MARKER_LINK_TARGET = "/tmp/victim-outside-the-namespace"


@pytest.mark.integration
def test_init_refuses_a_symlink_planted_at_the_ownership_marker():
    """The marker write must not follow a link that appears at its own name.

    The claim step decides the namespace is unowned by checking that no
    marker is there and that the directory is empty, and then wrote the
    marker with a plain truncating `>`. Both of those are checks, and a
    check has a window after it: a symlink sitting at `.owner` when the
    redirect opens is FOLLOWED, and whatever it names is created or
    truncated, outside the namespace the marker exists to bound. That is the
    unnamespaced-write defect, committed by the code written to prevent it.

    THE FIXTURE STANDS IN FOR THE RACE, deliberately, because a race cannot
    be driven deterministically from a test. It reproduces the state the race
    produces, which is what the write actually sees: the checks report an
    empty namespace with no marker while the name is in fact taken by a
    symlink. `ls -A` prints nothing for a directory it cannot read and its
    error goes to /dev/null, so a namespace root that is writable and
    searchable but not readable puts the claim step in exactly that state
    with no timing involved. `[ -e ]` on a dangling link is false for the
    same reason it is false during the race window: the name resolves to
    nothing that can be stat'ed.

    The fixture lives on the CONTAINER's own filesystem rather than on a
    bind-mounted spool, and the adapter is sourced here rather than reached
    through the entrypoint, because both of those are forced by the same
    measurement: a Docker Desktop bind mount reports the mode back faithfully
    (`stat -c %a` says 333) and then serves `ls -A` to the mounting user
    anyway, so the unreadable-directory state cannot be staged on one. A
    fixture that must exist BEFORE the adapter runs and cannot live on a
    mount cannot be staged by a first container either, so the test stages it
    and sources the adapter in one, exactly as entrypoint.sh 5.6 does: as the
    condition of an `if`, which is what makes the file's `set -e` inert and
    the explicit status check the only thing that reports the refusal.
    """
    init = "/opt/agentic/capabilities/session-store/seshmagic/init.sh"
    script = f"""
set -u
mkdir -p {_LOCAL_SPOOL}/{_RESERVED}
ln -s {_MARKER_LINK_TARGET} {_LOCAL_SPOOL}/{_RESERVED}/.owner
# Writable and searchable, NOT readable: `ls -A` fails and prints nothing,
# so the claim step reads the namespace as empty while `.owner` is taken.
chmod 0333 {_LOCAL_SPOOL}/{_RESERVED}
export {SessionStoreEnv.SPOOL}={_LOCAL_SPOOL}
export {SessionStoreEnv.PARTITION}=w1/p2
export {SessionStoreEnv.URL}=http://unused.invalid
export {SessionStoreEnv.TAGS}=workflow:w1,phase:p2
if . {init}; then echo INIT=ok; else echo INIT=refused; fi
if [ -e {_MARKER_LINK_TARGET} ]; then echo VICTIM=written; else echo VICTIM=absent; fi
printf 'LINK=%s\\n' "$(readlink {_LOCAL_SPOOL}/{_RESERVED}/.owner 2>/dev/null || echo gone)"
"""

    result = _run(["bash", "-c", script])

    assert "VICTIM=absent" in result.stdout, (
        f"the marker write followed the planted link and wrote to "
        f"{_MARKER_LINK_TARGET}: stdout={result.stdout!r}"
    )
    assert "INIT=refused" in result.stdout, (
        f"the adapter reported a successful init: stdout={result.stdout!r}"
    )
    # Loud, and naming the path, so an operator can find what is in the way.
    assert "could not create the ownership marker" in result.stderr, result.stderr
    assert f"{_LOCAL_SPOOL}/{_RESERVED}/.owner" in result.stderr, result.stderr
    # Refusing deletes nothing, the planted link included.
    assert f"LINK={_MARKER_LINK_TARGET}" in result.stdout, result.stdout


# --- An init that failed must never be reported as a healthy workspace -------
#
# entrypoint.sh 5.6 sources each adapter's init.sh as the condition of an `if`
# and, on failure, warns and carries on because "doctor in 5.7 will surface
# the cause". That is an assumption about COVERAGE -- that every check a
# doctor runs is a superset of everything its init can fail at -- and it was
# never verified. It is false for memory: with a read-only ~/.hindsight the
# adapter's config write fails and it returns 1, while the memory doctor
# validates the REQUESTED json, the backend, and the config file ALREADY on
# disk, all of which a stale but well-formed file satisfies.
#
# Each init.sh now records a completion marker as its LAST act, and each
# doctor asserts it. The marker holds a token the init mints fresh per run,
# because the spool and (optionally) $HOME outlive the container: a marker
# that only had to exist would be satisfied by the previous run's file, which
# is the same stale state one layer up.

_SS_INIT_MARKER = SessionStoreContract.init_marker_path("/spool", "w1/p2")
_SS_META_DIR = _SS_INIT_MARKER.rsplit("/", 1)[0]
_MEM_INIT_MARKER = MemoryContract.init_marker_path("/home/agent")
_MEM_MARKER_NAME = MemoryContract.INIT_MARKER_BASENAME


def _audit_dir(tmp_path: Path) -> Path:
    """Host directory the entrypoint's 5.7 doctor appends its JSON into.

    A failing preflight never reaches CMD, so the doctor's stdout cannot be
    read off the container's stdout the way the on-demand tests read it. The
    audit file is where the entrypoint puts it, and mounting it is the only
    way to assert on the payload of the run that actually hard-failed.
    """
    audit = tmp_path / "audit"
    audit.mkdir()
    os.chmod(audit, 0o777)
    return audit


def _doctor_record(audit: Path, capability: str) -> dict:
    """The last audit record that capability's doctor wrote."""
    lines = [
        line
        for path in sorted(audit.glob("*.jsonl"))
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    assert lines, f"the 5.7 doctor wrote no audit record into {audit}"
    records = [json.loads(line) for line in lines]
    mine = [r for r in records if r.get("capability") == capability]
    assert mine, (
        f"no {capability} record among {[r.get('capability') for r in records]}"
    )
    return mine[-1]


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
@pytest.mark.parametrize(
    ("keep_marker", "expected_detail"),
    [
        pytest.param(True, "DIFFERENT run's token", id="stale-marker-kept"),
        pytest.param(False, "absent or unreadable", id="marker-removed"),
    ],
)
def test_session_store_failed_init_fails_the_doctor_even_with_a_stale_marker(
    tmp_path: Path, keep_marker: bool, expected_detail: str
):
    """A failed init must fail the doctor, and last run's marker must not save it.

    Three containers against ONE spool and ONE persisted home, which is the
    configuration that makes this hazard real:

      1. a healthy run, which writes the marker for its own token;
      2. a staging run with the capability disabled, which makes the metadata
         directory read-only as the agent user (and, in the second case,
         removes the marker first);
      3. the run under test, whose `.capture-env` write therefore fails, so
         its init returns 1 before it can record anything.

    In run 3 every other check passes: the partition is writable, the
    symlinks from run 1 survive in the persisted home, the exporter is
    mounted and the store is live. So init_complete is the only thing between
    a failed init and a workspace that reports itself healthy while serving a
    previous run's correlation tags.
    """
    spool = _host_spool(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    _open_perms(home)
    audit = _audit_dir(tmp_path)

    capability_env = {
        "AGENTIC_CAPABILITIES": "session-store",
        SessionStoreEnv.PROVIDER: "seshmagic",
        SessionStoreEnv.URL: STORE_URL,
        SessionStoreEnv.TAGS: "workflow:w1,phase:p2",
        SessionStoreEnv.SPOOL: "/spool",
        SessionStoreEnv.PARTITION: "w1/p2",
    }
    mounts = [
        f"{spool}:/spool",
        f"{home}:/home/agent",
        f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
    ]

    healthy = _run(
        ["bash", "-c", f"cat {_SS_INIT_MARKER}"],
        env=capability_env,
        extra_mounts=mounts,
        add_host_gateway=True,
        tmpfs_home=False,
    )
    assert healthy.returncode == 0, f"the healthy run failed: {healthy.stderr}"
    first_token = healthy.stdout.strip()
    assert first_token, (
        "a successful init recorded no completion marker:\n"
        f"stdout={healthy.stdout!r} stderr={healthy.stderr!r}"
    )

    # Staged in the container, as the agent user that owns these paths: see
    # _stage_partition_sh for why a host-written fixture would not do.
    if not keep_marker:
        staging = _run(
            ["bash", "-c", f"rm -f {_SS_INIT_MARKER}"],
            extra_mounts=mounts,
            tmpfs_home=False,
        )
        assert staging.returncode == 0, f"staging failed: {staging.stderr}"

    # The metadata directory is made unwritable by REMOUNTING it read-only
    # rather than by chmod: Docker Desktop's bind-mount layer reports a mode
    # back faithfully and then serves the write anyway, so a chmod fixture
    # passes for the wrong reason on a developer's Mac (measured: the whole
    # run stayed green). A read-only mount is enforced by the kernel on both
    # platforms.
    result = _run(
        ["bash", "-c", "echo AGENT_RAN"],
        env={**capability_env, "AGENTIC_CAPABILITY_AUDIT_DIR": "/audit"},
        extra_mounts=[
            *mounts,
            f"{audit}:/audit",
            f"{spool}/{_RESERVED}/w1/p2:{_SS_META_DIR}:ro",
        ],
        add_host_gateway=True,
        tmpfs_home=False,
    )
    assert result.returncode != 0, (
        f"a failed init started the workspace anyway: {result.stdout} {result.stderr}"
    )
    assert "AGENT_RAN" not in result.stdout, "the agent ran on a failed init"

    record = _doctor_record(audit, "session-store")
    checks = {c["name"]: c for c in record["checks"]}
    assert checks["init_complete"]["passed"] is False, checks["init_complete"]
    assert expected_detail in checks["init_complete"]["detail"]
    assert _SS_INIT_MARKER in checks["init_complete"]["detail"]
    # The point of the check: nothing else noticed. Without init_complete this
    # doctor passes and the workspace runs with run 1's tags.
    other = {n: c for n, c in checks.items() if n != "init_complete"}
    assert all(c["passed"] for c in other.values()), (
        "this fixture is meant to fail init_complete ALONE; another check "
        f"failed too, so it no longer proves the gap: {other}"
    )


@pytest.mark.integration
@pytest.mark.skipif(not _hindsight_reachable(), reason="hindsight backend unreachable")
@pytest.mark.parametrize(
    ("keep_marker", "expected_message"),
    [
        pytest.param(True, "DIFFERENT run's token", id="stale-marker-kept"),
        pytest.param(False, "absent or unreadable", id="marker-removed"),
    ],
)
def test_memory_failed_init_fails_the_doctor_even_with_a_stale_marker(
    tmp_path: Path, keep_marker: bool, expected_message: str
):
    """The motivating scenario, reproduced directly: a read-only ~/.hindsight.

    Run 1 asks for one config and gets it. The staging run makes ~/.hindsight
    read-only. Run 3 asks for a DIFFERENT config, its write fails, and its
    init returns 1 -- with run 1's config still on disk, well-formed, with
    dynamicBankId already false, so config_json_valid, backend_dns,
    backend_health and the hindsight doctor.sh are all green. Only
    init_complete separates that from a healthy workspace, and a marker left
    by run 1 on the persisted $HOME must not satisfy it either.
    """
    home = tmp_path / "home"
    home.mkdir()
    _open_perms(home)
    audit = _audit_dir(tmp_path)
    hindsight_dir = "/home/agent/.hindsight"
    config_path = f"{hindsight_dir}/claude-code.json"

    def memory_env(banks: str) -> dict:
        return {
            "AGENTIC_CAPABILITIES": "memory",
            MemoryEnv.PROVIDER: "hindsight",
            MemoryEnv.URL: "http://host.docker.internal:9077",
            MemoryEnv.NAMESPACE: "init-marker-test",
            MemoryEnv.CONFIG_JSON: '{"dynamicBankId": false, '
            f'"recallAdditionalBanks": ["{banks}"]}}',
        }

    healthy = _run(
        ["bash", "-c", f"cat {_MEM_INIT_MARKER}"],
        env=memory_env("from-run-one"),
        extra_mounts=[f"{home}:/home/agent"],
        add_host_gateway=True,
        tmpfs_home=False,
    )
    assert healthy.returncode == 0, f"the healthy run failed: {healthy.stderr}"
    first_token = healthy.stdout.strip()
    assert first_token, (
        "a successful init recorded no completion marker:\n"
        f"stdout={healthy.stdout!r} stderr={healthy.stderr!r}"
    )

    if not keep_marker:
        staging = _run(
            ["bash", "-c", f"rm -f {_MEM_INIT_MARKER}"],
            extra_mounts=[f"{home}:/home/agent"],
            tmpfs_home=False,
        )
        assert staging.returncode == 0, f"staging failed: {staging.stderr}"

    # ~/.hindsight is made read-only by REMOUNTING it, not by chmod: Docker
    # Desktop's bind-mount layer serves the write anyway when only the mode
    # says otherwise (measured: the run stayed green), so a chmod fixture
    # would prove nothing on a developer's Mac. $HOME itself stays writable,
    # which is the point -- the marker is not written because init returns
    # before reaching it, not because it could not be written.
    result = _run(
        ["bash", "-c", "echo AGENT_RAN"],
        env={
            **memory_env("from-run-three"),
            "AGENTIC_CAPABILITY_AUDIT_DIR": "/audit",
        },
        extra_mounts=[
            f"{home}:/home/agent",
            f"{home}/.hindsight:{hindsight_dir}:ro",
            f"{audit}:/audit",
        ],
        add_host_gateway=True,
        tmpfs_home=False,
    )
    assert result.returncode != 0, (
        f"a failed init started the workspace anyway: {result.stdout} {result.stderr}"
    )
    assert "AGENT_RAN" not in result.stdout, "the agent ran on a failed init"

    record = _doctor_record(audit, "memory")
    checks = {c["name"]: c for c in record["checks"]}
    assert checks["init_complete"]["status"] == "fail", checks["init_complete"]
    assert expected_message in checks["init_complete"]["message"]
    assert _MEM_INIT_MARKER in checks["init_complete"]["message"]
    other = {n: c for n, c in checks.items() if n != "init_complete"}
    assert all(c["status"] != "fail" for c in other.values()), (
        "this fixture is meant to fail init_complete ALONE; another check "
        f"failed too, so it no longer proves the gap: {other}"
    )

    # And the configuration the agent would have run against is the one run 1
    # asked for, which is what makes the silent pass expensive.
    stale = _run(
        ["bash", "-c", f"cat {config_path}"],
        extra_mounts=[f"{home}:/home/agent"],
        tmpfs_home=False,
    )
    assert "from-run-one" in stale.stdout, stale.stdout
    assert "from-run-three" not in stale.stdout, stale.stdout


@pytest.mark.integration
@pytest.mark.parametrize(
    "provider",
    [pytest.param(None, id="provider-unset"), pytest.param("none", id="provider-none")],
)
def test_a_disabled_capability_writes_no_init_marker(tmp_path: Path, provider):
    """Opting out stays a complete no-op: no doctor, no marker, no writes.

    entrypoint.sh 5.6 skips a capability whose provider is unset or "none",
    and both doctors print nothing and exit 0 with no contract. The
    completion marker must not change any of that: a disabled capability
    writes nothing, into the spool or into $HOME.
    """
    spool = _host_spool(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    _open_perms(home)

    env = {"AGENTIC_CAPABILITIES": "memory session-store"}
    if provider is not None:
        env[SessionStoreEnv.PROVIDER] = provider
        env[MemoryEnv.PROVIDER] = provider

    result = _run(
        ["bash", "-c", "echo AGENT_RAN; ls -A /spool; ls -A /home/agent"],
        env=env,
        extra_mounts=[f"{spool}:/spool", f"{home}:/home/agent"],
        tmpfs_home=False,
    )
    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "AGENT_RAN" in result.stdout
    assert _RESERVED not in result.stdout, result.stdout
    assert _MEM_MARKER_NAME not in result.stdout, result.stdout
    assert "doctor" not in result.stderr.lower(), result.stderr
    # Asserted on the host too: `ls -A` shows the mount points, and these
    # names must not exist under either of them at all.
    assert not (spool / _RESERVED).exists()
    assert not (home / _MEM_MARKER_NAME).exists()


@pytest.mark.integration
@pytest.mark.skipif(not _store_reachable(), reason="session-store backend unreachable")
def test_deployment_is_absent_when_the_contract_does_not_set_it(tmp_path: Path):
    """Absent must stay absent, not become an empty string.

    A single-deployment host genuinely has no deployment identity. Exporting an
    empty SESSION_STORE_ORIGIN_DEPLOYMENT would hand the store an identity of
    nothing to group on as its own source, which is worse than sending none.
    """
    spool = tmp_path / "spool"
    spool.mkdir()
    result = _run(
        [
            "bash",
            "-c",
            "echo ORIGIN_DEPLOYMENT=${SESSION_STORE_ORIGIN_DEPLOYMENT:-unset}",
        ],
        env={
            "AGENTIC_CAPABILITIES": "session-store",
            "AGENTIC_SESSION_STORE_PROVIDER": "seshmagic",
            "AGENTIC_SESSION_STORE_URL": STORE_URL,
            "AGENTIC_SESSION_STORE_SPOOL": "/spool",
            "AGENTIC_SESSION_STORE_PARTITION": "w1/p2",
            "AGENTIC_SESSION_STORE_TAGS": "workflow:w1,phase:p2",
            # AGENTIC_SESSION_STORE_DEPLOYMENT deliberately not set.
        },
        extra_mounts=[
            f"{spool}:/spool",
            f"{_STUB_EXPORTER}:/usr/local/bin/SeshMagicSessionExporter:ro",
        ],
        add_host_gateway=True,
    )
    assert "ORIGIN_DEPLOYMENT=unset" in result.stdout
