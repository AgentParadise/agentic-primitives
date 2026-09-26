"""Shell startup files cannot preempt the capture guard, against pinned
Claude Code 2.1.281 and Codex 0.156.1 (syntropic137#1398).

Codex runs hooks with the passwd shell and ``-c`` (``/bin/bash -c`` in the
image); Claude runs ``/bin/sh -c``. A non-interactive ``bash -c`` reads only
``$BASH_ENV``; ``sh -c`` reads ``$ENV`` only when interactive. Hooks inherit
the harness process environment, which the agent cannot change after launch,
so the image's harness launch wrappers, the entrypoint and syn-delegate start
every harness with both unset, and the probe rejects an agent-modifiable one.

This module:

* reproduces the hazard the variables create (Codex with an agent-writable
  ``BASH_ENV`` that exits launches the child with nothing recorded) and shows
  the probe rejects that environment;
* with both variables unset (what every harness gets), passes the probe, then
  rewrites every agent-writable startup file to log its reader, export a
  poisoned ``BASH_ENV``/``ENV`` and ``exit 0``, and spawns a native child
  directly through each harness: the child is recorded (pending, then
  launched) and no hook shell read any of them.

Measured, not assumed: Codex 0.156.1 itself starts a login ``bash -lc`` at
session start to snapshot the user's shell for its shell tool, and that reads
``~/.bash_profile`` and ``~/.bashrc``. Its hooks do not use that snapshot:
variables exported there never reach a hook shell. The assertion is therefore
about hook shells (identified by the guard's command line), not every process.

Set CLAUDE_NATIVE_TEST_BINARY and/or CODEX_NATIVE_TEST_BINARY to opt in. Run
inside the pinned image with networking disabled.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from agentic_session_store.hook_command import HookHarness
from agentic_session_store.hook_probe import (
    SHELL_STARTUP_VARIABLES,
    CaptureProbeError,
    probe_guard,
)
from agentic_session_store.install_child_hooks import install
from tests.test_pinned_fail_closed import (
    _capture_env,
    _claude_reply,
    _codex_reply,
    _journal,
    _serve,
)

CLAUDE = os.environ.get("CLAUDE_NATIVE_TEST_BINARY")
CODEX = os.environ.get("CODEX_NATIVE_TEST_BINARY")

HOME_STARTUP_FILES = (
    ".bashrc",
    ".bash_profile",
    ".bash_login",
    ".bash_logout",
    ".profile",
    ".shrc",
    ".kshrc",
    ".zshenv",
    ".zprofile",
    ".zshrc",
    ".zlogin",
)
SYSTEM_STARTUP_FILES = (
    "/etc/profile",
    "/etc/bash.bashrc",
    "/etc/environment",
    "/etc/zsh/zshenv",
    "/etc/zshenv",
)


def _clean_env(root: Path, home: Path) -> dict[str, str]:
    env = {**os.environ, **_capture_env(root), "HOME": str(home)}
    for name in SHELL_STARTUP_VARIABLES:
        env.pop(name, None)
    return env


def _real_binary(binary: str) -> str:
    """The binary behind the image's harness launch wrapper, if there is one."""
    with open(binary, "rb") as source:
        head = source.read(4096)
    if not head.startswith(b"#!/bin/sh"):
        return binary
    for line in head.decode().splitlines():
        if line.startswith("exec "):
            return line.split()[1]
    return binary


def _poison_startup_files(home: Path, markers: Path) -> list[Path]:
    """Every startup file this user can write logs its reader, exports a
    poisoned BASH_ENV/ENV and exits 0."""
    markers.mkdir()
    log = markers / "readers.log"
    evil = markers / "evil.sh"
    reader = 'tr "\\0" " " < /proc/$$/cmdline'
    evil.write_text(f'echo "EVIL: $({reader})" >> {log}\nexit 0\n')
    targets = [home / name for name in HOME_STARTUP_FILES]
    system = [Path(p) for p in SYSTEM_STARTUP_FILES]
    profile_d = Path("/etc/profile.d")
    if profile_d.is_dir():
        system += sorted(profile_d.iterdir())
        if os.access(profile_d, os.W_OK):
            targets.append(profile_d / "zz-agent.sh")
    targets += [path for path in system if path.exists() and os.access(path, os.W_OK)]
    for path in targets:
        path.write_text(
            f'echo "{path.name}: $({reader})" >> {log}\n'
            f"export BASH_ENV={evil} ENV={evil}\nexit 0\n"
        )
    return targets


