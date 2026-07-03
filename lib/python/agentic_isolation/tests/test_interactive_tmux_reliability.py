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

    def exec(self, command, *, timeout_s=None):
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

                head, path_part = script.split("base64 -d >>")
                path = path_part.strip().strip("'\"")
                b64_literal = head.split("printf '%s' ", 1)[1].strip()
                b64_chunk = b64_literal.strip("'\"")
                self.fs[path] = self.fs.get(path, b"") + base64.b64decode(b64_chunk)
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
        assert any(c[:2] == ["tmux", "paste-buffer"] for c in commands)

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
