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


@dataclass
class FakeRunner:
    """Records every invocation and returns pre-programmed results."""

    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    calls: list[RecordedCall] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], *, stdin: str | None, timeout_s: float
    ) -> tuple[int, str, str]:
        self.calls.append(RecordedCall(argv=list(argv), stdin=stdin))
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

    def test_claude_plugin_dirs_joined_with_colon(self) -> None:
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

        argv = runner.calls[0].argv
        assert "--claude-plugin-dirs" in argv
        idx = argv.index("--claude-plugin-dirs")
        assert argv[idx + 1] == "/plugins/a:/plugins/b"

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

    def test_exit_code_1_raises(self) -> None:
        runner = FakeRunner(stdout="", stderr="await_completion failed", returncode=1)
        client = make_client(runner)

        with pytest.raises(ItmuxError):
            client.await_ready("itmuxdbg-60524", "claude", timeout_s=60.0)


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

    def test_nonzero_exit_code_is_not_an_error(self) -> None:
        runner = FakeRunner(stdout="", stderr="boom", returncode=1)
        client = make_client(runner)

        result = client.exec("itmuxdbg-60524", ["false"])

        assert result.exit_code == 1
        assert result.stderr == "boom"


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
