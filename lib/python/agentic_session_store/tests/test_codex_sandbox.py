"""Sandbox mode validation and the fail-closed live probe."""

import os
import sys

import pytest

from agentic_session_store.codex_sandbox import (
    CodexSandboxMode,
    parse_sandbox_mode,
    probe,
    resolve_sandbox_mode,
)


@pytest.mark.parametrize("value", [None, "", "  "])
def test_default_mode_is_workspace_write(value):
    assert parse_sandbox_mode(value) is CodexSandboxMode.WORKSPACE_WRITE


@pytest.mark.parametrize("mode", list(CodexSandboxMode))
def test_allowed_modes_round_trip(mode):
    assert parse_sandbox_mode(mode.value) is mode


@pytest.mark.parametrize("value", ["danger-full-access", "external-sandbox"])
def test_sandbox_disabling_modes_are_refused_by_name(value):
    with pytest.raises(ValueError, match="disables the sandbox"):
        parse_sandbox_mode(value)


@pytest.mark.parametrize("value", ["full-auto", "WORKSPACE-WRITE", "none"])
def test_unknown_modes_are_refused(value):
    with pytest.raises(ValueError, match="Unknown Codex sandbox mode"):
        parse_sandbox_mode(value)


def test_cli_value_wins_over_environment():
    environment = {"AGENTIC_DELEGATE_CODEX_SANDBOX": "read-only"}
    assert resolve_sandbox_mode(None, environment) is CodexSandboxMode.READ_ONLY
    assert (
        resolve_sandbox_mode("workspace-write", environment)
        is CodexSandboxMode.WORKSPACE_WRITE
    )


def _codex(tmp_path, body):
    binary = tmp_path / "bin" / "codex"
    binary.parent.mkdir(exist_ok=True)
    binary.write_text(f"#!{sys.executable}\n" + body)
    binary.chmod(0o700)
    return {**os.environ, "PATH": str(binary.parent)}


def test_probe_passes_on_clean_exit(tmp_path):
    record = tmp_path / "argv"
    env = _codex(
        tmp_path,
        f"import sys,os\nopen({str(record)!r},'w').write(repr((sys.argv[1:], os.getcwd())))\n",
    )
    status = probe(CodexSandboxMode.READ_ONLY, environment=env, cwd=str(tmp_path))
    assert status.available
    argv, cwd = eval(record.read_text())  # written by this test
    assert argv == ["sandbox", "-c", 'sandbox_mode="read-only"', "--", "true"]
    assert os.path.realpath(cwd) == os.path.realpath(tmp_path)


def test_probe_reports_the_bwrap_cause(tmp_path):
    env = _codex(
        tmp_path,
        "import sys\nprint('warning: noise', file=sys.stderr)\n"
        "print('bwrap: Failed to make / slave: Permission denied', file=sys.stderr)\n"
        "print('trailing', file=sys.stderr)\nsys.exit(1)\n",
    )
    status = probe(CodexSandboxMode.WORKSPACE_WRITE, environment=env)
    assert not status.available
    assert (
        status.detail
        == "probe exit 1: bwrap: Failed to make / slave: Permission denied"
    )


def test_probe_fails_closed_without_codex(tmp_path):
    status = probe(
        CodexSandboxMode.WORKSPACE_WRITE, environment={"PATH": str(tmp_path / "empty")}
    )
    assert not status.available
    assert "not installed" in status.detail


def test_probe_fails_closed_on_timeout(tmp_path):
    env = _codex(tmp_path, "import time\ntime.sleep(5)\n")
    status = probe(CodexSandboxMode.WORKSPACE_WRITE, environment=env, timeout=0.5)
    assert not status.available
    assert "timed out" in status.detail
