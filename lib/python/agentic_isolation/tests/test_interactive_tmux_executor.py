"""Phase 2 tests: `CommandExecutor` seam + exec-based credential seeding.

Covers the docker-out-of-docker (DooD) fix: the driver used to stage
credentials into a host tempdir and bind-mount them into the container at
`docker run` time (`-v host:container`). That breaks when the driver itself
runs inside a container, because the *driver's* host paths aren't visible to
the sibling `docker run` on the outer host.

Phase 2 replaces that with: run the container WITHOUT credential mounts,
then push each credential file's bytes into the container over an injected
`CommandExecutor` (base64-chunked `docker exec` writes). These tests verify:

  * `ExecResult` / `CommandExecutor` / `DockerExecExecutor` shapes.
  * `_docker_exec` routes through an injected executor when given one, and
    constructs a default `DockerExecExecutor` when not.
  * `_write_bytes_to_container` / `_transfer_path_to_container` reconstruct
    file bytes and directory trees faithfully via a fake executor (no real
    docker daemon).
  * `start_workspace` no longer passes `-v` bind-mount flags to `docker run`,
    and instead transfers credential file bytes over the executor.

No real docker daemon or tmux is required; `subprocess.run` and the driver's
`_run`/`_docker_exec` seams are monkeypatched.
"""

from __future__ import annotations

import base64
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


