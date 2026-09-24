"""Pinned Claude depth-three native capture with an offline Messages fixture."""

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

BINARY = os.environ.get("CLAUDE_NATIVE_TEST_BINARY")


@unittest.skipUnless(BINARY, "Set CLAUDE_NATIVE_TEST_BINARY for native conformance")
def test_native_claude_depth_three(tmp_path: Path, shell_context=False):
    assert (
        subprocess.check_output([BINARY, "--version"], text=True).strip()
        == "2.1.281 (Claude Code)"
    )
    root = tmp_path
    home = root / "home"
    home.mkdir()
    settings = home / ".claude/settings.json"
    install(settings, harness="claude")
    spool = root / "spool"
    journal_path = spool / ".agentic-session-store/run/children.sqlite"
    journal_path.parent.mkdir(parents=True)
    ChildJournal(journal_path)
    requests = []
    registered_before_child_request = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(req)
            agent = next(
                (
                    t["name"]
                    for t in req.get("tools", [])
                    if t["name"] in (("Bash",) if shell_context else ("Agent", "Task"))
                ),
                None,
            )
            first = req.get("messages", [{}])[0].get("content", [])
            prompt = next(
                (
                    b.get("text", "")
                    for b in first
                    if b.get("text", "").startswith("FIXTURE_DEPTH_")
                ),
                "",
            )
            depth = int(prompt.removeprefix("FIXTURE_DEPTH_")) if prompt else 99
            if depth in (1, 2, 3) and len(req.get("messages", [])) == 1:
                changes = ChildJournal(journal_path, read_only=True).page().changes
                registered_before_child_request.append(
                    any(
                        c.intent.call.tool_call_id == f"native-claude-call-{depth - 1}"
                        and c.intent.child_native_id is None
                        for c in changes
                    )
                )
            prior_call = any(
                m.get("role") == "assistant" for m in req.get("messages", [])
            )
            spawn = depth < (1 if shell_context else 3) and not prior_call and agent
            block = (
                {
                    "type": "tool_use",
                    "id": f"native-claude-call-{depth}",
                    "name": agent,
                    "input": {
                        "command": "printf '%s' \"$AGENTIC_PARENT_HARNESS:$AGENTIC_PARENT_NATIVE_ID\" > parent-context.txt"
                    }
                    if shell_context
                    else {
                        "description": "Fixture child",
                        "prompt": f"FIXTURE_DEPTH_{depth + 1}",
                        "subagent_type": "general-purpose",
                    },
                }
                if spawn
                else {"type": "text", "text": "CHILD_OK"}
            )
            msg = {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 0},
            }
            events = [
                {"type": "message_start", "message": msg},
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": dict(block, input={})
                    if spawn
                    else {"type": "text", "text": ""},
                },
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": json.dumps(block["input"]),
                    }
                    if spawn
                    else {"type": "text_delta", "text": "CHILD_OK"},
                },
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
            if req.get("stream"):
                body = "".join(
                    "event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n"
                    for e in events
                ).encode()
                kind = "text/event-stream"
            else:
                msg.update(
                    content=[block], stop_reason="tool_use" if spawn else "end_turn"
                )
                body = json.dumps(msg).encode()
                kind = "application/json"
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    env = {
        **os.environ,
        "HOME": str(home),
        "CLAUDE_CONFIG_DIR": str(home / ".claude"),
        "ANTHROPIC_API_KEY": "fixture",
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "AGENTIC_SESSION_STORE_PROVIDER": "local",
        "AGENTIC_SESSION_STORE_SPOOL": str(spool),
        "AGENTIC_SESSION_STORE_PARTITION": "run",
        "AGENTIC_INVOCATION_ID": "invocation",
        "AGENTIC_ATTEMPT_ID": "attempt",
    }
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    try:
        result = subprocess.run(
            [
                BINARY,
                "-p",
                "FIXTURE_DEPTH_0",
                "--model",
                "claude-sonnet-4-5",
                "--tools",
                "Bash" if shell_context else "Agent",
                "--allowedTools",
                "Bash" if shell_context else "Agent",
                "--settings",
                str(settings),
                "--setting-sources",
                "user",
                "--output-format",
                "json",
                "--max-turns",
                "4",
            ],
            env=env,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        output = json.loads(result.stdout)
        assert output["is_error"] is False
        if shell_context:
            assert (root / "parent-context.txt").read_text() == "claude:" + output[
                "session_id"
            ]
            return
        changes = ChildJournal(journal_path).page().changes
        assert len(changes) == 6
        assert registered_before_child_request == [True, True, True]
        bound = {
            c.intent.call.tool_call_id: c.intent
            for c in changes
            if c.intent.child_native_id
        }
        assert set(bound) == {f"native-claude-call-{d}" for d in range(3)}
        parent = output["session_id"]
        for depth in range(3):
            intent = bound[f"native-claude-call-{depth}"]
            assert intent.call.harness == "claude"
            assert intent.call.parent_native_id == parent
            assert intent.child_native_id != parent
            before = next(c for c in changes if c.intent.call == intent.call)
            assert before.intent.child_native_id is None
            parent = intent.child_native_id
        # Compare independently acquired native transcript headers against hooks.
        native = {}
        for path in (home / ".claude/projects").rglob("agent-*.jsonl"):
            for line in path.read_text().splitlines():
                row = json.loads(line)
                if row.get("agentId"):
                    native["agent-" + row["agentId"]] = row["sessionId"]
                    break
        assert set(native) == {i.child_native_id for i in bound.values()}
        assert set(native.values()) == {output["session_id"]}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@unittest.skipUnless(BINARY, "Set CLAUDE_NATIVE_TEST_BINARY for native conformance")
def test_native_claude_shell_context(tmp_path: Path):
    test_native_claude_depth_three(tmp_path, shell_context=True)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        test_native_claude_depth_three(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        test_native_claude_shell_context(Path(directory))
    print("Pinned Claude depth-three capture and shell context passed")
