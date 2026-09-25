"""Real pinned Codex spawning with an offline Responses fixture, no credentials."""

import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agentic_session_store.child_journal import ChildJournal
from agentic_session_store.install_child_hooks import install

BINARY = os.environ.get("CODEX_NATIVE_TEST_BINARY")


@unittest.skipUnless(BINARY, "Set CODEX_NATIVE_TEST_BINARY for native conformance")
def test_native_v2_spawn_registers_before_binding(tmp_path: Path, shell_context=False):
    assert (
        subprocess.check_output([BINARY, "--version"], text=True).strip()
        == "codex-cli 0.156.1"
    )
    home = tmp_path / "home"
    home.mkdir()
    install(home / "config.toml")
    spool = tmp_path / "spool"
    journal_path = spool / ".agentic-session-store/run/children.sqlite"
    journal_path.parent.mkdir(parents=True)
    ChildJournal(journal_path)
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append(1)
            item = (
                {
                    "type": "function_call",
                    "call_id": "native-spawn-1",
                    "namespace": "functions" if shell_context else "collaboration",
                    "name": "exec_command" if shell_context else "spawn_agent",
                    "arguments": json.dumps(
                        {"cmd": "printf '%s' \"$CODEX_THREAD_ID\" > parent-context.txt"}
                        if shell_context
                        else {"message": "Reply done", "task_name": "child"}
                    ),
                }
                if len(requests) == 1
                else {
                    "type": "message",
                    "id": "msg",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "done"}],
                }
            )
            events = [
                {"type": "response.created", "response": {"id": "r"}},
                {"type": "response.output_item.done", "item": item},
                {
                    "type": "response.completed",
                    "response": {
                        "id": "r",
                        "usage": {
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "total_tokens": 0,
                        },
                    },
                },
            ]
            body = "".join(
                "event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n"
                for e in events
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run(
            [
                BINARY,
                "exec",
                "--skip-git-repo-check",
                # Codex's own sandbox stays on. In a container this needs the
                # Codex sandbox seccomp profile (agentic_isolation).
                *(["--sandbox", "workspace-write"] if shell_context else []),
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
                "-c",
                'shell_environment_policy.inherit="all"',
                "Spawn a child.",
            ],
            env={
                **os.environ,
                "CODEX_HOME": str(home),
                "CODEX_SQLITE_HOME": str(home),
                "CODEX_API_KEY": "fixture",
                "AGENTIC_SESSION_STORE_PROVIDER": "local",
                "AGENTIC_SESSION_STORE_SPOOL": str(spool),
                "AGENTIC_SESSION_STORE_PARTITION": "run",
                "AGENTIC_INVOCATION_ID": "invocation",
                "AGENTIC_ATTEMPT_ID": "attempt",
            },
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=40,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        if shell_context:
            events = [json.loads(line) for line in result.stdout.splitlines()]
            native = next(
                e["thread_id"] for e in events if e.get("type") == "thread.started"
            )
            assert (tmp_path / "parent-context.txt").read_text() == native
            return
        changes = ChildJournal(journal_path).page().changes
        # Intent before launch; launched and bound on the spawn result;
        # completed when the child's turn fires SubagentStop.
        assert [c.intent.status for c in changes] == [
            "pending",
            "launched",
            "completed",
        ]
        assert changes[0].intent.child_native_id is None
        assert changes[1].intent.child_native_id == changes[2].intent.child_native_id
        bound = changes[1].intent
        assert bound.call.tool_call_id == "native-spawn-1"
        assert (
            bound.child_native_id
            and bound.child_native_id != bound.call.parent_native_id
        )
        assert len(requests) >= 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@unittest.skipUnless(BINARY, "Set CODEX_NATIVE_TEST_BINARY for native conformance")
def test_native_codex_shell_context(tmp_path: Path):
    test_native_v2_spawn_registers_before_binding(tmp_path, shell_context=True)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        test_native_v2_spawn_registers_before_binding(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        test_native_codex_shell_context(Path(directory))
    print("Pinned Codex child capture and shell context passed")