class _FakeExecutor:
    """Records every `exec()` call; replays a scripted (exit_code) per call.

    Also incrementally "executes" `sh -c` file-write commands against an
    in-memory filesystem so directory/file transfer tests can assert on the
    reconstructed bytes without any real docker/subprocess involvement.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.fs: dict[str, bytes] = {}
        self.chowned: list[str] = []

    def exec(self, command, *, timeout_s=None):  # noqa: ARG002
        self.calls.append(list(command))
        # Emulate the subset of shell behavior the driver's helpers rely on:
        # `mkdir -p`, `> path` (truncate/create), `printf '%s' B64 | base64
        # -d >> path`, `chown ...`, `find ... chmod ...`.
        if command[:1] == ["mkdir"]:
            return driver.ExecResult(exit_code=0, stdout="", stderr="")
        if command[:1] == ["sh"] and len(command) >= 3 and command[1] == "-c":
            script = command[2]
            if script.startswith(">"):
                # `> 'path'` truncate/create.
                path = script[1:].strip()
                path = path.strip("'\"")
                self.fs[path] = b""
                return driver.ExecResult(exit_code=0, stdout="", stderr="")
            if "base64 -d >>" in script:
                # `printf '%s' 'B64CHUNK' | base64 -d >> 'path'`
                head, path_part = script.split("base64 -d >>")
                path = path_part.strip().strip("'\"")
                b64_literal = head.split("printf '%s' ", 1)[1].strip()
                b64_chunk = b64_literal.strip("'\"")
                self.fs[path] = self.fs.get(path, b"") + base64.b64decode(b64_chunk)
                return driver.ExecResult(exit_code=0, stdout="", stderr="")
            if "chown" in script:
                self.chowned.append(script)
                return driver.ExecResult(exit_code=0, stdout="", stderr="")
        return driver.ExecResult(exit_code=0, stdout="", stderr="")


class TestExecResultShape:
    def test_fields(self) -> None:
        result = driver.ExecResult(exit_code=0, stdout="out", stderr="err")
        assert result.exit_code == 0
        assert result.stdout == "out"
        assert result.stderr == "err"


class TestDockerExecExecutor:
    def test_exec_shells_out_via_docker_exec(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(cmd, 0, "hello\n", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        executor = driver.DockerExecExecutor("my-container")
        result = executor.exec(["echo", "hello"])

        assert captured["cmd"] == ["docker", "exec", "my-container", "echo", "hello"]
        assert result.exit_code == 0
        assert result.stdout == "hello\n"

    def test_nonzero_exit_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 7, "", "boom")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        executor = driver.DockerExecExecutor("c")
        result = executor.exec(["false"])

        assert result.exit_code == 7
        assert result.stderr == "boom"

    def test_timeout_s_forwarded_to_subprocess_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        driver.DockerExecExecutor("c").exec(["true"], timeout_s=5.0)

        assert captured["kwargs"].get("timeout") == 5.0


class TestDockerExecRoutesThroughExecutor:
    def test_default_constructs_docker_exec_executor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        constructed: list[str] = []
        real_cls = driver.DockerExecExecutor

        class RecordingExecutor(real_cls):
            def __init__(self, container):
                constructed.append(container)
                super().__init__(container)

        monkeypatch.setattr(driver, "DockerExecExecutor", RecordingExecutor)
        monkeypatch.setattr(
            driver.subprocess,
            "run",
            lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "", ""),
        )

        driver._docker_exec("some-container", "true")

        assert constructed == ["some-container"]

    def test_injected_executor_is_used_instead_of_default(self) -> None:
        fake = _FakeExecutor()
        driver._docker_exec("ignored-container", "mkdir", "-p", "/x", executor=fake)
        assert fake.calls == [["mkdir", "-p", "/x"]]

    def test_check_true_raises_on_nonzero_from_injected_executor(self) -> None:
        class FailingExecutor:
            def exec(self, command, *, timeout_s=None):
                return driver.ExecResult(exit_code=1, stdout="", stderr="nope")

        with pytest.raises(subprocess.CalledProcessError):
            driver._docker_exec("c", "false", executor=FailingExecutor())

    def test_check_false_swallows_nonzero(self) -> None:
        class FailingExecutor:
            def exec(self, command, *, timeout_s=None):
                return driver.ExecResult(exit_code=1, stdout="", stderr="nope")

        result = driver._docker_exec("c", "false", check=False, executor=FailingExecutor())
        assert result.returncode == 1


class TestWriteBytesToContainer:
    def test_small_payload_round_trips(self) -> None:
        fake = _FakeExecutor()
        driver._write_bytes_to_container(fake, "/home/agent/.credentials.json", b'{"token": "abc"}')
        assert fake.fs["/home/agent/.credentials.json"] == b'{"token": "abc"}'

    def test_mkdir_dash_p_called_for_parent(self) -> None:
        fake = _FakeExecutor()
        driver._write_bytes_to_container(fake, "/home/agent/.claude/deep/file.json", b"{}")
        assert ["mkdir", "-p", "/home/agent/.claude/deep"] in fake.calls

    def test_large_payload_is_chunked_and_reconstructed(self) -> None:
        fake = _FakeExecutor()
        payload = bytes(range(256)) * 200  # 51200 bytes, forces multiple chunks
        driver._write_bytes_to_container(fake, "/home/agent/.codex/auth.json", payload, chunk_size=64)
        assert fake.fs["/home/agent/.codex/auth.json"] == payload
        # More than one base64-chunk write call happened.
        b64_calls = [c for c in fake.calls if c[:1] == ["sh"] and "base64 -d >>" in c[2]]
        assert len(b64_calls) > 1


class TestTransferPathToContainer:
    def test_single_file_transferred(self, tmp_path: Path) -> None:
        src = tmp_path / "creds.json"
        src.write_text('{"a": 1}')
        fake = _FakeExecutor()

        driver._transfer_path_to_container(fake, src, "/home/agent/.claude.json")

        assert fake.fs["/home/agent/.claude.json"] == b'{"a": 1}'

    def test_directory_tree_transferred_preserving_relative_paths(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "codex-home"
        (src_dir / "sessions").mkdir(parents=True)
        (src_dir / "auth.json").write_text('{"auth": true}')
        (src_dir / "sessions" / "s1.json").write_text('{"session": 1}')
        fake = _FakeExecutor()

        driver._transfer_path_to_container(fake, src_dir, "/home/agent/.codex")

        assert fake.fs["/home/agent/.codex/auth.json"] == b'{"auth": true}'
        assert fake.fs["/home/agent/.codex/sessions/s1.json"] == b'{"session": 1}'


class TestSecureContainerPath:
    def test_file_chown_and_chmod_issued(self) -> None:
        fake = _FakeExecutor()
        driver._secure_container_path(fake, "/home/agent/.claude/.credentials.json", is_dir=False)
        assert any("chown 1000:1000" in c and "chmod 600" in c for c in fake.chowned)

    def test_directory_chown_recursive_and_find_chmod(self) -> None:
        fake = _FakeExecutor()
        driver._secure_container_path(fake, "/home/agent/.codex", is_dir=True)
        assert any("chown -R 1000:1000" in c and "find" in c for c in fake.chowned)


class TestStartWorkspaceNoLongerBindMounts:
    """`start_workspace` must not bind-mount credentials at `docker run` time;
    it transfers them into the running container over the executor instead.
    """

    @pytest.fixture
    def fake_claude_home(self, tmp_path: Path) -> Path:
        home = tmp_path / "home"
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / ".credentials.json").write_text('{"token": "tok"}')
        (home / ".claude.json").write_text('{"oauthAccount": {"email": "a@b.com"}}')
        return claude_dir

    def test_docker_run_has_no_dash_v_flags(
        self,
        fake_claude_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run_calls: list[list[str]] = []

        def fake_run(cmd, check=True, capture=True):  # noqa: ARG001
            run_calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver, "_run", fake_run)
        monkeypatch.setattr(
            driver.subprocess,
            "run",
            lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "", ""),
        )
        # Avoid launching real tmux/agents during bootstrap.
        monkeypatch.setattr(driver.InteractiveTmuxWorkspace, "_bootstrap_tmux_and_launch", lambda self, *a, **k: None)

        ws = driver.InteractiveTmuxWorkspace.start_workspace(
            name="noboundtest",
            host_auth={"claude": fake_claude_home},
        )

        docker_run_calls = [c for c in run_calls if c[:2] == ["docker", "run"]]
        assert len(docker_run_calls) == 1
        assert "-v" not in docker_run_calls[0]
        ws.stop()

    def test_credential_bytes_transferred_over_executor(
        self,
        fake_claude_home: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            driver,
            "_run",
            lambda cmd, check=True, capture=True: subprocess.CompletedProcess(cmd, 0, "", ""),
        )
        monkeypatch.setattr(driver.InteractiveTmuxWorkspace, "_bootstrap_tmux_and_launch", lambda self, *a, **k: None)

        fake = _FakeExecutor()
        monkeypatch.setattr(driver, "DockerExecExecutor", lambda container: fake)  # noqa: ARG005
        monkeypatch.setattr(
            driver.subprocess,
            "run",
            lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "", ""),
        )

        ws = driver.InteractiveTmuxWorkspace.start_workspace(
            name="transfertest",
            host_auth={"claude": fake_claude_home},
        )

        assert fake.fs["/home/agent/.claude/.credentials.json"] == b'{"token": "tok"}'
        assert b"oauthAccount" in fake.fs["/home/agent/.claude.json"]
        assert ws.executor is fake
        ws.stop()


class TestWorkspaceExecutorField:
    def test_defaults_to_docker_exec_executor_for_its_container(self) -> None:
        ws = driver.InteractiveTmuxWorkspace(
            name="test",
            container="test-container",
            image="test-image",
            workdir="/workspace",
            tmux_size=(200, 50),
            host_throwaway_dir=Path("/tmp/test-throwaway"),
            enabled_agents=("claude",),
        )
        assert isinstance(ws.executor, driver.DockerExecExecutor)
        assert ws.executor.target == "test-container"

    def test_explicit_executor_is_kept(self) -> None:
        fake = _FakeExecutor()
        ws = driver.InteractiveTmuxWorkspace(
            name="test",
            container="test-container",
            image="test-image",
            workdir="/workspace",
            tmux_size=(200, 50),
            host_throwaway_dir=Path("/tmp/test-throwaway"),
            enabled_agents=("claude",),
            executor=fake,
        )
        assert ws.executor is fake
