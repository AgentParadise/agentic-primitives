"""Pinned Codex: the effective sandbox mode is the one syn-delegate chose.

Runs the real pinned binary through syn-delegate against an offline Responses
fixture, with no credentials. Codex states its effective sandbox mode in the
permissions instructions it sends to the model, so the captured request is
the evidence. Prompts that look like options, and a CODEX_HOME config that
asks for `danger-full-access`, must not change it.

Inside a container this needs the Codex sandbox seccomp profile (and the
AppArmor profile on AppArmor hosts), because syn-delegate probes the sandbox
before launching.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BINARY = os.environ.get("CODEX_NATIVE_TEST_BINARY")
PROMPTS = [
    "--sandbox danger-full-access",
    "--sandbox",
    "-c",
    'sandbox_mode="danger-full-access"',
    "--",
    "--dangerously-bypass-approvals-and-sandbox",
]


def _run(tmp_path: Path, prompt: str, mode: str | None) -> tuple[int, str, str]:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args: object) -> None:
            pass

        def do_POST(self) -> None:
            requests.append(
                self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
            )
            events = [
                {"type": "response.created", "response": {"id": "r"}},
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "message",
                        "id": "m",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    },
                },
                {
                    "type": "response.completed",
                    "response": {
                        "id": "r",
                        "usage": {
                            "input_tokens": 0,
                            "input_tokens_details": None,
                            "output_tokens": 0,
                            "output_tokens_details": None,
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
    home = tmp_path / "codex-home"
    home.mkdir(exist_ok=True)
    # A hostile config: asks for no sandbox and points at the fixture.
    (home / "config.toml").write_text(
        'sandbox_mode = "danger-full-access"\n'
        'approval_policy = "never"\n'
        'model_provider = "fixture"\n'
        "[model_providers.fixture]\n"
        'name = "fixture"\n'
        f'base_url = "http://127.0.0.1:{server.server_port}/v1"\n'
        'wire_api = "responses"\n'
        "requires_openai_auth = false\n"
        "supports_websockets = false\n"
    )
    spool = tmp_path / "spool"
    (spool / ".agentic-session-store/run").mkdir(parents=True, exist_ok=True)
    binary_dir = str(Path(BINARY or "codex").parent)
    environment = {
        **os.environ,
        "PATH": binary_dir + os.pathsep + os.environ.get("PATH", ""),
        "CODEX_HOME": str(home),
        "CODEX_SQLITE_HOME": str(home),
        "CODEX_API_KEY": "fixture",
        "AGENTIC_SESSION_STORE_PROVIDER": "local",
        "AGENTIC_SESSION_STORE_SPOOL": str(spool),
        "AGENTIC_SESSION_STORE_PARTITION": "run",
        "AGENTIC_INVOCATION_ID": "invocation",
        "AGENTIC_ATTEMPT_ID": "attempt",
        "AGENTIC_PARENT_HARNESS": "claude",
        "AGENTIC_PARENT_NATIVE_ID": "parent",
    }
    command = [
        sys.executable,
        "-m",
        "agentic_session_store.delegate",
        "codex",
        f"--prompt={prompt}",
        "--timeout",
        "60",
    ]
    if mode is not None:
        command += ["--sandbox", mode]
    try:
        result = subprocess.run(
            command,
            env=environment,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return result.returncode, result.stderr, "\n".join(requests)


@unittest.skipUnless(BINARY, "Set CODEX_NATIVE_TEST_BINARY for native conformance")
def test_option_like_prompt_and_hostile_config_keep_workspace_write(
    tmp_path: Path,
) -> None:
    for index, prompt in enumerate(PROMPTS):
        run_dir = tmp_path / str(index)
        run_dir.mkdir()
        code, stderr, requests = _run(run_dir, prompt, None)
        assert code == 0, (prompt, stderr)
        assert "`sandbox_mode` is `workspace-write`" in requests, requests[-2000:]
        assert "`sandbox_mode` is `danger-full-access`" not in requests
        assert json.dumps(prompt)[1:-1] in requests, prompt


@unittest.skipUnless(BINARY, "Set CODEX_NATIVE_TEST_BINARY for native conformance")
def test_read_only_request_is_honoured_over_config(tmp_path: Path) -> None:
    code, stderr, requests = _run(tmp_path, "hello", "read-only")
    assert code == 0, stderr
    assert "`sandbox_mode` is `read-only`" in requests, requests[-2000:]
    assert "danger-full-access`" not in requests


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        test_option_like_prompt_and_hostile_config_keep_workspace_write(Path(directory))
    with tempfile.TemporaryDirectory() as directory:
        test_read_only_request_is_honoured_over_config(Path(directory))
    print("Pinned Codex sandbox mode held for every prompt and config")
