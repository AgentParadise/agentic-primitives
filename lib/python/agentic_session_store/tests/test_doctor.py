import json
import subprocess
import sys

from agentic_session_store.contract import CAPABILITY, Env, SessionStoreContract
from agentic_session_store.doctor import CheckResult, run_checks
import agentic_session_store.doctor as doctor_module


def _contract(tmp_path, url="http://unreachable.invalid"):
    return SessionStoreContract(
        provider="seshmagic",
        url=url,
        auth=None,
        tags=None,
        spool=str(tmp_path),
        partition="w1/p2",
    )


def test_spool_writable_creates_partition(tmp_path):
    results = run_checks(_contract(tmp_path))
    by_name = {r.name: r for r in results}
    assert by_name["spool_writable"].passed
    assert (tmp_path / "w1" / "p2").is_dir()


def test_unreachable_store_fails_that_check_only(tmp_path):
    results = run_checks(_contract(tmp_path))
    by_name = {r.name: r for r in results}
    assert not by_name["store_reachable"].passed
    assert by_name["spool_writable"].passed


def test_json_mode_emits_parseable_object_and_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv(Env.PROVIDER, "seshmagic")
    monkeypatch.setenv(Env.URL, "http://unreachable.invalid")
    monkeypatch.setenv(Env.SPOOL, str(tmp_path))
    monkeypatch.setenv(Env.PARTITION, "w1/p2")
    proc = subprocess.run(
        [sys.executable, "-m", "agentic_session_store.doctor", "--json"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["capability"] == CAPABILITY
    assert payload["passed"] is False


def test_no_contract_is_clean_exit_zero(monkeypatch):
    monkeypatch.delenv(Env.PROVIDER, raising=False)
    proc = subprocess.run(
        [sys.executable, "-m", "agentic_session_store.doctor", "--json"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0


def test_malformed_url_fails_only_that_check_and_still_emits_all_five(tmp_path, monkeypatch):
    """A URL with no scheme must not crash the doctor or short-circuit the run.

    Regression test: `urllib.request.Request(...)` raises ValueError at
    construction for a scheme-less URL, which previously escaped
    store_reachable's except tuple and killed the whole process before any
    JSON was written.
    """
    monkeypatch.setenv(Env.PROVIDER, "seshmagic")
    monkeypatch.setenv(Env.URL, "store-internal-host")
    monkeypatch.setenv(Env.SPOOL, str(tmp_path))
    monkeypatch.setenv(Env.PARTITION, "w1/p2")
    proc = subprocess.run(
        [sys.executable, "-m", "agentic_session_store.doctor", "--json"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert proc.stdout.strip(), f"no JSON on stdout; stderr was:\n{proc.stderr}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["capability"] == CAPABILITY
    assert payload["passed"] is False
    assert len(payload["checks"]) == 5
    by_name = {c["name"]: c for c in payload["checks"]}
    assert by_name["store_reachable"]["passed"] is False
    assert by_name["spool_writable"]["passed"] is True


def test_symlinks_correct_passes_when_each_link_targets_its_own_subdir(tmp_path, monkeypatch):
    """~/.claude/projects and ~/.codex/sessions must resolve to their OWN
    claude/ and codex/ subdirectories under the partition, matching the
    layout the seshmagic adapter's init.sh actually creates. Needs no
    store, no container.
    """
    partition_dir = tmp_path / "spool" / "w1" / "p2"
    claude_dir = partition_dir / "claude"
    codex_dir = partition_dir / "codex"
    claude_dir.mkdir(parents=True)
    codex_dir.mkdir(parents=True)

    claude_link = tmp_path / "home" / ".claude" / "projects"
    codex_link = tmp_path / "home" / ".codex" / "sessions"
    claude_link.parent.mkdir(parents=True)
    codex_link.parent.mkdir(parents=True)
    claude_link.symlink_to(claude_dir)
    codex_link.symlink_to(codex_dir)

    monkeypatch.setattr(doctor_module, "CLAUDE_PROJECTS_DIR", str(claude_link))
    monkeypatch.setattr(doctor_module, "CODEX_SESSIONS_DIR", str(codex_link))

    result = doctor_module._symlinks_correct(
        _contract(tmp_path / "spool", url="http://unreachable.invalid")
    )
    assert result.passed is True


def test_symlinks_correct_fails_when_both_links_point_at_the_partition_root(tmp_path, monkeypatch):
    """Regression test for the shipped defect: comparing both symlinks
    against the SAME partition root (instead of each against its own
    claude/ or codex/ subdirectory) can never fail even when the layout
    is wrong in exactly this way. Both links resolving to the bare
    partition directory (not a per-harness subdirectory) must FAIL.
    """
    partition_dir = tmp_path / "spool" / "w1" / "p2"
    partition_dir.mkdir(parents=True)

    claude_link = tmp_path / "home" / ".claude" / "projects"
    codex_link = tmp_path / "home" / ".codex" / "sessions"
    claude_link.parent.mkdir(parents=True)
    codex_link.parent.mkdir(parents=True)
    claude_link.symlink_to(partition_dir)
    codex_link.symlink_to(partition_dir)

    monkeypatch.setattr(doctor_module, "CLAUDE_PROJECTS_DIR", str(claude_link))
    monkeypatch.setattr(doctor_module, "CODEX_SESSIONS_DIR", str(codex_link))

    result = doctor_module._symlinks_correct(
        _contract(tmp_path / "spool", url="http://unreachable.invalid")
    )
    assert result.passed is False


def _doctor_json(monkeypatch, **env):
    """Run the doctor as a subprocess with `env` applied, return (proc, payload).

    payload is None when stdout held no JSON, which is itself the defect
    these tests exist to catch.
    """
    for name, value in env.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    proc = subprocess.run(
        [sys.executable, "-m", "agentic_session_store.doctor", "--json"],
        capture_output=True, text=True,
    )
    payload = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else None
    return proc, payload


def _assert_contract_failure(proc, payload, expected_in_detail):
    """Every malformed-contract case must produce the SAME structured shape.

    The audit log at entrypoint.sh 5.7 appends this object; a traceback and
    an empty file are indistinguishable from "the doctor never ran".
    """
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr, proc.stderr
    assert payload is not None, f"no JSON on stdout; stderr was:\n{proc.stderr}"
    assert payload["capability"] == CAPABILITY
    assert payload["passed"] is False
    checks = {c["name"]: c for c in payload["checks"]}
    assert checks["contract_parses"]["passed"] is False
    assert expected_in_detail in checks["contract_parses"]["detail"]
    # Same shape as a normal run: an audit reader parses one schema, not two.
    assert len(payload["checks"]) == 5


def test_missing_url_emits_json_and_exits_1(tmp_path, monkeypatch):
    """A raising contract must become a failed structured result, not a traceback."""
    proc, payload = _doctor_json(
        monkeypatch,
        **{
            Env.PROVIDER: "seshmagic",
            Env.URL: None,  # required, so from_env raises
            Env.SPOOL: str(tmp_path),
            Env.PARTITION: "w1/p2",
        },
    )
    _assert_contract_failure(proc, payload, Env.URL)


def test_invalid_partition_emits_json_and_exits_1(tmp_path, monkeypatch):
    proc, payload = _doctor_json(
        monkeypatch,
        **{
            Env.PROVIDER: "seshmagic",
            Env.URL: "http://unreachable.invalid",
            Env.SPOOL: str(tmp_path),
            Env.PARTITION: "../escape",
        },
    )
    _assert_contract_failure(proc, payload, "partition")


def test_invalid_spool_emits_json_and_exits_1(monkeypatch):
    proc, payload = _doctor_json(
        monkeypatch,
        **{
            Env.PROVIDER: "seshmagic",
            Env.URL: "http://unreachable.invalid",
            Env.SPOOL: "not/an/absolute/path",
            Env.PARTITION: "w1/p2",
        },
    )
    _assert_contract_failure(proc, payload, "spool")


def test_run_checks_converts_a_raising_check_into_a_failed_result(tmp_path, monkeypatch):
    """run_checks must never let an individual check's exception propagate."""

    def _boom(contract):
        raise ValueError("embedded \x00 null byte or some other unanticipated failure")

    monkeypatch.setattr(doctor_module, "CHECKS", [("exploding_check", _boom)])

    results = run_checks(_contract(tmp_path))

    assert len(results) == 1
    assert results[0].name == "exploding_check"
    assert results[0].passed is False
    assert "ValueError" in results[0].detail
