#!/usr/bin/env python3
"""Run the runtime noise-guard probe with a local OTLP receiver."""

from __future__ import annotations

import argparse
import base64
import http.server
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import threading
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT = ROOT / "experiments/2026-07-08--langfuse--runtime-noise-guard"
RUNS = EXPERIMENT / "runs"
ITMUX = ROOT / "providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux"
TRANSCRIPT = (
    ROOT
    / "providers/workspaces/claude-cli/fixtures/recordings/v2.0.74_claude-sonnet-4-5_file-read.jsonl"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", choices=["suppressed", "forced"], required=True)
    args = parser.parse_args()
    run_dir = RUNS / args.condition
    run_dir.mkdir(parents=True, exist_ok=True)
    receiver = Receiver()
    receiver.start()
    try:
        env = os.environ.copy()
        env.update(
            {
                "TRACE_TO_LANGFUSE": "true",
                "LANGFUSE_PUBLIC_KEY": "pk-lf-" + "test-public",
                "LANGFUSE_SECRET_KEY": "sk-lf-" + "test-secret",
                "LANGFUSE_TRACING_ENVIRONMENT": "runtime-noise-guard",
            }
        )
        cmd = [
            str(ITMUX),
            "claude-transcript",
            "--transcript",
            str(TRANSCRIPT),
            "--run-id",
            f"runtime-noise-guard-{args.condition}",
            "--result-file",
            str(run_dir / "result.json"),
            "--observability-file",
            str(run_dir / "events.jsonl"),
            "--observability-syntropic-file",
            str(run_dir / "syntropic-events.jsonl"),
            "--observability-langfuse",
            "--langfuse-base-url",
            receiver.base_url,
            "--langfuse-project-id",
            "runtime-noise-project",
            "--langfuse-label",
            f"{args.condition} LangFuse fallback",
        ]
        if args.condition == "forced":
            cmd.append("--observability-langfuse-force")
        completed = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        (run_dir / "stdout.jsonl").write_text(completed.stdout)
        (run_dir / "stderr.txt").write_text(redact(completed.stderr))
        (run_dir / "command.json").write_text(
            json.dumps(
                {
                    "argv": cmd,
                    "returncode": completed.returncode,
                    "receiver_base_url": receiver.base_url,
                    "env": {
                        "TRACE_TO_LANGFUSE": env["TRACE_TO_LANGFUSE"],
                        "LANGFUSE_PUBLIC_KEY": "pk-lf-REDACTED",
                        "LANGFUSE_SECRET_KEY": "sk-lf-REDACTED",
                        "LANGFUSE_TRACING_ENVIRONMENT": env["LANGFUSE_TRACING_ENVIRONMENT"],
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        time.sleep(0.2)
        (run_dir / "receiver.json").write_text(
            json.dumps(receiver.snapshot(), indent=2, sort_keys=True)
        )
        return completed.returncode
    finally:
        receiver.stop()


class Receiver:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.httpd: socketserver.TCPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self.httpd is None:
            raise RuntimeError("receiver not started")
        host, port = self.httpd.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        receiver = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                receiver.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": redact_headers(dict(self.headers)),
                        "body_len": len(body),
                        "body_prefix_b64": base64.b64encode(body[:96]).decode("ascii"),
                    }
                )
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"OK")

            def log_message(self, *_args: object) -> None:
                return

        self.httpd = socketserver.TCPServer(("127.0.0.1", free_port()), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)

    def snapshot(self) -> dict[str, Any]:
        return {"request_count": len(self.requests), "requests": self.requests}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    out = {}
    for key, value in headers.items():
        if key.lower() == "authorization":
            out[key] = "Basic [REDACTED]"
        else:
            out[key] = redact(value)
    return out


def redact(value: str) -> str:
    return (
        value.replace("pk-lf-" + "test-public", "pk-lf-REDACTED")
        .replace("sk-lf-" + "test-secret", "sk-lf-REDACTED")
    )


if __name__ == "__main__":
    raise SystemExit(main())
