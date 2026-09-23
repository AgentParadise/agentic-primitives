"""Real subprocess launch, stream binding, crash, timeout and shell masking."""

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
    assert last.child_native_id is None
    assert last.exit_code is None
