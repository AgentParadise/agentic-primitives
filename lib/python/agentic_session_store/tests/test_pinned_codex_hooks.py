"""Offline trust conformance against the workspace's real Codex 0.156.1 binary.

Set CODEX_NATIVE_TEST_BINARY to opt in. No credentials, model calls or network
are required. Run this module directly with Python inside the pinned image.
"""

import json
import os
import selectors
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from agentic_session_store.codex_hook_config import HOOK_COMMAND
from agentic_session_store.install_child_hooks import install

BINARY = os.environ.get("CODEX_NATIVE_TEST_BINARY")


def request(process, identifier, method, params):
    process.stdin.write(
        json.dumps({"id": identifier, "method": method, "params": params}) + "\n"
    )
    process.stdin.flush()
    deadline = time.monotonic() + 20
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if not selector.select(max(0, deadline - time.monotonic())):
                break
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("Pinned app-server exited before replying")
            message = json.loads(line)
            if message.get("id") == identifier:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message["result"]
    raise TimeoutError(method)


@unittest.skipUnless(
    BINARY, "Set CODEX_NATIVE_TEST_BINARY for pinned runtime conformance"
)
class PinnedCodexHooks(unittest.TestCase):
    def test_only_installed_capture_handlers_are_trusted(self):
        version = subprocess.check_output([BINARY, "--version"], text=True).strip()
        self.assertEqual(version, "codex-cli 0.156.1")
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "config.toml"
            config.write_text(
                '[[hooks.PreToolUse]]\nmatcher="Bash"\n'
                '[[hooks.PreToolUse.hooks]]\ntype="command"\ncommand="unrelated-hook"\n'
            )
            install(config)
            self.assertFalse(install(config))
            process = subprocess.Popen(
                [BINARY, "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                env={**os.environ, "CODEX_HOME": directory},
                cwd=directory,
            )
            try:
                request(
                    process,
                    1,
                    "initialize",
                    {
                        "clientInfo": {"name": "capture-conformance", "version": "1"},
                        "capabilities": {"experimentalApi": True},
                    },
                )
                result = request(process, 2, "hooks/list", {"cwds": [directory]})
                entries = result["data"][0]
                self.assertEqual(entries["errors"], [])
                capture = [
                    hook for hook in entries["hooks"] if hook["command"] == HOOK_COMMAND
                ]
                self.assertEqual(
                    {hook["eventName"] for hook in capture},
                    {"preToolUse", "postToolUse"},
                )
                self.assertEqual(len(capture), 2)
                for hook in capture:
                    self.assertEqual(hook["trustStatus"], "trusted")
                    self.assertTrue(hook["enabled"])
                    self.assertFalse(hook["async"])
                unrelated = [
                    hook
                    for hook in entries["hooks"]
                    if hook["command"] == "unrelated-hook"
                ]
                self.assertEqual(len(unrelated), 1)
                self.assertEqual(unrelated[0]["trustStatus"], "untrusted")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process.stdin.close()
                process.stdout.close()


if __name__ == "__main__":
    unittest.main()
