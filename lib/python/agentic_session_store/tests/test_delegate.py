"""Real subprocess launch, stream binding, crash, timeout and shell masking."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentic_session_store.child_journal import ChildJournal


@pytest.fixture
def environment(tmp_path):
    spool = tmp_path / "spool"
    (spool / ".agentic-session-store/run").mkdir(parents=True)
    binary = tmp_path / "bin"
    binary.mkdir()
    status = tmp_path / "codex-sandbox.json"
    status.write_text(
        json.dumps({"schema_version": 1, "available": True, "detail": "probe ok"})
    )
    return {
        **os.environ,
        "PATH": str(binary),
        "AGENTIC_SESSION_STORE_PROVIDER": "local",
        "AGENTIC_SESSION_STORE_SPOOL": str(spool),
        "AGENTIC_SESSION_STORE_PARTITION": "run",
        "AGENTIC_INVOCATION_ID": "invocation",
        "AGENTIC_ATTEMPT_ID": "attempt",
        "AGENTIC_PARENT_HARNESS": "claude",
        "AGENTIC_PARENT_NATIVE_ID": "parent",
        "AGENTIC_CODEX_SANDBOX_STATUS": str(status),
    }


def _fake(environment, body):
    binary = Path(environment["PATH"].split(os.pathsep)[0]) / "codex"
    binary.write_text(f"#!{sys.executable}\n" + body)
    binary.chmod(0o700)


def _journal(environment):
    return ChildJournal(
        Path(environment["AGENTIC_SESSION_STORE_SPOOL"])
        / ".agentic-session-store/run/children.sqlite"
    )


def _command(timeout=5):
    return [
        sys.executable,
        "-m",
        "agentic_session_store.delegate",
        "codex",
        "--prompt",
        "PRIVATE",
        "--timeout",
        str(timeout),
    ]


@pytest.mark.parametrize("exit_code", [0, 9])
def test_real_process_identity_and_status_survive_restart(environment, exit_code):
    _fake(
        environment,
        'import json,sys\nprint(json.dumps({"type":"thread.started","thread_id":"child"}),flush=True)\nsys.exit('
        + str(exit_code)
        + ")\n",
    )
    result = subprocess.run(
        _command(), env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == exit_code
    changes = _journal(environment).page().changes
    assert len(changes) == 4
    assert changes[0].intent.child_native_id is None
    assert changes[-1].intent.call.target_harness == "codex"
    assert changes[-1].intent.call.harness == "claude"
    assert changes[-1].intent.child_native_id == "child"
    assert changes[-1].intent.exit_code == exit_code
    assert b"PRIVATE" not in result.stderr


def test_shell_success_cannot_hide_delegate_failure(environment):
    import shlex

    _fake(environment, "raise SystemExit(13)\n")
    result = subprocess.run(
        ["/bin/sh", "-c", shlex.join(_command()) + " || true"],
        env=environment,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert _journal(environment).page().changes[-1].intent.exit_code == 13


def test_missing_context_prevents_process_launch(environment, tmp_path):
    marker = tmp_path / "launched"
    _fake(environment, f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    environment.pop("AGENTIC_PARENT_NATIVE_ID")
    result = subprocess.run(
        _command(), env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 70
    assert not marker.exists()
    assert not _journal(environment).page().changes


def test_timeout_records_actual_signal_exit(environment):
    _fake(environment, "import time\ntime.sleep(30)\n")
    result = subprocess.run(
        _command(0.1), env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 128 + signal.SIGTERM
    last = _journal(environment).page().changes[-1].intent
    assert last.status == "cancelled"
    assert last.exit_code == -signal.SIGTERM


def test_cancellation_terminates_child_and_records_outcome(environment):
    _fake(
        environment,
        'import json,time\nprint(json.dumps({"type":"thread.started","thread_id":"child"}),flush=True)\ntime.sleep(30)\n',
    )
    process = subprocess.Popen(
        _command(), env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            changes = _journal(environment).page().changes
            if changes and changes[-1].intent.child_native_id:
                break
            time.sleep(0.02)
        else:
            pytest.fail("delegate did not bind")
        process.terminate()
        process.communicate(timeout=10)
        assert process.returncode == 128 + signal.SIGTERM
        assert (
            _journal(environment).page().changes[-1].intent.exit_code == -signal.SIGTERM
        )
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_codex_native_environment_supplies_parent_and_is_not_inherited(environment):
    environment.pop("AGENTIC_PARENT_HARNESS")
    environment.pop("AGENTIC_PARENT_NATIVE_ID")
    environment["CODEX_THREAD_ID"] = "native-codex-parent"
    environment["CLAUDECODE"] = "1"
    _fake(
        environment,
        'import os\nassert "CODEX_THREAD_ID" not in os.environ\nassert "CLAUDECODE" not in os.environ\nassert os.environ["AGENTIC_INVOCATION_ID"] == "invocation"\n',
    )
    result = subprocess.run(
        _command(), env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr
    call = _journal(environment).page().changes[-1].intent.call
    assert call.harness == "codex"
    assert call.parent_native_id == "native-codex-parent"


def test_failed_os_launch_retains_distinct_intent(environment):
    _fake(environment, "")
    binary = Path(environment["PATH"].split(os.pathsep)[0]) / "codex"
    binary.write_text("#!/definitely-missing-interpreter\n")
    result = subprocess.run(
        _command(), env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 127
    last = _journal(environment).page().changes[-1].intent
    assert last.status == "launch_failed"
    assert last.reason == "process_start_failed"
    assert last.child_native_id is None
    assert last.exit_code is None


def _argv_recorder(tmp_path):
    record = tmp_path / "argv.json"
    return record, (
        f"import json,sys\nopen({str(record)!r},'w').write(json.dumps(sys.argv[1:]))\n"
    )


def test_codex_receives_explicit_workspace_write_sandbox(environment, tmp_path):
    record, body = _argv_recorder(tmp_path)
    _fake(environment, body)
    result = subprocess.run(
        _command(), env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr
    argv = json.loads(record.read_text())
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv


@pytest.mark.parametrize(
    ("cli", "env", "expected"),
    [
        (None, "read-only", "read-only"),
        ("workspace-write", "read-only", "workspace-write"),
        ("read-only", None, "read-only"),
    ],
)
def test_sandbox_mode_override(environment, tmp_path, cli, env, expected):
    record, body = _argv_recorder(tmp_path)
    _fake(environment, body)
    if env is not None:
        environment["AGENTIC_DELEGATE_CODEX_SANDBOX"] = env
    command = _command() + ([] if cli is None else ["--sandbox", cli])
    result = subprocess.run(
        command, env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr
    argv = json.loads(record.read_text())
    assert argv[argv.index("--sandbox") + 1] == expected


@pytest.mark.parametrize("mode", ["danger-full-access", "external-sandbox", "bogus"])
@pytest.mark.parametrize("source", ["cli", "env"])
def test_sandbox_disabling_modes_are_rejected_before_launch(
    environment, tmp_path, mode, source
):
    marker = tmp_path / "launched"
    _fake(environment, f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    command = _command()
    if source == "cli":
        command += ["--sandbox", mode]
    else:
        environment["AGENTIC_DELEGATE_CODEX_SANDBOX"] = mode
    result = subprocess.run(
        command, env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 2
    assert mode.encode() in result.stderr
    assert not marker.exists()
    assert not _journal(environment).page().changes


@pytest.mark.parametrize(
    "status",
    [
        None,
        {"schema_version": 1, "available": False, "detail": "bwrap: no namespace"},
        {"schema_version": 1, "available": "yes"},
        {"schema_version": 99, "available": True},
        "not json",
    ],
)
def test_unavailable_sandbox_refuses_launch_and_records_reason(
    environment, tmp_path, status
):
    marker = tmp_path / "launched"
    _fake(environment, f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    path = Path(environment["AGENTIC_CODEX_SANDBOX_STATUS"])
    if status is None:
        path.unlink()
    elif isinstance(status, str):
        path.write_text(status)
    else:
        path.write_text(json.dumps(status))
    result = subprocess.run(
        _command(), env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 69
    assert b"Codex sandbox is unavailable" in result.stderr
    assert not marker.exists()
    last = _journal(environment).page().changes[-1].intent
    assert last.status == "launch_failed"
    assert last.reason == "codex_sandbox_unavailable"
    assert last.exit_code is None
    assert last.child_native_id is None


def test_claude_delegate_ignores_codex_sandbox_status(environment, tmp_path):
    Path(environment["AGENTIC_CODEX_SANDBOX_STATUS"]).unlink()
    binary = Path(environment["PATH"].split(os.pathsep)[0]) / "claude"
    binary.write_text(f"#!{sys.executable}\n")
    binary.chmod(0o700)
    command = _command()
    command[command.index("codex")] = "claude"
    result = subprocess.run(
        command, env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr


def test_sandbox_flag_is_codex_only(environment):
    command = _command() + ["--sandbox", "read-only"]
    command[command.index("codex")] = "claude"
    result = subprocess.run(
        command, env=environment, capture_output=True, timeout=10, check=False
    )
    assert result.returncode == 2
    assert b"codex only" in result.stderr
