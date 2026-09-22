"""Local workspace capture requires no store and preserves native roots."""

import os
import subprocess
from pathlib import Path

import pytest

from agentic_session_store.contract import Env, ExporterEnv, SessionStoreContract
from agentic_session_store.doctor import _exporter_present, _store_reachable

CAPABILITY = (
    Path(__file__).resolve().parents[4] / "workspace/capabilities/session-store"
)


@pytest.mark.parametrize(
    "help_text,expected",
    [("--spool-only --spool-list --spool-read", True), ("--version --json", False)],
)
def test_local_preflight_rejects_exporter_without_local_interface(
    tmp_path, monkeypatch, help_text, expected
):
    binary = tmp_path / "exporter"
    binary.write_text(f"#!/bin/sh\nprintf '%s\\n' '{help_text}'\n")
    binary.chmod(0o700)
    monkeypatch.setenv(Env.EXPORTER_BIN, str(binary))
    contract = SessionStoreContract.from_env(
        {Env.PROVIDER: "local", Env.PARTITION: "run"}
    )
    assert contract is not None
    assert _exporter_present(contract).passed is expected


def test_local_contract_needs_no_url_and_never_probes_store(monkeypatch):
    contract = SessionStoreContract.from_env(
        {Env.PROVIDER: "local", Env.PARTITION: "run"}
    )
    assert contract is not None
    assert contract.url == ""

    def unexpected_network(*args, **kwargs):
        raise AssertionError("local capture must not probe a remote store")

    monkeypatch.setattr(
        "agentic_session_store.doctor._SAME_ORIGIN_OPENER.open", unexpected_network
    )
    assert _store_reachable(contract).passed
    with pytest.raises(ValueError, match="required"):
        SessionStoreContract.from_env({Env.PROVIDER: "apss", Env.PARTITION: "run"})


def test_local_init_preserves_native_roots_and_exports_durable_index(tmp_path):
    home = tmp_path / "home"
    native = home / ".claude/projects/project"
    native.mkdir(parents=True)
    (native / "session.jsonl").write_text("original native bytes\n")
    spool = tmp_path / "spool"
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "HOSTNAME": "test",
        Env.PROVIDER: "local",
        Env.SPOOL: str(spool),
        Env.PARTITION: "run/phase",
    }
    script = f'if . "$1"; then printf "%s\\n" "${{{ExporterEnv.SPOOL_DIR}}}"; else exit 1; fi'
    result = subprocess.run(
        ["bash", "-c", script, "test", str(CAPABILITY / "local/init.sh")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    index = spool / ".agentic-session-store/run/phase/envelopes"
    assert result.stdout.strip() == str(index)
    assert index.is_dir()
    assert (index.parent / "children.sqlite").is_file()
    import tomllib

    config = tomllib.loads((home / ".codex/config.toml").read_text())
    assert config["hooks"]["PreToolUse"][0]["matcher"] == "spawn_agent"
    assert (home / ".claude/projects").is_symlink()
    assert (
        spool / "run/phase/claude/project/session.jsonl"
    ).read_text() == "original native bytes\n"


@pytest.mark.parametrize("exit_code", [0, 3, 1])
def test_local_finalizer_invokes_local_capture_and_retains_files(tmp_path, exit_code):
    exporter = tmp_path / "exporter"
    exporter.write_text(
        f'#!/bin/sh\n[ "$1" = "--spool-only" ] || exit 99\necho invoked\nexit {exit_code}\n'
    )
    exporter.chmod(0o700)
    retained = tmp_path / "native.jsonl"
    retained.write_text("recoverable")
    env = {
        "PATH": os.environ["PATH"],
        Env.EXPORTER_BIN: str(exporter),
        ExporterEnv.SPOOL_DIR: str(tmp_path),
    }
    result = subprocess.run(
        ["bash", str(CAPABILITY / "local/finalize.sh")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "invoked" in result.stdout
    assert (
        "requires recovery" in result.stderr or "require recovery" in result.stderr
    ) == (exit_code != 0)
    assert retained.read_text() == "recoverable"


def test_local_init_does_not_claim_ready_when_hooks_are_disabled(tmp_path):
    home = tmp_path / "home"
    (home / ".codex").mkdir(parents=True)
    config = home / ".codex/config.toml"
    original = "[features]\nhooks=false\n"
    config.write_text(original)
    spool = tmp_path / "spool"
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "HOSTNAME": "test",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        Env.PROVIDER: "local",
        Env.SPOOL: str(spool),
        Env.PARTITION: "run/phase",
    }
    result = subprocess.run(
        ["bash", "-c", '. "$1"', "test", str(CAPABILITY / "local/init.sh")],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert config.read_text() == original
    assert not (spool / ".agentic-session-store/run/phase/.init-complete").exists()
