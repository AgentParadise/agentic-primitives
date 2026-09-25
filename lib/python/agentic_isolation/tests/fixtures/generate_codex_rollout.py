"""Regenerate codex_rollout_0.156.1.jsonl from the REAL pinned codex binary, offline.

Usage: uv run python generate_codex_rollout.py <codex-0.156.1 binary> <out.jsonl>

A local Responses fixture server returns: reasoning (SECRET_REASONING*), an assistant
message, a shell call printing TOOL_OUTPUT_SECRET, then FINAL_ANSWER. No credentials.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BINARY = sys.argv[1]
OUT = sys.argv[2]
reqs = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        reqs.append(1)
        if len(reqs) == 1:
            items = [
                {
                    "type": "reasoning",
                    "id": "rs",
                    "summary": [{"type": "summary_text", "text": "SECRET_REASONING"}],
                    "content": [{"type": "reasoning_text", "text": "SECRET_REASONING_RAW"}],
                },
                {
                    "type": "message",
                    "id": "m0",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Running a command."}],
                },
                {
                    "type": "function_call",
                    "call_id": "c1",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": "printf TOOL_OUTPUT_SECRET"}),
                },
            ]
        else:
            items = [
                {
                    "type": "message",
                    "id": "m1",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "FINAL_ANSWER"}],
                }
            ]
        ev = [{"type": "response.created", "response": {"id": "r"}}]
        ev += [{"type": "response.output_item.done", "item": i} for i in items]
        ev += [
            {
                "type": "response.completed",
                "response": {
                    "id": "r",
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                },
            }
        ]
        body = "".join(
            "event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n" for e in ev
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


s = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=s.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory() as t:
    home = pathlib.Path(t) / "home"
    home.mkdir()
    work = pathlib.Path(t) / "w"
    work.mkdir()
    r = subprocess.run(
        [
            BINARY,
            "exec",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
            "--json",
            "-c",
            'model_provider="fixture"',
            "-c",
            "model_providers.fixture={"
            'name="fixture",'
            f'base_url="http://127.0.0.1:{s.server_port}/v1",'
            'wire_api="responses",requires_openai_auth=false,supports_websockets=false}',
            "HUMAN_PROMPT please run it",
        ],
        env={
            **os.environ,
            "CODEX_HOME": str(home),
            "CODEX_SQLITE_HOME": str(home),
            "CODEX_API_KEY": "fixture",
        },
        cwd=work,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    print("rc", r.returncode, r.stderr[-500:])
    files = sorted(home.glob("sessions/**/rollout-*.jsonl"))
    print(files)
    pathlib.Path(OUT).write_bytes(files[0].read_bytes())
s.shutdown()
