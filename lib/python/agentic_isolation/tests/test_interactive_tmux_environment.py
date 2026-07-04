"""Environment seam tests (issue #225 follow-up): provisioning becomes
pluggable, one layer above `CommandExecutor`.

Covers:
  * `DockerEnvironment.start()` runs the exact `docker run ...` shape
    `start_workspace` always ran, and returns a `DockerExecExecutor` bound
    to the container it created.
  * `DockerEnvironment.stop()` runs `docker rm -f <name>` and tolerates a
    wedged/timed-out `subprocess.run` the same way the old inline
    `InteractiveTmuxWorkspace.stop()` logic did.
  * `start_workspace(environment=None)` (the default) builds its own
    `DockerEnvironment` from `image`/`workdir` — zero behavior change for
    every existing caller.
  * `start_workspace(environment=<fake>)` uses the injected `Environment`
    instead of constructing a `DockerEnvironment` / shelling out to
    `docker run` at all, and `ws.stop()` delegates to the injected
    environment's `.stop()`.

No real docker daemon or tmux required; subprocess calls are monkeypatched
at the driver module level, matching the convention of the sibling
interactive-tmux test files.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


def _load_driver_module():
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = (
            ancestor
            / "providers"
            / "workspaces"
            / "interactive-tmux"
            / "driver"
            / "interactive_tmux.py"
        )
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("interactive_tmux", candidate)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules.setdefault("interactive_tmux", module)
            spec.loader.exec_module(module)
            return module
    pytest.skip("interactive_tmux driver not found in repo layout")


driver = _load_driver_module()


@pytest.fixture
def fake_claude_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / ".credentials.json").write_text("{}")
    (home / ".claude.json").write_text("{}")
    return claude_dir


class _FakeEnvironment:
    """Records lifecycle calls instead of touching docker at all."""

    def __init__(self, executor=None) -> None:
        self.started = False
        self.stopped = False
        self._executor = executor or _FakeExecutor()

    def start(self):
        self.started = True
        return self._executor

    def stop(self) -> None:
        self.stopped = True


class _FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def exec(self, command, *, timeout_s=None):  # noqa: ARG002
        self.calls.append(list(command))
        return driver.ExecResult(exit_code=0, stdout="", stderr="")


class TestEnvironmentProtocol:
    def test_docker_environment_satisfies_protocol(self) -> None:
        env = driver.DockerEnvironment(name="c", image="img", workdir="/workspace")
        assert isinstance(env, driver.Environment)

    def test_fake_environment_satisfies_protocol(self) -> None:
        assert isinstance(_FakeEnvironment(), driver.Environment)


class TestDockerEnvironmentStart:
    def test_start_runs_expected_docker_run_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, check=True, capture=True, timeout_s=None):
            captured["cmd"] = cmd
            captured["timeout_s"] = timeout_s
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver, "_run", fake_run)

        env = driver.DockerEnvironment(
            name="my-container", image="my-image:latest", workdir="/workspace"
        )
        executor = env.start()

        assert captured["cmd"] == [
            "docker",
            "run",
            "-d",
            "--name",
            "my-container",
            "--workdir",
            "/workspace",
            "my-image:latest",
            "sleep",
            "infinity",
        ]
        assert isinstance(executor, driver.DockerExecExecutor)
        assert executor.target == "my-container"
        assert captured["timeout_s"] == driver.DEFAULT_RUN_TIMEOUT_S

    def test_start_honors_custom_run_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, check=True, capture=True, timeout_s=None):
            captured["timeout_s"] = timeout_s
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver, "_run", fake_run)

        env = driver.DockerEnvironment(
            name="my-container",
            image="my-image:latest",
            workdir="/workspace",
            run_timeout_s=2.5,
        )
        env.start()

        assert captured["timeout_s"] == 2.5

    def test_start_propagates_run_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def failing_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(125, cmd)

        monkeypatch.setattr(driver, "_run", failing_run)
        env = driver.DockerEnvironment(name="c", image="img", workdir="/workspace")
        with pytest.raises(subprocess.CalledProcessError):
            env.start()


class TestDockerEnvironmentStop:
    def test_stop_runs_docker_rm_dash_f(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)
        env = driver.DockerEnvironment(name="my-container", image="img", workdir="/workspace")
        env.stop()

        assert captured["cmd"] == ["docker", "rm", "-f", "my-container"]
        assert captured["kwargs"]["check"] is False

    def test_stop_tolerates_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def timing_out_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

        monkeypatch.setattr(driver.subprocess, "run", timing_out_run)
        env = driver.DockerEnvironment(name="c", image="img", workdir="/workspace")
        # Must not raise.
        env.stop()


class TestStartWorkspaceEnvironmentInjection:
    def test_default_environment_is_docker_environment(
        self, fake_claude_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`environment=None` (the default) must build a `DockerEnvironment`
        from `image`/`workdir` exactly as `start_workspace` always did —
        zero behavior change for every existing caller."""
        captured: dict = {}

        def fake_run(cmd, check=True, capture=True, timeout_s=None):
            captured["run_cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver, "_run", fake_run)
        monkeypatch.setattr(
            driver.InteractiveTmuxWorkspace,
            "_bootstrap_tmux_and_launch",
            lambda self, *a, **k: None,
        )
        monkeypatch.setattr(
            driver.subprocess,
            "run",
            lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "", ""),
        )

        ws = driver.InteractiveTmuxWorkspace.start_workspace(
            name="envdefault",
            host_auth={"claude": fake_claude_home},
            image="custom-image:latest",
            workdir="/custom-workdir",
        )
        try:
            assert isinstance(ws.environment, driver.DockerEnvironment)
            assert ws.environment.image == "custom-image:latest"
            assert ws.environment.workdir == "/custom-workdir"
            assert captured["run_cmd"][:2] == ["docker", "run"]
            assert "--name" in captured["run_cmd"]
        finally:
            ws.stop()

    def test_injected_environment_is_used_instead_of_docker_run(
        self, fake_claude_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When `environment=` is passed, `start_workspace` must not shell
        out to `docker run` at all — it uses the injected `Environment`."""
        fake_executor = _FakeExecutor()
        fake_env = _FakeEnvironment(executor=fake_executor)

        def unexpected_run(cmd, **kwargs):
            raise AssertionError(
                f"start_workspace should not call _run() when environment= is injected: {cmd}"
            )

        monkeypatch.setattr(driver, "_run", unexpected_run)
        monkeypatch.setattr(
            driver.InteractiveTmuxWorkspace,
            "_bootstrap_tmux_and_launch",
            lambda self, *a, **k: None,
        )

        ws = driver.InteractiveTmuxWorkspace.start_workspace(
            name="envinjected",
            host_auth={"claude": fake_claude_home},
            environment=fake_env,
        )

        assert fake_env.started is True
        assert ws.environment is fake_env
        assert ws.executor is fake_executor
        # Credential bytes must have been transferred over the injected
        # executor (not a freshly-constructed DockerExecExecutor).
        assert fake_executor.calls

        ws.stop()
        assert fake_env.stopped is True

    def test_injected_environment_stop_called_on_bootstrap_failure(
        self, fake_claude_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failure after provisioning (e.g. tmux bootstrap) must still
        tear down the injected environment, not just a DockerEnvironment."""
        fake_env = _FakeEnvironment()

        def failing_bootstrap(self, *a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            driver.InteractiveTmuxWorkspace, "_bootstrap_tmux_and_launch", failing_bootstrap
        )

        with pytest.raises(RuntimeError, match="boom"):
            driver.InteractiveTmuxWorkspace.start_workspace(
                name="envfail",
                host_auth={"claude": fake_claude_home},
                environment=fake_env,
            )

        assert fake_env.started is True
        assert fake_env.stopped is True

    def test_bootstrap_passes_injected_executor_to_agent_launch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_executor = _FakeExecutor()
        ws = driver.InteractiveTmuxWorkspace(
            name="envbootstrap",
            container="not-a-docker-container",
            image="img",
            workdir="/workspace",
            tmux_size=(200, 50),
            host_throwaway_dir=Path("/tmp/envbootstrap"),
            enabled_agents=("claude",),
            executor=fake_executor,
        )
        captured: dict = {}

        def fake_launch(container, workdir, plugin_dirs=None, *, executor=None, timeout_s=None):
            captured["container"] = container
            captured["workdir"] = workdir
            captured["plugin_dirs"] = plugin_dirs
            captured["executor"] = executor
            captured["timeout_s"] = timeout_s

        monkeypatch.setattr(
            driver._ADAPTERS["claude"],
            "launch_in_window",
            staticmethod(fake_launch),
        )
        monkeypatch.setattr(
            ws,
            "_wait_for_started",
            lambda agent, timeout_s: driver.AwaitResult(
                ready=True,
                timed_out=False,
                reason="ready",
                duration_ms=0.0,
                stable_polls_observed=1,
            ),
        )

        ws._bootstrap_tmux_and_launch(startup_timeout_s=1.0, strict_startup=True)

        assert captured["container"] == "not-a-docker-container"
        assert captured["workdir"] == "/workspace"
        assert captured["executor"] is fake_executor


class TestLocalExecutor:
    def test_exec_happy_path_runs_argv_directly_no_docker_prefix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(cmd, 0, "out", "err")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        executor = driver.LocalExecutor(workdir=tmp_path)
        result = executor.exec(["echo", "hi"], timeout_s=5)

        assert captured["cmd"] == ["echo", "hi"]
        assert captured["kwargs"]["cwd"] == tmp_path
        assert captured["kwargs"]["timeout"] == 5
        assert captured["kwargs"]["capture_output"] is True
        assert captured["kwargs"]["text"] is True
        assert result == driver.ExecResult(exit_code=0, stdout="out", stderr="err")

    def test_exec_timeout_returns_timed_out_exec_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def timing_out_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

        monkeypatch.setattr(driver.subprocess, "run", timing_out_run)

        executor = driver.LocalExecutor(workdir=tmp_path)
        result = executor.exec(["sleep", "99"], timeout_s=1)

        assert result.timed_out is True
        assert result.exit_code == -1
        assert "timed out after 1s" in result.stderr

    def test_exec_cwd_passed_through(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cwd"] = kwargs.get("cwd")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)
        executor = driver.LocalExecutor(workdir=tmp_path)
        executor.exec(["pwd"])

        assert captured["cwd"] == tmp_path


class TestLocalEnvironment:
    def test_satisfies_environment_protocol(self, tmp_path: Path) -> None:
        env = driver.LocalEnvironment(workdir=tmp_path)
        assert isinstance(env, driver.Environment)

    def test_start_raises_runtime_error_when_tmux_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(driver.shutil, "which", lambda tool: None)
        env = driver.LocalEnvironment(workdir=tmp_path)

        with pytest.raises(RuntimeError, match="tmux"):
            env.start()

    def test_start_returns_local_executor_when_tmux_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(driver.shutil, "which", lambda tool: "/usr/bin/tmux")
        env = driver.LocalEnvironment(workdir=tmp_path)

        executor = env.start()

        assert isinstance(executor, driver.LocalExecutor)
        assert executor.workdir == tmp_path

    def test_stop_is_a_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(driver.shutil, "which", lambda tool: "/usr/bin/tmux")
        env = driver.LocalEnvironment(workdir=tmp_path)
        env.start()
        # Must not raise, must not touch subprocess at all.
        env.stop()


class TestSSHExecutor:
    def test_exec_happy_path_builds_expected_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(cmd, 0, "out", "err")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        base_argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-i",
            "/home/me/.ssh/id_ed25519",
            "-p",
            "22",
            "--",
            "me@example.com",
        ]
        executor = driver.SSHExecutor(base_argv)
        result = executor.exec(["echo", "hi there"], timeout_s=5)

        assert captured["cmd"] == [*base_argv, "echo 'hi there'"]
        assert captured["kwargs"]["timeout"] == 5
        assert captured["kwargs"]["capture_output"] is True
        assert captured["kwargs"]["text"] is True
        assert result == driver.ExecResult(exit_code=0, stdout="out", stderr="err")

    def test_exec_timeout_returns_timed_out_exec_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def timing_out_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

        monkeypatch.setattr(driver.subprocess, "run", timing_out_run)

        executor = driver.SSHExecutor(["ssh", "me@example.com"])
        result = executor.exec(["sleep", "99"], timeout_s=1)

        assert result.timed_out is True
        assert result.exit_code == -1
        assert "timed out after 1s" in result.stderr

    def test_exec_prefixes_cd_when_workdir_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        base_argv = ["ssh", "me@example.com"]
        executor = driver.SSHExecutor(base_argv, workdir="/remote/work")
        executor.exec(["pwd"])

        assert captured["cmd"] == [*base_argv, "cd /remote/work && pwd"]

    def test_exec_omits_cd_when_no_workdir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        base_argv = ["ssh", "me@example.com"]
        executor = driver.SSHExecutor(base_argv)
        executor.exec(["pwd"])

        assert captured["cmd"] == [*base_argv, "pwd"]


class TestSSHEnvironment:
    def test_satisfies_environment_protocol(self) -> None:
        env = driver.SSHEnvironment(host="example.com", user="me")
        assert isinstance(env, driver.Environment)

    def test_start_runs_reachability_check_with_expected_argv(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        env = driver.SSHEnvironment(
            host="example.com",
            user="me",
            key_path="/home/me/.ssh/id_ed25519",
            port=2222,
            workdir="/remote/work",
            connect_timeout_s=7.0,
        )
        executor = env.start()

        assert captured["cmd"] == [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=7",
            "-i",
            "/home/me/.ssh/id_ed25519",
            "-p",
            "2222",
            "--",
            "me@example.com",
            "true",
        ]
        assert captured["kwargs"]["timeout"] == 7.0
        assert isinstance(executor, driver.SSHExecutor)
        assert executor.workdir == "/remote/work"
        assert executor.base_argv == [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=7",
            "-i",
            "/home/me/.ssh/id_ed25519",
            "-p",
            "2222",
            "--",
            "me@example.com",
        ]

    def test_base_argv_uses_option_terminator_before_destination(self) -> None:
        env = driver.SSHEnvironment(host="-oProxyCommand=bad", user="-l bad")

        argv = env._base_argv()

        assert argv[-2] == "--"
        assert argv[-1] == "-l bad@-oProxyCommand=bad"

    def test_start_without_key_path_omits_dash_i(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        env = driver.SSHEnvironment(host="example.com", user="me")
        env.start()

        assert "-i" not in captured["cmd"]

    def test_start_raises_runtime_error_with_stderr_on_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(
                cmd, 255, "", "ssh: connect to host example.com port 22: Connection refused"
            )

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        env = driver.SSHEnvironment(host="example.com", user="me")

        with pytest.raises(RuntimeError, match="Connection refused"):
            env.start()

    def test_start_raises_runtime_error_on_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def timing_out_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

        monkeypatch.setattr(driver.subprocess, "run", timing_out_run)

        env = driver.SSHEnvironment(host="example.com", user="me", connect_timeout_s=3.0)

        with pytest.raises(RuntimeError, match="timed out"):
            env.start()

    def test_stop_is_a_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        env = driver.SSHEnvironment(host="example.com", user="me")
        env.start()
        env.stop()  # must not raise
