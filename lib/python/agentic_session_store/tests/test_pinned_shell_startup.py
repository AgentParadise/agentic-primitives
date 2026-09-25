"""A shell startup file that preempts the guard, against pinned Codex 0.156.1.

Codex runs hooks with the passwd shell and ``-c`` (bash in the workspace image;
verified: ``$SHELL`` does not select it). Bash reads ``$BASH_ENV`` before the
hook command, so a file there that exits or hangs means the guard never runs
and Codex launches the child. No hook can prevent that, so it is a checked
precondition: ``hook_probe`` fails in that environment (session-store init
refuses readiness) and syn-delegate refuses to start a delegate there.

This module first reproduces the hazard (the child launches, nothing is
recorded), then shows both checks catch it. zsh is not in the image; the zsh
``.zshenv`` equivalent is covered by tests/test_hook_probe.py where zsh exists.

Set CODEX_NATIVE_TEST_BINARY to opt in. Run inside the pinned image with
networking disabled and the Codex sandbox seccomp profile (for syn-delegate).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agentic_session_store.child_journal import ChildJournal
from agentic_session_store.hook_command import HookHarness
from agentic_session_store.hook_probe import CaptureProbeError, probe_guard
from agentic_session_store.install_child_hooks import install
from tests.test_pinned_fail_closed import _capture_env, _codex_reply, _journal, _serve

CODEX = os.environ.get("CODEX_NATIVE_TEST_BINARY")


@unittest.skipUnless(CODEX, "Set CODEX_NATIVE_TEST_BINARY")
class PinnedShellStartup(unittest.TestCase):
    def _env(self, root: Path, startup: str | None) -> dict[str, str]:
        if not (root / "spool").exists():
            _capture_env(root)
        env = {
            **os.environ,
            "AGENTIC_SESSION_STORE_PROVIDER": "local",
            "AGENTIC_SESSION_STORE_SPOOL": str(root / "spool"),
            "AGENTIC_SESSION_STORE_PARTITION": "run",
            "AGENTIC_INVOCATION_ID": "invocation",
            "AGENTIC_ATTEMPT_ID": "attempt",
        }
        if startup is None:
            env.pop("BASH_ENV", None)
        else:
            rc = root / "bash_env"
            rc.write_text(startup + "\n")
            env["BASH_ENV"] = str(rc)
        return env

    def test_bash_env_exit_fails_open_natively_and_is_caught(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "codex"
            home.mkdir()
            install(home / "config.toml")
            env = self._env(root, "exit 0")
            server, requests = _serve(_codex_reply)
            try:
                result = subprocess.run(
                    [
                        CODEX,
                        "exec",
                        "--skip-git-repo-check",
                        "--json",
                        "-c",
                        'model_provider="fixture"',
                        "-c",
                        'model_providers.fixture={name="fixture",base_url="http://127.0.0.1:'
                        + str(server.server_port)
                        + '/v1",wire_api="responses",requires_openai_auth=false,supports_websockets=false}',
                        "-c",
                        "features.multi_agent=true",
                        "-c",
                        "features.multi_agent_v2=true",
                        "Spawn a child.",
                    ],
                    env={
                        **env,
                        "CODEX_HOME": str(home),
                        "CODEX_SQLITE_HOME": str(home),
                        "CODEX_API_KEY": "fixture",
                    },
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            finally:
                server.shutdown()
                server.server_close()
            self.assertEqual(result.returncode, 0, result.stderr)
            # The hazard: the guard never ran, the child launched unrecorded.
            self.assertGreaterEqual(len(requests), 3, "child should have run")
            self.assertEqual(_journal(root).page().changes, ())
            # The precondition check catches exactly this environment.
            with self.assertRaises(CaptureProbeError):
                probe_guard(HookHarness.CODEX, env)

    def test_probe_passes_clean_and_fails_on_hanging_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            probe_guard(HookHarness.CODEX, self._env(root, None))
            probe_guard(HookHarness.CLAUDE, self._env(root, None))
            with self.assertRaises(CaptureProbeError):
                probe_guard(HookHarness.CODEX, self._env(root, "sleep 60"), timeout=5)

    def test_syn_delegate_refuses_when_hooks_cannot_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {
                **self._env(root, "exit 0"),
                "AGENTIC_INVOCATION_ID": "invocation",
                "AGENTIC_ATTEMPT_ID": "attempt",
                "AGENTIC_PARENT_HARNESS": "claude",
                "AGENTIC_PARENT_NATIVE_ID": "parent",
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agentic_session_store.delegate",
                    "codex",
                    "--prompt",
                    "never runs",
                ],
                env=env,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            self.assertEqual(result.returncode, 70, result.stderr)
            intent = (
                ChildJournal(root / "spool/.agentic-session-store/run/children.sqlite")
                .page()
                .changes[-1]
                .intent
            )
            self.assertEqual(
                (intent.status, intent.reason),
                ("launch_failed", "capture_hook_unreachable"),
            )
            self.assertNotIn("thread.started", json.dumps(result.stdout))


if __name__ == "__main__":
    unittest.main()
