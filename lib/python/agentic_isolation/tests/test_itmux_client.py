"""Tests for the typed itmux subprocess client.

All tests use a FAKE runner (records argv/stdin, returns canned
stdout/stderr/rc) - no real `itmux` binary or Docker is invoked.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest
from pydantic import ValidationError

from agentic_isolation.itmux_client import (
    AwaitResult,
    ExecResult,
    ItmuxBinaryNotFound,
    ItmuxClient,
    ItmuxError,
    ItmuxStartupError,
    StartReport,
    resolve_itmux_bin,
)

REAL_START_JSON = json.dumps(
    {
        "name": "itmuxdbg-60524",
        "container": "interactive-tmux-itmuxdbg-60524-23a2e180",
        "agents": ["claude"],
        "startup_status": {
            "claude": {
                "duration_ms": 634.25,
                "error": None,
                "pane": "...full pane text...",
                "ready": True,
                "reason": "ready",
                "stable_polls_observed": 1,
                "timed_out": False,
            }
        },
    }
)

REAL_AWAIT_JSON = json.dumps(
    {
        "ready": True,
        "timed_out": False,
        "reason": "ready",
        "duration_ms": 123.45,
        "stable_polls_observed": 4,
        "pane": "",
        "error": None,
    }
)


@dataclass
class RecordedCall:
    argv: list[str]
    stdin: str | None
    env: dict[str, str] | None


@dataclass
class FakeRunner:
    """Records every invocation and returns pre-programmed results."""

    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    calls: list[RecordedCall] = field(default_factory=list)

    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None,
        timeout_s: float,
        env: dict[str, str] | None,
    ) -> tuple[int, str, str]:
        self.calls.append(RecordedCall(argv=list(argv), stdin=stdin, env=env))
        return self.returncode, self.stdout, self.stderr


def make_client(runner: FakeRunner) -> ItmuxClient:
    return ItmuxClient(itmux_bin="/fake/path/itmux", runner=runner)


class TestStart:
    def test_builds_expected_argv(self) -> None:
        runner = FakeRunner(stdout=REAL_START_JSON, returncode=0)
        client = make_client(runner)

        client.start(
            "itmuxdbg-60524",
            image="agentic-workspace-interactive-tmux:latest",
            workdir="/workspace",
            agents=["claude"],
            startup_timeout_s=45.0,
            strict_startup=True,
        )

        assert len(runner.calls) == 1
        argv = runner.calls[0].argv
        assert argv[0] == "/fake/path/itmux"
        assert argv[1] == "start"
        assert "--name" in argv
        assert argv[argv.index("--name") + 1] == "itmuxdbg-60524"
        assert "--image" in argv
        assert argv[argv.index("--image") + 1] == "agentic-workspace-interactive-tmux:latest"
        assert "--workdir" in argv
        assert argv[argv.index("--workdir") + 1] == "/workspace"
        assert "--agents" in argv
        assert argv[argv.index("--agents") + 1] == "claude"
        assert "--startup-timeout" in argv
        assert argv[argv.index("--startup-timeout") + 1] == "45.0"
        assert "--strict-startup" in argv

    def test_omits_strict_startup_flag_when_false(self) -> None:
        runner = FakeRunner(stdout=REAL_START_JSON, returncode=0)
        client = make_client(runner)

        client.start(
            "itmuxdbg-60524",
            image="agentic-workspace-interactive-tmux:latest",
            workdir="/workspace",
            agents=["claude"],
            startup_timeout_s=45.0,
            strict_startup=False,
        )

        argv = runner.calls[0].argv
        assert "--strict-startup" not in argv

    def test_claude_plugin_dirs_passed_via_env_not_flag(self) -> None:
        runner = FakeRunner(stdout=REAL_START_JSON, returncode=0)
        client = make_client(runner)

        client.start(
            "itmuxdbg-60524",
            image="agentic-workspace-interactive-tmux:latest",
            workdir="/workspace",
            agents=["claude"],
            startup_timeout_s=45.0,
            strict_startup=True,
            claude_plugin_dirs=["/plugins/a", "/plugins/b"],
        )

        call = runner.calls[0]
        # itmux has no CLI flag for plugin dirs; they travel via env.
        assert "--claude-plugin-dirs" not in call.argv
        assert call.env is not None
        assert call.env["ITMUX_CLAUDE_PLUGIN_DIRS"] == "/plugins/a:/plugins/b"

    def test_no_plugin_dirs_means_no_env_override(self) -> None:
        runner = FakeRunner(stdout=REAL_START_JSON, returncode=0)
        client = make_client(runner)

        client.start(
            "itmuxdbg-60524",
            image="agentic-workspace-interactive-tmux:latest",
            workdir="/workspace",
            agents=["claude"],
            startup_timeout_s=45.0,
            strict_startup=True,
        )

        call = runner.calls[0]
        # No plugin dirs: env is left untouched (inherit parent), so the
        # var must not appear in any per-call override.
        assert call.env is None or "ITMUX_CLAUDE_PLUGIN_DIRS" not in call.env

    def test_parses_real_start_report_shape(self) -> None:
        runner = FakeRunner(stdout=REAL_START_JSON, returncode=0)
        client = make_client(runner)

        report = client.start(
            "itmuxdbg-60524",
            image="agentic-workspace-interactive-tmux:latest",
            workdir="/workspace",
            agents=["claude"],
            startup_timeout_s=45.0,
            strict_startup=True,
        )

        assert isinstance(report, StartReport)
        assert report.name == "itmuxdbg-60524"
        assert report.container == "interactive-tmux-itmuxdbg-60524-23a2e180"
        assert report.agents == ["claude"]
        assert set(report.startup_status.keys()) == {"claude"}
        status = report.startup_status["claude"]
        assert status.duration_ms == 634.25
        assert status.error is None
        assert status.pane == "...full pane text..."
        assert status.ready is True
        assert status.reason == "ready"
        assert status.stable_polls_observed == 1
        assert status.timed_out is False

    def test_nonzero_exit_raises_itmux_error(self) -> None:
        runner = FakeRunner(stdout="", stderr="docker: not found", returncode=1)
        client = make_client(runner)

        with pytest.raises(ItmuxError) as exc_info:
            client.start(
                "itmuxdbg-60524",
                image="agentic-workspace-interactive-tmux:latest",
                workdir="/workspace",
                agents=["claude"],
                startup_timeout_s=45.0,
                strict_startup=True,
            )

        err = exc_info.value
        assert err.stderr == "docker: not found"
        assert "start" in err.command

    def test_itmux_error_preserves_stdout(self) -> None:
        # itmux can print structured JSON on stdout even on a non-zero
        # exit; that stdout must be preserved on the raised ItmuxError.
        runner = FakeRunner(stdout='{"some":"json"}', stderr="boom", returncode=1)
        client = make_client(runner)

        with pytest.raises(ItmuxError) as exc_info:
            client.start(
                "itmuxdbg-60524",
                image="agentic-workspace-interactive-tmux:latest",
                workdir="/workspace",
                agents=["claude"],
                startup_timeout_s=45.0,
                strict_startup=True,
            )

        assert exc_info.value.stdout == '{"some":"json"}'

    def test_exit_3_with_startreport_raises_typed_startup_error(self) -> None:
        # The real `itmux start` exits 3 on agent startup-readiness
        # failure but still prints a full StartReport (with per-agent
        # startup_status) on stdout. That must surface as a typed
        # ItmuxStartupError carrying the parsed report.
        failed_report_json = json.dumps(
            {
                "name": "itmuxdbg-60524",
                "container": "interactive-tmux-itmuxdbg-60524-23a2e180",
                "agents": ["codex"],
                "startup_status": {
                    "codex": {
                        "duration_ms": 45000.0,
                        "error": "never became ready",
                        "pane": "boot log...",
                        "ready": False,
                        "reason": "timeout_never_ready",
                        "stable_polls_observed": 0,
                        "timed_out": True,
                    }
                },
            }
        )
        runner = FakeRunner(stdout=failed_report_json, stderr="agent not ready", returncode=3)
        client = make_client(runner)

        with pytest.raises(ItmuxStartupError) as exc_info:
            client.start(
                "itmuxdbg-60524",
                image="agentic-workspace-interactive-tmux:latest",
                workdir="/workspace",
                agents=["codex"],
                startup_timeout_s=45.0,
                strict_startup=True,
            )

        err = exc_info.value
        assert isinstance(err, ItmuxError)  # subclass, so generic callers still catch it
        assert err.returncode == 3
        assert err.report.startup_status["codex"].ready is False
        assert err.report.startup_status["codex"].reason == "timeout_never_ready"
        assert err.stdout == failed_report_json

    def test_exit_3_with_unparseable_stdout_raises_plain_itmux_error(self) -> None:
        # If itmux exits 3 but stdout is not a parseable StartReport,
        # fall back to a plain ItmuxError (not the typed startup error).
        runner = FakeRunner(stdout="not json", stderr="agent not ready", returncode=3)
        client = make_client(runner)

        with pytest.raises(ItmuxError) as exc_info:
            client.start(
                "itmuxdbg-60524",
                image="agentic-workspace-interactive-tmux:latest",
                workdir="/workspace",
                agents=["codex"],
                startup_timeout_s=45.0,
                strict_startup=True,
            )

        assert not isinstance(exc_info.value, ItmuxStartupError)
        assert exc_info.value.stdout == "not json"


class TestSend:
    def test_builds_expected_argv_and_returns_none(self) -> None:
        runner = FakeRunner(stdout="", returncode=0)
        client = make_client(runner)

        result = client.send("itmuxdbg-60524", "claude", "hello world")

        assert result is None
        argv = runner.calls[0].argv
        assert argv[1] == "send"
        assert argv[argv.index("--name") + 1] == "itmuxdbg-60524"
        assert argv[argv.index("--agent") + 1] == "claude"
        assert argv[argv.index("--text") + 1] == "hello world"

    def test_nonzero_exit_raises(self) -> None:
        runner = FakeRunner(stdout="", stderr="no registered workspace", returncode=1)
        client = make_client(runner)

        with pytest.raises(ItmuxError):
            client.send("missing", "claude", "hi")


class TestAwaitReady:
    def test_parses_await_result(self) -> None:
        runner = FakeRunner(stdout=REAL_AWAIT_JSON, returncode=0)
        client = make_client(runner)

        result = client.await_ready("itmuxdbg-60524", "claude", timeout_s=60.0)

        assert isinstance(result, AwaitResult)
        assert result.ready is True
        assert result.timed_out is False
        assert result.reason == "ready"
        assert result.duration_ms == 123.45
        assert result.stable_polls_observed == 4
        assert result.error is None

        argv = runner.calls[0].argv
        assert argv[1] == "await"
        assert argv[argv.index("--timeout") + 1] == "60.0"

    def test_exit_code_2_is_not_ready_not_an_error(self) -> None:
        not_ready_json = json.dumps(
            {
                "ready": False,
                "timed_out": True,
                "reason": "timeout_never_ready",
                "duration_ms": 60000.0,
                "stable_polls_observed": 0,
                "pane": "",
                "error": None,
            }
        )
        runner = FakeRunner(stdout=not_ready_json, returncode=2)
        client = make_client(runner)

        result = client.await_ready("itmuxdbg-60524", "claude", timeout_s=60.0)

        assert result.ready is False
        assert result.timed_out is True

    def test_exit_code_1_preserves_stdout(self) -> None:
        runner = FakeRunner(
            stdout='{"reason":"unregistered_workspace"}',
            stderr="await_completion failed",
            returncode=1,
        )
        client = make_client(runner)

        with pytest.raises(ItmuxError) as exc_info:
            client.await_ready("itmuxdbg-60524", "claude", timeout_s=60.0)

        assert exc_info.value.stdout == '{"reason":"unregistered_workspace"}'

    def test_parses_when_pane_key_absent(self) -> None:
        # The real `itmux await` strips `pane` from its printed JSON
        # (see `handle_await` in driver-rs/src/main.rs), so the client
        # must still parse the result with `pane` defaulting to "".
        no_pane_json = json.dumps(
            {
                "ready": True,
                "timed_out": False,
                "reason": "ready",
                "duration_ms": 123.45,
                "stable_polls_observed": 4,
                "error": None,
            }
        )
        assert "pane" not in json.loads(no_pane_json)
        runner = FakeRunner(stdout=no_pane_json, returncode=0)
        client = make_client(runner)

        result = client.await_ready("itmuxdbg-60524", "claude", timeout_s=60.0)

        assert result.ready is True
        assert result.pane == ""


class TestCapture:
    def test_returns_raw_stdout_text(self) -> None:
        runner = FakeRunner(stdout="captured pane text", returncode=0)
        client = make_client(runner)

        text = client.capture("itmuxdbg-60524", "claude")

        assert text == "captured pane text"
        argv = runner.calls[0].argv
        assert argv[1] == "capture"


class TestExec:
    def test_builds_argv_with_trailing_argv(self) -> None:
        runner = FakeRunner(stdout="hi\n", stderr="", returncode=0)
        client = make_client(runner)

        result = client.exec("itmuxdbg-60524", ["echo", "hi"])

        assert isinstance(result, ExecResult)
        assert result.exit_code == 0
        assert result.stdout == "hi\n"
        assert result.stderr == ""
        argv = runner.calls[0].argv
        assert argv[1] == "exec"
        assert argv[-3:] == ["--", "echo", "hi"]

    def test_exit_code_is_itmux_level_not_inner_command(self) -> None:
        # `exit_code` is the itmux-level exit code, not the inner
        # command's. The real `itmux exec` ALWAYS returns 0 on its Ok
        # path (it does NOT forward the inner command's code today), so
        # a failing inner command like `test -e /missing` still surfaces
        # here as exit_code == 0. The fake reproduces that real
        # behaviour: itmux returns 0 even though the inner command
        # "failed".
        runner = FakeRunner(stdout="", stderr="", returncode=0)
        client = make_client(runner)

        result = client.exec("itmuxdbg-60524", ["test", "-e", "/missing"])

        assert result.exit_code == 0

    def test_driver_error_exit_code_is_surfaced_not_raised(self) -> None:
        # A driver-level failure (itmux returns 1) is surfaced on the
        # ExecResult rather than raised - `exec` never raises on a
        # non-zero code, unlike start/send/capture/stop.
        runner = FakeRunner(stdout="", stderr="exec: driver failure", returncode=1)
        client = make_client(runner)

        result = client.exec("itmuxdbg-60524", ["echo", "hi"])

        assert result.exit_code == 1
        assert result.stderr == "exec: driver failure"


class TestStop:
    def test_returns_none_on_success(self) -> None:
        runner = FakeRunner(stdout="", returncode=0)
        client = make_client(runner)

        result = client.stop("itmuxdbg-60524")

        assert result is None
        argv = runner.calls[0].argv
        assert argv[1] == "stop"

    def test_nonzero_exit_raises(self) -> None:
        runner = FakeRunner(stdout="", stderr="stop failed", returncode=1)
        client = make_client(runner)

        with pytest.raises(ItmuxError):
            client.stop("itmuxdbg-60524")


class TestBinaryResolution:
    def test_env_var_wins(self, monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
        import pathlib

        fake_bin = pathlib.Path(str(tmp_path)) / "itmux"
        fake_bin.write_text("#!/bin/sh\n")
        fake_bin.chmod(0o755)
        monkeypatch.setenv("AGENTIC_ITMUX_BIN", str(fake_bin))

        resolved = resolve_itmux_bin()

        assert resolved == str(fake_bin)

    def test_repo_path_used_when_no_env_var(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        import pathlib

        monkeypatch.delenv("AGENTIC_ITMUX_BIN", raising=False)
        repo_bin_dir = pathlib.Path(str(tmp_path)) / (
            "providers/workspaces/interactive-tmux/driver-rs/target/release"
        )
        repo_bin_dir.mkdir(parents=True)
        repo_bin = repo_bin_dir / "itmux"
        repo_bin.write_text("#!/bin/sh\n")
        repo_bin.chmod(0o755)

        resolved = resolve_itmux_bin(repo_root=pathlib.Path(str(tmp_path)))

        assert resolved == str(repo_bin)

    def test_path_fallback(self, monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
        import pathlib

        monkeypatch.delenv("AGENTIC_ITMUX_BIN", raising=False)
        fake_path_dir = pathlib.Path(str(tmp_path)) / "bin"
        fake_path_dir.mkdir()
        path_bin = fake_path_dir / "itmux"
        path_bin.write_text("#!/bin/sh\n")
        path_bin.chmod(0o755)
        monkeypatch.setenv("PATH", str(fake_path_dir))

        resolved = resolve_itmux_bin(repo_root=pathlib.Path(str(tmp_path)) / "nonexistent-repo")

        assert resolved == str(path_bin)

    def test_raises_typed_error_when_nothing_found(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        import pathlib

        monkeypatch.delenv("AGENTIC_ITMUX_BIN", raising=False)
        monkeypatch.setenv("PATH", str(pathlib.Path(str(tmp_path)) / "empty-bin"))

        with pytest.raises(ItmuxBinaryNotFound):
            resolve_itmux_bin(repo_root=pathlib.Path(str(tmp_path)) / "nonexistent-repo")


class TestModelStrictness:
    def test_start_report_rejects_unexpected_field(self) -> None:
        bad_json = json.dumps(
            {
                "name": "x",
                "container": "c",
                "agents": ["claude"],
                "startup_status": {},
                "unexpected_field": "surprise",
            }
        )
        with pytest.raises(ValidationError):
            StartReport.model_validate_json(bad_json)

    def test_await_result_rejects_unexpected_field(self) -> None:
        bad_json = json.dumps(
            {
                "ready": True,
                "timed_out": False,
                "reason": "ready",
                "duration_ms": 1.0,
                "stable_polls_observed": 1,
                "pane": "",
                "error": None,
                "unexpected_field": "surprise",
            }
        )
        with pytest.raises(ValidationError):
            AwaitResult.model_validate_json(bad_json)
