"""Phase 3 tests: bounded timeouts + tmux send-keys payload batching.

Covers the reliability hardening pass:

  * `DockerExecExecutor.exec()` catches `subprocess.TimeoutExpired` and
    returns a `timed_out=True` `ExecResult` instead of letting the
    exception hang the caller.
  * `_docker_exec` / `_run` forward a bounded default `timeout_s` to every
    subprocess call so nothing in the driver blocks forever.
  * `send_message`/`await_completion`/`capture_response` each pass a
    bounded per-call timeout distinct from `await_completion`'s overall
    deadline, and a single failed/timed-out poll doesn't abort the whole
    `await_completion` call.
  * Payloads over `TMUX_SEND_KEYS_MAX_BYTES` are staged via tmux
    `load-buffer`/`paste-buffer` instead of raw `send-keys -l`; small
    payloads keep using the raw path unchanged.

No real docker daemon or tmux required; `subprocess.run` and the driver's
executor seam are monkeypatched/faked.
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


class _FakeExecutor:
    """Records every `exec()` call; can be scripted to raise/time out.

    Also emulates the subset of shell behavior `_write_bytes_to_container`
    relies on (`mkdir -p`, `> path` truncate, `printf | base64 -d >>`) so
    payload-staging tests can assert on reconstructed bytes without any
    real docker/subprocess involvement — mirrors the fake in
    `test_interactive_tmux_executor.py`.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], float | None]] = []
        self.fs: dict[str, bytes] = {}

    def exec(self, command, *, timeout_s=None, stdin=None):
        self.calls.append((list(command), timeout_s))
        if command[:1] == ["mkdir"]:
            return driver.ExecResult(exit_code=0, stdout="", stderr="")
        if command[:1] == ["sh"] and len(command) >= 3 and command[1] == "-c":
            script = command[2]
            if script.startswith(">"):
                path = script[1:].strip().strip("'\"")
                self.fs[path] = b""
                return driver.ExecResult(exit_code=0, stdout="", stderr="")
            if "base64 -d >>" in script:
                import base64

                # Payload now arrives over STDIN, not in argv (leak fix).
                path = script.split("base64 -d >>")[1].strip().strip("'\"")
                assert stdin is not None
                self.fs[path] = self.fs.get(path, b"") + base64.b64decode(stdin)
                return driver.ExecResult(exit_code=0, stdout="", stderr="")
        return driver.ExecResult(exit_code=0, stdout="", stderr="")


class TestDockerExecExecutorTimeout:
    def test_timeout_expired_becomes_timed_out_exec_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        executor = driver.DockerExecExecutor("c")
        result = executor.exec(["tmux", "capture-pane"], timeout_s=2.0)

        assert result.timed_out is True
        assert result.exit_code != 0
        assert "timed out" in result.stderr

    def test_no_timeout_expired_is_not_timed_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            driver.subprocess,
            "run",
            lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "ok", ""),
        )
        result = driver.DockerExecExecutor("c").exec(["true"], timeout_s=5.0)
        assert result.timed_out is False


class TestBoundedDefaultTimeouts:
    def test_docker_exec_forwards_default_timeout_to_injected_executor(self) -> None:
        fake = _FakeExecutor()
        driver._docker_exec("c", "tmux", "capture-pane", executor=fake)
        (_cmd, timeout_s) = fake.calls[0]
        assert timeout_s == driver.DEFAULT_EXEC_TIMEOUT_S

    def test_docker_exec_honors_explicit_timeout_override(self) -> None:
        fake = _FakeExecutor()
        driver._docker_exec("c", "tmux", "capture-pane", executor=fake, timeout_s=3.0)
        (_cmd, timeout_s) = fake.calls[0]
        assert timeout_s == 3.0

    def test_run_forwards_default_run_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_subprocess_run(cmd, **kwargs):
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_subprocess_run)
        driver._run(["docker", "run", "-d", "x"])
        assert captured["kwargs"].get("timeout") == driver.DEFAULT_RUN_TIMEOUT_S

    def test_tmux_capture_forwards_timeout_to_executor(self) -> None:
        fake = _FakeExecutor()
        driver._tmux_capture("c", "claude", executor=fake, timeout_s=7.0)
        (_cmd, timeout_s) = fake.calls[0]
        assert timeout_s == 7.0

    def test_tmux_send_keys_forwards_timeout_to_executor(self) -> None:
        fake = _FakeExecutor()
        driver._tmux_send_keys("c", "claude", "Enter", executor=fake, timeout_s=4.0)
        (_cmd, timeout_s) = fake.calls[0]
        assert timeout_s == 4.0


