"""Cross-package integration with the installed APS session exporter binary."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from agentic_session_store.contract import Env, ExporterEnv

EXPORTER = os.environ.get("LOCAL_CAPTURE_TEST_EXPORTER") or shutil.which(
    "apss-session-exporter"
)
CAPABILITY = (
    Path(__file__).resolve().parents[4] / "workspace/capabilities/session-store"
)


@pytest.mark.skipif(
    not EXPORTER, reason="Set LOCAL_CAPTURE_TEST_EXPORTER to test the real exporter"
)
def test_real_exporter_captures_and_reads_exact_native_bytes_without_store(tmp_path):
    home = tmp_path / "home"
    native = home / ".claude/projects/project"
    native.mkdir(parents=True)
    raw = '{"type":"user","sessionId":"native-test","timestamp":"2026-07-01T00:00:00Z","message":{"role":"user","content":"durable local capture"}}\r\n'
    (native / "native-test.jsonl").write_bytes(raw.encode())
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "HOSTNAME": "local-test",
        Env.PROVIDER: "local",
        Env.PARTITION: "run/phase",
        Env.SPOOL: str(tmp_path / "spool"),
        Env.EXPORTER_BIN: EXPORTER,
    }
    script = 'if . "$1"; then bash "$2"; else exit 1; fi'
    result = subprocess.run(
        [
            "bash",
            "-c",
            script,
            "test",
            str(CAPABILITY / "local/init.sh"),
            str(CAPABILITY / "local/finalize.sh"),
        ],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["stored"] == 1, result.stderr
    # Original source can disappear after capture without losing the envelope.
    (native / "native-test.jsonl").unlink()
    env[ExporterEnv.SPOOL_DIR] = str(
        tmp_path / "spool/.agentic-session-store/run/phase/envelopes"
    )
    page = json.loads(subprocess.check_output([EXPORTER, "--spool-list", "0"], env=env))
    assert len(page["entries"]) == 1
    body = json.loads(
        subprocess.check_output(
            [EXPORTER, "--spool-read", str(page["entries"][0]["sequence"])], env=env
        )
    )
    assert body["raw"] == raw
