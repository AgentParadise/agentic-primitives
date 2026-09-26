"""The capture probe fails closed when a hook's shell never reaches the guard.

A shell startup file runs before the hook command. Codex 0.156.1 runs hooks
with the passwd shell and ``-c``, so bash reads ``$BASH_ENV`` and zsh reads
``.zshenv`` first. One that exits or hangs makes the harness launch the child.
"""

import os
import shutil
import sys
from pathlib import Path

import pytest

from agentic_session_store.contract import METADATA_NAMESPACE, Env
from agentic_session_store.hook_command import HookHarness
from agentic_session_store.hook_probe import CaptureProbeError, main, probe_guard


@pytest.fixture
def environment(tmp_path: Path) -> dict[str, str]:
    (tmp_path / METADATA_NAMESPACE / "run").mkdir(parents=True)
    directory = tmp_path / "bin"
    directory.mkdir()
    shim = directory / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    shim.chmod(0o755)
    (directory / "sleep").symlink_to(shutil.which("sleep"))
    return {
        "PATH": str(directory),
        "HOME": str(tmp_path),
        "PYTHONPATH": os.pathsep.join(sys.path),
        Env.PROVIDER: "local",
        Env.SPOOL: str(tmp_path),
        Env.PARTITION: "run",
    }


BASH = shutil.which("bash")
ZSH = shutil.which("zsh")


@pytest.mark.parametrize("harness", list(HookHarness))
def test_reachable_guard_passes(environment, harness) -> None:
    probe_guard(harness, environment, shells=[("/bin/sh", "-c")])
    if BASH:
        probe_guard(harness, environment, shells=[(BASH, "-c")])


def test_missing_contract_fails(environment) -> None:
    environment.pop(Env.PROVIDER)
    with pytest.raises(CaptureProbeError):
        probe_guard(HookHarness.CODEX, environment, shells=[("/bin/sh", "-c")])


def test_missing_interpreter_fails(environment, tmp_path) -> None:
    (tmp_path / "bin/python3").unlink()
    with pytest.raises(CaptureProbeError):
        probe_guard(HookHarness.CLAUDE, environment, shells=[("/bin/sh", "-c")])


@pytest.mark.skipif(BASH is None, reason="bash not installed")
@pytest.mark.parametrize("startup", ["exit 0", "exit 2", "sleep 30", "echo noise >&2"])
def test_bash_env_that_preempts_the_guard_fails(environment, tmp_path, startup) -> None:
    rc = tmp_path / "bash_env"
    rc.write_text(startup + "\n")
    environment["BASH_ENV"] = str(rc)
    with pytest.raises(CaptureProbeError):
        probe_guard(HookHarness.CODEX, environment, shells=[(BASH, "-c")], timeout=3)


@pytest.mark.skipif(ZSH is None, reason="zsh not installed")
@pytest.mark.parametrize("startup", ["exit 0", "sleep 30"])
def test_zshenv_that_preempts_the_guard_fails(environment, tmp_path, startup) -> None:
    zdot = tmp_path / "zdot"
    zdot.mkdir()
    (zdot / ".zshenv").write_text(startup + "\n")
    environment["ZDOTDIR"] = str(zdot)
    with pytest.raises(CaptureProbeError):
        probe_guard(HookHarness.CODEX, environment, shells=[(ZSH, "-c")], timeout=3)


@pytest.mark.skipif(ZSH is None, reason="zsh not installed")
def test_clean_zsh_passes(environment, tmp_path) -> None:
    zdot = tmp_path / "zdot"
    zdot.mkdir()
    environment["ZDOTDIR"] = str(zdot)
    probe_guard(HookHarness.CODEX, environment, shells=[(ZSH, "-c")])


def test_main_reports_failure_generically(environment, monkeypatch, capsys) -> None:
    environment.pop(Env.PROVIDER)
    monkeypatch.setattr(os, "environ", environment)
    assert main(["--harness", "claude"]) == 1
    assert "probe failed" in capsys.readouterr().err


def test_startup_file_trust_requires_root_owned_unwritable_path(tmp_path) -> None:
    from agentic_session_store.hook_probe import (
        trusted_startup_file,
        without_untrusted_startup,
    )

    agent_file = tmp_path / "rc"
    agent_file.write_text("exit 0\n")
    assert not trusted_startup_file(str(agent_file))
    assert not trusted_startup_file("relative/rc")
    assert not trusted_startup_file("/nonexistent/rc")
    assert trusted_startup_file("/etc/passwd")
    clean = without_untrusted_startup(
        {"BASH_ENV": str(agent_file), "ENV": "/etc/passwd", "OTHER": "kept"}
    )
    assert clean == {"ENV": "/etc/passwd", "OTHER": "kept"}


@pytest.mark.parametrize("name", ["BASH_ENV", "ENV"])
def test_agent_modifiable_startup_variable_fails_even_if_harmless_now(
    environment, tmp_path, name
) -> None:
    """Passing now proves nothing: the agent can edit the file after the probe."""
    rc = tmp_path / "rc"
    rc.write_text(": harmless for now\n")
    environment[name] = str(rc)
    with pytest.raises(CaptureProbeError):
        probe_guard(HookHarness.CODEX, environment, shells=[("/bin/sh", "-c")])