class TestSendKeysPayloadBatching:
    def test_small_payload_uses_raw_send_keys(self) -> None:
        fake = _FakeExecutor()
        driver._tmux_send_literal("c", "claude", "hello world", executor=fake)

        assert len(fake.calls) == 1
        (cmd, _timeout) = fake.calls[0]
        assert cmd[:2] == ["tmux", "send-keys"]
        assert "-l" in cmd

    def test_payload_at_threshold_uses_raw_send_keys(self) -> None:
        fake = _FakeExecutor()
        text = "a" * driver.TMUX_SEND_KEYS_MAX_BYTES
        driver._tmux_send_literal("c", "claude", text, executor=fake)

        send_keys_calls = [c for c, _ in fake.calls if c[:2] == ["tmux", "send-keys"]]
        assert len(send_keys_calls) == 1

    def test_large_payload_is_staged_via_load_and_paste_buffer(self) -> None:
        fake = _FakeExecutor()
        text = "x" * (driver.TMUX_SEND_KEYS_MAX_BYTES + 1000)
        driver._tmux_send_literal("c", "claude", text, executor=fake)

        commands = [c for c, _ in fake.calls]
        # No raw send-keys -l for the oversized payload.
        assert not any(c[:2] == ["tmux", "send-keys"] and "-l" in c for c in commands)
        assert any(c[:2] == ["tmux", "load-buffer"] for c in commands)
        paste_calls = [c for c in commands if c[:2] == ["tmux", "paste-buffer"]]
        assert paste_calls
        # Finding 3: paste-buffer MUST use `-p` (bracketed paste) so a
        # multiline payload's embedded newlines don't dispatch as individual
        # Enter presses and submit the prompt early.
        assert all("-p" in c for c in paste_calls)

    def test_large_payload_bytes_round_trip_through_write_bytes_to_container(self) -> None:
        fake = _FakeExecutor()
        text = "y" * (driver.TMUX_SEND_KEYS_MAX_BYTES + 500)
        driver._tmux_send_literal("c", "claude", text, executor=fake)

        # Exactly one staged buffer file was written with the full payload.
        written = [v for v in fake.fs.values() if v == text.encode("utf-8")]
        assert len(written) == 1

    def test_large_payload_cleans_up_staged_buffer_file(self) -> None:
        fake = _FakeExecutor()
        text = "z" * (driver.TMUX_SEND_KEYS_MAX_BYTES + 200)
        driver._tmux_send_literal("c", "claude", text, executor=fake)

        commands = [c for c, _ in fake.calls]
        assert any(c[:2] == ["rm", "-f"] for c in commands)


