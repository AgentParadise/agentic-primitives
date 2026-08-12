import json
import subprocess
import sys

from agentic_session_store.contract import CAPABILITY, Env, SessionStoreContract
from agentic_session_store.doctor import CheckResult, run_checks


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
