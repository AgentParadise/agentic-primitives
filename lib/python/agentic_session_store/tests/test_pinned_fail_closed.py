"""Pinned Claude 2.1.281 and Codex 0.156.1 deny a child launch whose intent
cannot be recorded, offline and without credentials (syntropic137#1398).

Unguarded, both harnesses let the tool call proceed when a hook command cannot
start or exceeds its timeout. These cases install the real capture hooks and
make the recorder unavailable (no ``python3`` on PATH) or hang it (a
``python3`` that never exits), then check the child never ran and the parent
model received the generic denial.

Set CLAUDE_NATIVE_TEST_BINARY and/or CODEX_NATIVE_TEST_BINARY to opt in. Run
inside the pinned image with networking disabled.
"""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agentic_session_store.child_journal import ChildJournal
from agentic_session_store.hook_command import FAILURE_MESSAGE, WATCHDOG_SECONDS
from agentic_session_store.install_child_hooks import install

CLAUDE = os.environ.get("CLAUDE_NATIVE_TEST_BINARY")
CODEX = os.environ.get("CODEX_NATIVE_TEST_BINARY")
MODES = ("missing_interpreter", "hung_interpreter", "no_contract")
# Mutable so one case can request an agent type the harness rejects.
SUBAGENT_TYPE = ["general-purpose"]


def _path(root: Path, mode: str) -> str:
    """A PATH whose python3 is missing or hangs; everything else is real.

    ``no_contract`` keeps the real interpreter: the recorder runs but the
    session-store provider is absent from the hook environment.
    """
    directory = root / "bin"
    directory.mkdir()
    sleep = shutil.which("sleep")
    assert sleep is not None
    names = ["sleep", "cat", "git", "rg", "node"]
    if mode == "no_contract":
        names.append("python3")
    for name in names:
        found = shutil.which(name)
        if found:
            (directory / name).symlink_to(found)
    if mode == "hung_interpreter":
        shim = directory / "python3"
        shim.write_text(f"#!/bin/sh\nexec {sleep} 120\n")
        shim.chmod(0o755)
    return str(directory)


def _serve(reply):
    requests: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            events = reply(body, requests)
            data = "".join(
                "event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n"
                for e in events
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, requests


def _claude_reply(body, _requests):
    first = body["messages"][0]["content"]
    first = [{"text": first}] if isinstance(first, str) else first
    parent = any(b.get("text") == "FIXTURE_PARENT" for b in first)
    spawn = parent and not any(m["role"] == "assistant" for m in body["messages"])
    block = (
        {
            "type": "tool_use",
            "id": "fail-closed-call",
            "name": "Agent",
            "input": {},
        }
        if spawn
        else {"type": "text", "text": ""}
    )
    delta = (
        {
            "type": "input_json_delta",
            "partial_json": json.dumps(
                {
                    "description": "Fixture child",
                    "prompt": "FIXTURE_CHILD",
                    "subagent_type": SUBAGENT_TYPE[0],
                }
            ),
        }
        if spawn
        else {"type": "text_delta", "text": "done"}
    )
    return [
        {
            "type": "message_start",
            "message": {
                "id": "m",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 0},
            },
        },
        {"type": "content_block_start", "index": 0, "content_block": block},
        {"type": "content_block_delta", "index": 0, "delta": delta},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {
                "stop_reason": "tool_use" if spawn else "end_turn",
                "stop_sequence": None,
            },
            "usage": {"output_tokens": 1},
        },
        {"type": "message_stop"},
    ]


def _codex_reply(_body, requests):
    item = (
        {
            "type": "function_call",
            "call_id": "fail-closed-spawn",
            "namespace": "collaboration",
            "name": "spawn_agent",
            "arguments": json.dumps({"message": "FIXTURE_CHILD", "task_name": "child"}),
        }
        if len(requests) == 1
        else {
            "type": "message",
            "id": "msg",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "done"}],
        }
    )
    return [
        {"type": "response.created", "response": {"id": "r"}},
        {"type": "response.output_item.done", "item": item},
        {
            "type": "response.completed",
            "response": {
                "id": "r",
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            },
        },
    ]


def _capture_env(root: Path, mode: str = "") -> dict[str, str]:
    spool = root / "spool"
    journal = spool / ".agentic-session-store/run/children.sqlite"
    journal.parent.mkdir(parents=True)
    ChildJournal(journal)
    return {
        "AGENTIC_SESSION_STORE_PROVIDER": "none" if mode == "no_contract" else "local",
        "AGENTIC_SESSION_STORE_SPOOL": str(spool),
        "AGENTIC_SESSION_STORE_PARTITION": "run",
        "AGENTIC_INVOCATION_ID": "invocation",
        "AGENTIC_ATTEMPT_ID": "attempt",
    }


