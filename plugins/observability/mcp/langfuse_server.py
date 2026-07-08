#!/usr/bin/env python3
"""MCP stdio server for agentic-primitives LangFuse learning-loop queries.

The server intentionally delegates to the `itmux langfuse-*` commands instead
of duplicating LangFuse API logic. That keeps credentials, endpoint handling,
self-host compatibility, and compact summary shapes in one proven place.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TIMEOUT_S = 60


def _text_schema(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "agentic_langfuse_trace_summary",
        "description": (
            "Return the compact learning-loop summary for one LangFuse trace. "
            "Provide either run_id or trace_id. Uses `itmux langfuse-trace "
            "--output summary` and can include trace-scoped scores."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": _text_schema("itmux run id; converted to deterministic trace id"),
                "trace_id": _text_schema("32-hex LangFuse/OpenTelemetry trace id"),
                "api": {
                    "type": "string",
                    "enum": ["legacy-trace", "observations-v2"],
                    "default": "legacy-trace",
                    "description": "LangFuse read API. legacy-trace is compatible with LangFuse v3 self-host.",
                },
                "include_scores": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include trace-scoped scores in the summary.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 100,
                    "description": "Maximum observation rows to request.",
                },
                "score_limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 20,
                    "description": "Maximum score rows to request when include_scores is true.",
                },
                "langfuse_base_url": _text_schema("Optional LangFuse origin or OTLP endpoint override."),
            },
            "oneOf": [{"required": ["run_id"]}, {"required": ["trace_id"]}],
            "additionalProperties": False,
        },
    },
    {
        "name": "agentic_langfuse_trace_discovery",
        "description": (
            "List recent LangFuse traces for agent discovery before drilling "
            "into a specific run. Supports harness/provider/model/environment filters."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                    "description": "Maximum trace rows to request.",
                },
                "page": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1,
                    "description": "1-based LangFuse page number.",
                },
                "harness": _text_schema("Optional harness filter, for example codex or claude."),
                "provider": _text_schema("Optional provider filter, for example openai or anthropic."),
                "model": _text_schema("Optional model filter."),
                "environment": _text_schema("Optional LangFuse environment filter."),
                "langfuse_base_url": _text_schema("Optional LangFuse origin or OTLP endpoint override."),
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "agentic_langfuse_scores",
        "description": "Read trace-scoped LangFuse scores for learning-loop feedback.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": _text_schema("itmux run id; converted to deterministic trace id"),
                "trace_id": _text_schema("32-hex LangFuse/OpenTelemetry trace id"),
                "score_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional score ids to fetch.",
                },
                "name": _text_schema("Optional score name filter."),
                "data_type": {
                    "type": "string",
                    "enum": ["boolean", "numeric", "categorical"],
                    "description": "Optional score data type filter.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 20,
                    "description": "Maximum score rows to request.",
                },
                "langfuse_base_url": _text_schema("Optional LangFuse origin or OTLP endpoint override."),
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "agentic_langfuse_score_feedback",
        "description": (
            "Create or update a trace-scoped LangFuse score so an evaluator or "
            "agent can write durable learning-loop feedback."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": _text_schema("itmux run id; converted to deterministic trace id"),
                "trace_id": _text_schema("32-hex LangFuse/OpenTelemetry trace id"),
                "score_id": _text_schema("Stable score id for idempotent retries."),
                "name": _text_schema("Score name, for example agentic.learning_loop_probe."),
                "value": {
                    "description": "Score value. Boolean, numeric, or categorical string depending on data_type."
                },
                "data_type": {
                    "type": "string",
                    "enum": ["boolean", "numeric", "categorical"],
                    "default": "boolean",
                    "description": "LangFuse score data type.",
                },
                "comment": _text_schema("Optional human or evaluator comment."),
                "metadata": {
                    "type": "object",
                    "description": "Optional JSON metadata object.",
                    "additionalProperties": True,
                },
                "langfuse_base_url": _text_schema("Optional LangFuse origin or OTLP endpoint override."),
            },
            "required": ["name", "value"],
            "anyOf": [{"required": ["run_id"]}, {"required": ["trace_id"]}],
            "additionalProperties": False,
        },
    },
]


class McpServer:
    def __init__(self, itmux_bin: str | None = None, timeout_s: int = DEFAULT_TIMEOUT_S):
        self.itmux_bin = itmux_bin or os.getenv("ITMUX_BIN") or shutil.which("itmux") or "itmux"
        self.timeout_s = timeout_s

    def serve(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                return
            response = self._handle_message(message)
            if response is not None:
                self._write_message(response)

    def _read_message(self) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = sys.stdin.buffer.readline()
            if line == b"":
                return None
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.decode("ascii", errors="replace").partition(":")
            headers[key.lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        if length <= 0:
            return None
        payload = sys.stdin.buffer.read(length)
        return json.loads(payload.decode("utf-8"))

    def _write_message(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii"))
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    def _handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}
        try:
            if method == "initialize":
                return self._result(
                    request_id,
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "agentic-primitives-langfuse",
                            "version": "0.3.0",
                        },
                    },
                )
            if method == "notifications/initialized":
                return None
            if method == "ping":
                return self._result(request_id, {})
            if method == "tools/list":
                return self._result(request_id, {"tools": TOOLS})
            if method == "tools/call":
                return self._call_tool(request_id, params)
            if request_id is None:
                return None
            return self._error(request_id, -32601, f"unsupported method: {method}")
        except Exception as exc:  # Keep MCP server alive; return actionable error.
            if request_id is None:
                return None
            return self._error(request_id, -32000, str(exc))

    def _call_tool(self, request_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "agentic_langfuse_trace_summary":
            return self._tool_result(request_id, self._langfuse_trace(args))
        if name == "agentic_langfuse_trace_discovery":
            return self._tool_result(request_id, self._langfuse_traces(args))
        if name == "agentic_langfuse_scores":
            return self._tool_result(request_id, self._langfuse_scores(args))
        if name == "agentic_langfuse_score_feedback":
            return self._tool_result(request_id, self._langfuse_score(args))
        return self._error(request_id, -32602, f"unknown tool: {name}")

    def _tool_result(self, request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return self._result(
            request_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result["payload"], indent=2, sort_keys=True),
                    }
                ],
                "isError": not result["ok"],
            },
        )

    def _langfuse_trace(self, args: dict[str, Any]) -> dict[str, Any]:
        cmd = [self.itmux_bin, "langfuse-trace", "--output", "summary"]
        self._add_trace_selector(cmd, args)
        self._add_option(cmd, "--api", args.get("api", "legacy-trace"))
        self._add_option(cmd, "--limit", args.get("limit"))
        if args.get("include_scores"):
            cmd.append("--include-scores")
            self._add_option(cmd, "--score-limit", args.get("score_limit"))
        self._add_option(cmd, "--langfuse-base-url", args.get("langfuse_base_url"))
        return self._run_itmux(cmd)

    def _langfuse_traces(self, args: dict[str, Any]) -> dict[str, Any]:
        cmd = [self.itmux_bin, "langfuse-traces"]
        for flag in ("limit", "page", "harness", "provider", "model", "environment"):
            self._add_option(cmd, f"--{flag.replace('_', '-')}", args.get(flag))
        self._add_option(cmd, "--langfuse-base-url", args.get("langfuse_base_url"))
        return self._run_itmux(cmd)

    def _langfuse_scores(self, args: dict[str, Any]) -> dict[str, Any]:
        cmd = [self.itmux_bin, "langfuse-scores"]
        self._add_optional_trace_selector(cmd, args)
        score_ids = args.get("score_ids")
        if score_ids:
            self._add_option(cmd, "--score-ids", ",".join(str(item) for item in score_ids))
        for flag in ("name", "data_type", "limit"):
            self._add_option(cmd, f"--{flag.replace('_', '-')}", args.get(flag))
        self._add_option(cmd, "--langfuse-base-url", args.get("langfuse_base_url"))
        return self._run_itmux(cmd)

    def _langfuse_score(self, args: dict[str, Any]) -> dict[str, Any]:
        cmd = [self.itmux_bin, "langfuse-score"]
        self._add_trace_selector(cmd, args)
        for flag in ("score_id", "name", "data_type", "comment"):
            self._add_option(cmd, f"--{flag.replace('_', '-')}", args.get(flag))
        self._add_option(cmd, "--value", args.get("value"))
        if args.get("metadata") is not None:
            self._add_option(cmd, "--metadata-json", json.dumps(args["metadata"], separators=(",", ":")))
        self._add_option(cmd, "--langfuse-base-url", args.get("langfuse_base_url"))
        return self._run_itmux(cmd)

    def _run_itmux(self, cmd: list[str]) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=self.timeout_s,
                check=False,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "payload": {
                    "ok": False,
                    "error": f"itmux binary not found: {self.itmux_bin}",
                    "hint": "Set ITMUX_BIN or put itmux on PATH.",
                },
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "payload": {
                    "ok": False,
                    "error": f"itmux command timed out after {self.timeout_s}s",
                    "stdout": exc.stdout,
                    "stderr": exc.stderr,
                },
            }
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        try:
            payload: Any = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            payload = {"raw_stdout": stdout}
        if completed.returncode != 0:
            if isinstance(payload, dict):
                payload.setdefault("ok", False)
                payload.setdefault("error", "itmux command failed")
                payload["exit_code"] = completed.returncode
                if stderr:
                    payload["stderr"] = stderr
            else:
                payload = {
                    "ok": False,
                    "error": "itmux command failed",
                    "exit_code": completed.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                }
            return {"ok": False, "payload": payload}
        return {"ok": True, "payload": payload}

    def _add_trace_selector(self, cmd: list[str], args: dict[str, Any]) -> None:
        run_id = args.get("run_id")
        trace_id = args.get("trace_id")
        if bool(run_id) == bool(trace_id):
            raise ValueError("provide exactly one of run_id or trace_id")
        self._add_option(cmd, "--run-id", run_id)
        self._add_option(cmd, "--trace-id", trace_id)

    def _add_optional_trace_selector(self, cmd: list[str], args: dict[str, Any]) -> None:
        run_id = args.get("run_id")
        trace_id = args.get("trace_id")
        if run_id and trace_id:
            raise ValueError("provide only one of run_id or trace_id")
        self._add_option(cmd, "--run-id", run_id)
        self._add_option(cmd, "--trace-id", trace_id)

    @staticmethod
    def _add_option(cmd: list[str], flag: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, bool):
            value = "true" if value else "false"
        cmd.extend([flag, str(value)])

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _frame(payload: dict[str, Any]) -> bytes:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data


def _read_framed_payloads(data: bytes) -> list[dict[str, Any]]:
    payloads = []
    offset = 0
    while offset < len(data):
        header_end = data.index(b"\r\n\r\n", offset)
        headers = data[offset:header_end].decode("ascii")
        length = 0
        for line in headers.split("\r\n"):
            key, _, value = line.partition(":")
            if key.lower() == "content-length":
                length = int(value.strip())
        start = header_end + 4
        payloads.append(json.loads(data[start : start + length].decode("utf-8")))
        offset = start + length
    return payloads


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "itmux"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "print(json.dumps({'ok': True, 'argv': sys.argv[1:]}))\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        proc = subprocess.run(
            [sys.executable, __file__, "--itmux-bin", str(fake)],
            input=(
                _frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
                + _frame({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
                + _frame(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "agentic_langfuse_trace_summary",
                            "arguments": {"run_id": "run-test", "include_scores": True},
                        },
                    }
                )
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            sys.stderr.buffer.write(proc.stderr)
            return proc.returncode
        payloads = _read_framed_payloads(proc.stdout)
        assert payloads[0]["result"]["serverInfo"]["name"] == "agentic-primitives-langfuse"
        tool_names = {tool["name"] for tool in payloads[1]["result"]["tools"]}
        assert "agentic_langfuse_trace_summary" in tool_names
        text = payloads[2]["result"]["content"][0]["text"]
        called = json.loads(text)["argv"]
        assert called[:3] == ["langfuse-trace", "--output", "summary"]
        assert "--run-id" in called and "run-test" in called
        assert "--include-scores" in called
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Agentic LangFuse MCP server")
    parser.add_argument("--itmux-bin", help="Path to itmux binary. Defaults to ITMUX_BIN or PATH.")
    parser.add_argument("--timeout-s", type=int, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    McpServer(itmux_bin=args.itmux_bin, timeout_s=args.timeout_s).serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