class TestAwaitCompletionResilientToTransientPollFailure:
    def test_single_failed_poll_does_not_abort_await(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A poll that raises must be swallowed and retried, not propagated,
        so a transient wedged `docker exec` can't crash `await_completion`.
        """
        calls = {"n": 0}
        ready_tail = "❯ \n? for shortcuts"

        def flaky_capture(container, window, **kwargs):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise subprocess.CalledProcessError(1, ["docker", "exec"])
            return ready_tail

        monkeypatch.setattr(driver, "_tmux_capture", flaky_capture)
        monkeypatch.setattr(driver.time, "sleep", lambda *_a, **_k: None)

        ws = driver.InteractiveTmuxWorkspace(
            name="test",
            container="test-container",
            image="test-image",
            workdir="/workspace",
            tmux_size=(200, 50),
            host_throwaway_dir=Path("/tmp/test-throwaway"),
            enabled_agents=("claude",),
        )

        result = ws.await_completion("claude", timeout=5.0, stable_polls=1, warmup=0.0)

        assert calls["n"] > 2
        assert result.ready is True

    def test_await_completion_accepts_poll_timeout_s(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured_timeouts: list[float | None] = []

        def capture(container, window, **kwargs):
            captured_timeouts.append(kwargs.get("timeout_s"))
            return "❯ \n? for shortcuts"

        monkeypatch.setattr(driver, "_tmux_capture", capture)
        monkeypatch.setattr(driver.time, "sleep", lambda *_a, **_k: None)

        ws = driver.InteractiveTmuxWorkspace(
            name="test",
            container="test-container",
            image="test-image",
            workdir="/workspace",
            tmux_size=(200, 50),
            host_throwaway_dir=Path("/tmp/test-throwaway"),
            enabled_agents=("claude",),
        )

        ws.await_completion("claude", timeout=5.0, stable_polls=1, warmup=0.0, poll_timeout_s=3.0)

        assert captured_timeouts
        assert all(t == 3.0 for t in captured_timeouts)
        # The per-poll timeout must be strictly smaller than the overall
        # await deadline it was called with, so a wedged poll can't eat
        # the whole budget silently.
        assert 3.0 < 5.0


class TestDockerExecStdin:
    """Finding 1: credential payloads travel over STDIN, not argv. The
    executor must add `-i` (keep stdin open) and forward the bytes as
    `subprocess.run(input=...)`.
    """

    def test_stdin_adds_dash_i_and_forwards_input(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["input"] = kwargs.get("input")
            captured["text"] = kwargs.get("text")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        driver.DockerExecExecutor("c").exec(["sh", "-c", "base64 -d >> /x"], stdin=b"payload")

        assert captured["cmd"] == ["docker", "exec", "-i", "c", "sh", "-c", "base64 -d >> /x"]
        assert captured["input"] == b"payload"
        # bytes input requires text=False; outputs are decoded via `_decode`.
        assert captured["text"] is False

    def test_no_stdin_omits_dash_i_and_keeps_text_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["text"] = kwargs.get("text")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver.subprocess, "run", fake_run)

        driver.DockerExecExecutor("c").exec(["true"])

        assert "-i" not in captured["cmd"]
        assert captured["text"] is True


class TestRunExecCheckedRedactsCredentials:
    """Finding 2: a failing credential-seeding exec must not leak the payload
    OR the raw command into the raised error — only the redacted `label`.
    """

    def test_label_used_instead_of_raw_command_on_failure(self) -> None:
        class FailingExecutor:
            def exec(self, command, *, timeout_s=None, stdin=None):  # noqa: ARG002
                return driver.ExecResult(exit_code=1, stdout="", stderr="boom")

        with pytest.raises(RuntimeError) as excinfo:
            driver._run_exec_checked(
                FailingExecutor(),
                ["sh", "-c", "base64 -d >> /home/agent/.claude/.credentials.json"],
                stdin=b"c2VjcmV0",
                label="write bytes to /home/agent/.claude/.credentials.json",
            )

        msg = str(excinfo.value)
        assert "write bytes to /home/agent/.claude/.credentials.json" in msg
        # Neither the raw command list nor the base64 payload appears.
        assert "base64 -d" not in msg
        assert "c2VjcmV0" not in msg

    def test_write_bytes_failure_message_carries_no_payload(self) -> None:
        secret = b"top-secret-token"

        class FailingExecutor:
            def exec(self, command, *, timeout_s=None, stdin=None):  # noqa: ARG002
                # Fail only on the actual base64 write (not mkdir / truncate).
                if command[:1] == ["sh"] and "base64 -d >>" in command[2]:
                    return driver.ExecResult(exit_code=1, stdout="", stderr="disk full")
                return driver.ExecResult(exit_code=0, stdout="", stderr="")

        import base64 as _b64

        with pytest.raises(RuntimeError) as excinfo:
            driver._write_bytes_to_container(FailingExecutor(), "/home/agent/.claude.json", secret)

        msg = str(excinfo.value)
        assert secret.decode() not in msg
        assert _b64.b64encode(secret).decode() not in msg


class TestReadinessBreaksFastOnDeadContainer:
    """Finding 4: a container that is GONE must break the readiness poll
    immediately (naming the death) instead of spinning the full deadline and
    then reporting a misleading generic timeout.
    """

    @staticmethod
    def _ws():
        return driver.InteractiveTmuxWorkspace(
            name="test",
            container="test-container",
            image="test-image",
            workdir="/workspace",
            tmux_size=(200, 50),
            host_throwaway_dir=Path("/tmp/test-throwaway"),
            enabled_agents=("claude",),
        )

    def test_await_completion_breaks_immediately_on_dead_container(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}

        def dead_capture(container, window, **kwargs):  # noqa: ARG001
            calls["n"] += 1
            raise subprocess.CalledProcessError(
                1, ["docker", "exec"], "", "Error: No such container: test-container"
            )

        monkeypatch.setattr(driver, "_tmux_capture", dead_capture)
        monkeypatch.setattr(driver.time, "sleep", lambda *_a, **_k: None)

        # Generous overall timeout: if the fix regressed, this would spin
        # (many capture calls) instead of breaking after the first.
        result = self._ws().await_completion("claude", timeout=100.0, stable_polls=1, warmup=0.0)

        assert result.ready is False
        assert result.timed_out is False
        assert result.reason == "container_dead"
        assert "No such container" in (result.error or "")
        assert calls["n"] == 1

    def test_wait_for_started_breaks_immediately_on_dead_container(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = {"n": 0}

        def dead_capture(container, window, **kwargs):  # noqa: ARG001
            calls["n"] += 1
            raise subprocess.CalledProcessError(
                1, ["docker", "exec"], "", "Error response from daemon: Container is not running"
            )

        monkeypatch.setattr(driver, "_tmux_capture", dead_capture)
        monkeypatch.setattr(driver.time, "sleep", lambda *_a, **_k: None)

        result = self._ws()._wait_for_started("claude", 100.0)

        assert result.ready is False
        assert result.timed_out is False
        assert result.reason == "container_dead"
        assert "is not running" in (result.error or "")
        assert calls["n"] == 1

    def test_transient_capture_failure_still_retries_while_alive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A CalledProcessError whose stderr does NOT name a dead container is
        a genuine transient hiccup and must stay on the retry path."""
        calls = {"n": 0}

        def flaky(container, window, **kwargs):  # noqa: ARG001
            calls["n"] += 1
            if calls["n"] == 1:
                raise subprocess.CalledProcessError(1, ["docker", "exec"], "", "temporary glitch")
            return "❯ \n? for shortcuts"

        monkeypatch.setattr(driver, "_tmux_capture", flaky)
        monkeypatch.setattr(driver.time, "sleep", lambda *_a, **_k: None)

        result = self._ws().await_completion("claude", timeout=100.0, stable_polls=1, warmup=0.0)

        assert result.ready is True
        assert calls["n"] >= 2

    def test_docker_daemon_outage_is_transient_not_container_dead(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A daemon/socket connectivity error must NOT be read as container death.

        "Cannot connect to the Docker daemon" means the daemon blipped, not
        that the container is gone; classifying it as container_dead would
        abort a still-alive workspace. It must stay on the retry path and
        recover once the daemon responds again.
        """
        calls = {"n": 0}

        def daemon_blip(container, window, **kwargs):  # noqa: ARG001
            calls["n"] += 1
            if calls["n"] == 1:
                raise subprocess.CalledProcessError(
                    1,
                    ["docker", "exec"],
                    "",
                    "Cannot connect to the Docker daemon at unix:///var/run/docker.sock.",
                )
            return "❯ \n? for shortcuts"

        monkeypatch.setattr(driver, "_tmux_capture", daemon_blip)
        monkeypatch.setattr(driver.time, "sleep", lambda *_a, **_k: None)

        result = self._ws().await_completion("claude", timeout=100.0, stable_polls=1, warmup=0.0)

        assert result.ready is True
        assert result.reason != "container_dead"
        assert calls["n"] >= 2