def _journal(root: Path) -> ChildJournal:
    return ChildJournal(
        root / "spool/.agentic-session-store/run/children.sqlite", read_only=True
    )


class PinnedFailClosed(unittest.TestCase):
    def _check_elapsed(self, mode: str, elapsed: float) -> None:
        if mode == "hung_interpreter":
            # The guard's watchdog decided, not the 30 s harness timeout.
            self.assertGreaterEqual(elapsed, WATCHDOG_SECONDS)

    @unittest.skipUnless(CLAUDE, "Set CLAUDE_NATIVE_TEST_BINARY")
    def test_claude_denies_unrecordable_launch(self):
        self.assertEqual(
            subprocess.check_output([CLAUDE, "--version"], text=True).strip(),
            "2.1.281 (Claude Code)",
        )
        for mode in MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                home = root / "home"
                settings = home / ".claude/settings.json"
                install(settings, harness="claude")
                server, requests = _serve(_claude_reply)
                env = {
                    **os.environ,
                    **_capture_env(root, mode),
                    "PATH": _path(root, mode),
                    "HOME": str(home),
                    "CLAUDE_CONFIG_DIR": str(home / ".claude"),
                    "ANTHROPIC_API_KEY": "fixture",
                    "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                }
                env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
                started = time.monotonic()
                try:
                    result = subprocess.run(
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
                self._check_elapsed(mode, time.monotonic() - started)
                prompts = json.dumps([r["messages"][0] for r in requests])
                self.assertFalse("FIXTURE_CHILD" in prompts, "child must never run")
                results = [
                    block
                    for r in requests
                    for m in r["messages"]
                    if isinstance(m["content"], list)
                    for block in m["content"]
                    if block.get("type") == "tool_result"
                ]
                self.assertTrue(results, "parent must see the denied tool call")
                self.assertIn(FAILURE_MESSAGE, json.dumps(results))
                # No interpreter ran, so no intent, binding or launch exists.
                self.assertEqual(_journal(root).page().changes, ())

    @unittest.skipUnless(CLAUDE, "Set CLAUDE_NATIVE_TEST_BINARY")
    def test_claude_rejected_spawn_is_a_distinct_failed_launch(self):
        """With the recorder available, a spawn the harness rejects (unknown
        agent type, PostToolUseFailure) is launch_failed, never launched."""
        SUBAGENT_TYPE[0] = "no-such-agent-type"
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                home = root / "home"
                settings = home / ".claude/settings.json"
                install(settings, harness="claude")
                server, _requests = _serve(_claude_reply)
                env = {
                    **os.environ,
                    **_capture_env(root),
                    "HOME": str(home),
                    "CLAUDE_CONFIG_DIR": str(home / ".claude"),
                    "ANTHROPIC_API_KEY": "fixture",
                    "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                }
                env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
                try:
                    result = subprocess.run(
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
                history = [
                    (c.intent.status, c.intent.child_native_id, c.intent.reason)
                    for c in _journal(root).page().changes
                ]
                self.assertEqual(
                    history,
                    [
                        ("pending", None, None),
                        ("launch_failed", None, "native_tool_failed"),
                    ],
                )
        finally:
            SUBAGENT_TYPE[0] = "general-purpose"

    @unittest.skipUnless(CODEX, "Set CODEX_NATIVE_TEST_BINARY")
    def test_codex_denies_unrecordable_launch(self):
        self.assertEqual(
            subprocess.check_output([CODEX, "--version"], text=True).strip(),
            "codex-cli 0.156.1",
        )
        for mode in MODES:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                home = root / "codex"
                home.mkdir()
                install(home / "config.toml")
                server, requests = _serve(_codex_reply)
                started = time.monotonic()
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
                            **os.environ,
                            **_capture_env(root, mode),
                            "PATH": _path(root, mode),
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
                self._check_elapsed(mode, time.monotonic() - started)
                # Parent spawn request plus the follow-up; no child request.
                self.assertEqual(len(requests), 2)
                self.assertIn(FAILURE_MESSAGE, json.dumps(requests[1]))
                self.assertFalse(list((home / "sessions").rglob("*.jsonl"))[1:])
                self.assertEqual(_journal(root).page().changes, ())


if __name__ == "__main__":
    unittest.main()