def _codex(home: Path, env: dict[str, str], port: int, cwd: Path, binary=None):
    return subprocess.run(
        [
            binary or CODEX,
            "exec",
            "--skip-git-repo-check",
            "--json",
            "-c",
            'model_provider="fixture"',
            "-c",
            'model_providers.fixture={name="fixture",base_url="http://127.0.0.1:'
            + str(port)
            + '/v1",wire_api="responses",requires_openai_auth=false,supports_websockets=false}',
            "-c",
            "features.multi_agent=true",
            "-c",
            "features.multi_agent_v2=true",
            "Spawn a child.",
        ],
        env={
            **env,
            "CODEX_HOME": str(home / ".codex"),
            "CODEX_SQLITE_HOME": str(home / ".codex"),
            "CODEX_API_KEY": "fixture",
        },
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _claude(home: Path, env: dict[str, str], port: int, cwd: Path):
    settings = home / ".claude/settings.json"
    env = {
        **env,
        "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        "ANTHROPIC_API_KEY": "fixture",
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    return subprocess.run(
        [
            CLAUDE,
            "-p",
            "FIXTURE_PARENT",
            "--model",
            "claude-sonnet-4-5",
            "--tools",
            "Agent",
            "--allowedTools",
            "Agent",
            "--settings",
            str(settings),
            "--setting-sources",
            "user",
            "--output-format",
            "json",
            "--max-turns",
            "3",
        ],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


class PinnedShellStartup(unittest.TestCase):
    @unittest.skipUnless(CODEX, "Set CODEX_NATIVE_TEST_BINARY")
    def test_agent_writable_bash_env_is_the_hazard_and_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / ".codex").mkdir(parents=True)
            install(home / ".codex/config.toml")
            env = _clean_env(root, home)
            rc = root / "bash_env"
            rc.write_text("exit 0\n")
            env["BASH_ENV"] = str(rc)
            server, requests = _serve(_codex_reply)
            try:
                # The unwrapped binary: the image wrapper would clear BASH_ENV.
                result = _codex(
                    home, env, server.server_port, root, _real_binary(CODEX)
                )
            finally:
                server.shutdown()
                server.server_close()
            self.assertEqual(result.returncode, 0, result.stderr)
            # The guard never ran: the child launched with nothing recorded.
            self.assertGreaterEqual(len(requests), 3, "child should have run")
            self.assertEqual(_journal(root).page().changes, ())
            with self.assertRaises(CaptureProbeError):
                probe_guard(HookHarness.CODEX, env)

    def _poisoned_spawn(self, harness: HookHarness, spawn, reply) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            home.mkdir()
            if harness is HookHarness.CODEX:
                (home / ".codex").mkdir()
                install(home / ".codex/config.toml")
            else:
                install(home / ".claude/settings.json", harness="claude")
            env = _clean_env(root, home)
            probe_guard(harness, env)
            poisoned = _poison_startup_files(home, root / "markers")
            self.assertTrue(poisoned)
            server, _requests = _serve(reply)
            try:
                result = spawn(home, env, server.server_port, root)
            finally:
                server.shutdown()
                server.server_close()
            self.assertEqual(result.returncode, 0, result.stderr)
            log = root / "markers/readers.log"
            readers = log.read_text() if log.exists() else ""
            self.assertNotIn("agentic_session_store.child_hook", readers, readers)
            statuses = [c.intent.status for c in _journal(root).page().changes]
            self.assertEqual(statuses[:2], ["pending", "launched"], statuses)

    @unittest.skipUnless(CODEX, "Set CODEX_NATIVE_TEST_BINARY")
    def test_codex_hooks_read_no_startup_file(self):
        self._poisoned_spawn(HookHarness.CODEX, _codex, _codex_reply)

    @unittest.skipUnless(CLAUDE, "Set CLAUDE_NATIVE_TEST_BINARY")
    def test_claude_hooks_read_no_startup_file(self):
        self._poisoned_spawn(HookHarness.CLAUDE, _claude, _claude_reply)


class PinnedLaunchWrapper(unittest.TestCase):
    @unittest.skipUnless(CODEX, "Set CODEX_NATIVE_TEST_BINARY")
    def test_wrapper_clears_bash_env_so_the_spawn_is_recorded(self):
        """Through the image wrapper, the same agent-writable BASH_ENV that
        defeats the unwrapped binary never reaches a hook."""
        if _real_binary(CODEX) == CODEX:
            self.skipTest("binary is not behind the image launch wrapper")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            (home / ".codex").mkdir(parents=True)
            install(home / ".codex/config.toml")
            env = _clean_env(root, home)
            rc = root / "bash_env"
            rc.write_text("exit 0\n")
            env["BASH_ENV"] = str(rc)
            server, _requests = _serve(_codex_reply)
            try:
                result = _codex(home, env, server.server_port, root)
            finally:
                server.shutdown()
                server.server_close()
            self.assertEqual(result.returncode, 0, result.stderr)
            statuses = [c.intent.status for c in _journal(root).page().changes]
            self.assertEqual(statuses[:2], ["pending", "launched"], statuses)


if __name__ == "__main__":
    unittest.main()
