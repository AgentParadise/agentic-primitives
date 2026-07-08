#!/usr/bin/env python3
"""MCP stdio server for agentic-primitives LangFuse learning-loop queries.

The server intentionally delegates to the `itmux langfuse-*` commands instead
of duplicating LangFuse API logic. That keeps credentials, endpoint handling,
self-host compatibility, and compact summary shapes in one proven place.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
from urllib import error, parse, request


PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TIMEOUT_S = 60
REDACTION = "[REDACTED]"
SECRET_PATTERNS = [
    re.compile(r"sk-lf-[A-Za-z0-9._-]+"),
    re.compile(r"pk-lf-[A-Za-z0-9._-]+"),
    re.compile(r"(?i)(authorization:\s*(?:basic|bearer)\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:LANGFUSE_SECRET_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN)=)[^\s]+"),
]


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
            "oneOf": [{"required": ["run_id"]}, {"required": ["trace_id"]}],
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
        args = {**args}
        args.setdefault("data_type", "boolean")
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
            fallback = self._run_direct_langfuse(cmd[1:])
            return {
                "ok": bool(fallback.get("ok")),
                "payload": {
                    "itmux_error": f"itmux binary not found: {self.itmux_bin}",
                    "fallback": "direct-langfuse",
                    **fallback,
                }
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "ok": False,
                "payload": {
                    "ok": False,
                    "error": f"itmux command timed out after {self.timeout_s}s",
                    "stdout": _redact(exc.stdout),
                    "stderr": _redact(exc.stderr),
                },
            }
        stdout = _redact(completed.stdout.strip())
        stderr = _redact(completed.stderr.strip())
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

    def _run_direct_langfuse(self, args: list[str]) -> dict[str, Any]:
        command = args[0] if args else ""
        parsed = _parse_cli_args(args[1:])
        try:
            if command == "langfuse-trace":
                return self._direct_langfuse_trace(parsed)
            if command == "langfuse-traces":
                return self._direct_langfuse_traces(parsed)
            if command == "langfuse-scores":
                return self._direct_langfuse_scores(parsed)
            if command == "langfuse-score":
                return self._direct_langfuse_score(parsed)
            return {
                "ok": False,
                "error": f"direct LangFuse fallback does not support {command}",
                "hint": "Set ITMUX_BIN or put itmux on PATH.",
            }
        except Exception as exc:
            return {"ok": False, "error": _redact(str(exc)), "hint": "Set ITMUX_BIN or put itmux on PATH."}

    def _direct_langfuse_trace(self, args: dict[str, Any]) -> dict[str, Any]:
        trace_id, run_id = _direct_trace_selector(args)
        include_scores = bool(args.get("include-scores"))
        base_url = _langfuse_api_base_url(args.get("langfuse-base-url"))
        endpoint = f"{base_url}/api/public/traces/{parse.quote(trace_id, safe='')}"
        response = _langfuse_request("GET", endpoint)
        summary = _basic_trace_summary(response, trace_id, run_id)
        scores_response = None
        if include_scores:
            scores_response = self._direct_langfuse_scores(
                {"trace-id": trace_id, "limit": args.get("score-limit") or 20}
            )
            summary["scores"] = scores_response.get("payload", scores_response)
        return {
            "ok": True,
            "request": {
                "api": args.get("api") or "legacy-trace",
                "endpoint": endpoint,
                "trace_id": trace_id,
                "run_id": run_id,
                "include_scores": include_scores,
                "direct_fallback": True,
            },
            "summary": summary,
            "response": response,
            "scores_response": scores_response,
        }

    def _direct_langfuse_traces(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = int(args.get("limit") or 20)
        page = int(args.get("page") or 1)
        base_url = _langfuse_api_base_url(args.get("langfuse-base-url"))
        query = parse.urlencode({"limit": limit, "page": page})
        endpoint = f"{base_url}/api/public/traces?{query}"
        response = _langfuse_request("GET", endpoint)
        traces = _rows(response)
        filters = {
            "harness": args.get("harness"),
            "provider": args.get("provider"),
            "model": args.get("model"),
            "environment": args.get("environment"),
        }
        filtered = [trace for trace in traces if _trace_matches(trace, filters)]
        return {
            "ok": True,
            "request": {"endpoint": endpoint, "limit": limit, "page": page, **{k: v for k, v in filters.items() if v}},
            "summary": {"returned_count": len(filtered), "traces": [_basic_trace_row(trace) for trace in filtered]},
            "response": response,
        }

    def _direct_langfuse_scores(self, args: dict[str, Any]) -> dict[str, Any]:
        trace_id = args.get("trace-id") or (langfuse_trace_id_for_run(args["run-id"]) if args.get("run-id") else None)
        base_url = _langfuse_api_base_url(args.get("langfuse-base-url"))
        params: dict[str, Any] = {"limit": int(args.get("limit") or 20), "page": 1}
        if trace_id:
            params["traceId"] = trace_id
        if args.get("score-ids"):
            params["scoreIds"] = args["score-ids"]
        if args.get("name"):
            params["name"] = args["name"]
        if args.get("data-type"):
            params["dataType"] = str(args["data-type"]).upper()
        endpoint = f"{base_url}/api/public/scores?{parse.urlencode(params)}"
        response = _langfuse_request("GET", endpoint)
        scores = _rows(response)
        return {
            "ok": True,
            "request": {"endpoint": endpoint, "trace_id": trace_id, "run_id": args.get("run-id")},
            "summary": {"returned_count": len(scores), "scores": scores},
            "response": response,
        }

    def _direct_langfuse_score(self, args: dict[str, Any]) -> dict[str, Any]:
        trace_id, run_id = _direct_trace_selector(args)
        base_url = _langfuse_api_base_url(args.get("langfuse-base-url"))
        data_type = str(args.get("data-type") or "boolean").upper()
        payload: dict[str, Any] = {
            "traceId": trace_id,
            "name": args["name"],
            "value": _score_value(args.get("value"), data_type),
            "dataType": data_type,
        }
        if args.get("score-id"):
            payload["id"] = args["score-id"]
        if args.get("comment"):
            payload["comment"] = args["comment"]
        if args.get("metadata"):
            payload["metadata"] = args["metadata"]
        endpoint = f"{base_url}/api/public/scores"
        response = _langfuse_request("POST", endpoint, payload)
        return {
            "ok": True,
            "request": {
                "endpoint": endpoint,
                "trace_id": trace_id,
                "run_id": run_id,
                "name": args["name"],
                "data_type": data_type,
            },
            "summary": response,
            "response": response,
        }

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


def _parse_cli_args(args: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    index = 0
    while index < len(args):
        item = args[index]
        if not item.startswith("--"):
            index += 1
            continue
        key = item[2:]
        if key == "include-scores":
            parsed[key] = True
            index += 1
            continue
        if index + 1 >= len(args):
            parsed[key] = True
            index += 1
            continue
        parsed[key] = args[index + 1]
        index += 2
    return parsed


def _direct_trace_selector(args: dict[str, Any]) -> tuple[str, str | None]:
    run_id = args.get("run-id")
    trace_id = args.get("trace-id")
    if bool(run_id) == bool(trace_id):
        raise ValueError("provide exactly one of run_id or trace_id")
    if run_id:
        return langfuse_trace_id_for_run(str(run_id)), str(run_id)
    return str(trace_id), None


def langfuse_trace_id_for_run(run_id: str) -> str:
    first = _stable_hash64("agentic-primitives.trace-id.0", run_id)
    second = _stable_hash64("agentic-primitives.trace-id.1", run_id)
    return f"{first:016x}{second:016x}" or "00000000000000000000000000000001"


def _stable_hash64(domain: str, value: str) -> int:
    hash_value = 0xCBF29CE484222325
    for byte in domain.encode() + b"\0" + value.encode():
        hash_value ^= byte
        hash_value = (hash_value * 0x00000100000001B3) & 0xFFFFFFFFFFFFFFFF
    return hash_value


def _langfuse_api_base_url(base_url: Any) -> str:
    value = str(base_url or os.getenv("LANGFUSE_BASE_URL") or "").strip()
    if not value:
        raise ValueError("missing required LangFuse query configuration: LANGFUSE_BASE_URL")
    for suffix in ("/api/public/otel/v1/traces", "/api/public/otel"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value.rstrip("/")


def _langfuse_request(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    public_key = (
        os.getenv("LANGFUSE_PUBLIC_KEY")
        or os.getenv("LANGFUSE_INIT_PROJECT_PUBLIC_KEY")
        or ""
    ).strip()
    secret_key = (
        os.getenv("LANGFUSE_SECRET_KEY")
        or os.getenv("LANGFUSE_INIT_PROJECT_SECRET_KEY")
        or ""
    ).strip()
    missing = [
        name
        for name, value in (
            ("LANGFUSE_PUBLIC_KEY", public_key),
            ("LANGFUSE_SECRET_KEY", secret_key),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"missing required LangFuse query configuration: {', '.join(missing)}")
    body = None if payload is None else json.dumps(payload).encode()
    headers = {
        "Authorization": "Basic "
        + base64.b64encode(f"{public_key}:{secret_key}".encode()).decode(),
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=DEFAULT_TIMEOUT_S) as response:
            raw = response.read().decode()
    except error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        raise RuntimeError(_redact(f"LangFuse HTTP {exc.code}: {raw}")) from exc
    return json.loads(raw) if raw else {}


def _rows(response: Any) -> list[Any]:
    if isinstance(response, list):
        return response
    if not isinstance(response, dict):
        return []
    for key in ("data", "traces", "scores", "observations"):
        value = response.get(key)
        if isinstance(value, list):
            return value
    return []


def _basic_trace_summary(response: Any, trace_id: str, run_id: str | None) -> dict[str, Any]:
    row = response if isinstance(response, dict) else {}
    return {
        "trace_id": trace_id,
        "session_id": run_id or _deep_get(row, ("metadata", "agentic.run_id")),
        "trace_name": row.get("name"),
        "environment": row.get("environment") or _deep_get(row, ("metadata", "agentic.environment")),
        "harnesses": _compact_list([_deep_get(row, ("metadata", "agentic.harness"))]),
        "providers": _compact_list([_deep_get(row, ("metadata", "agentic.provider"))]),
        "models": _compact_list([_deep_get(row, ("metadata", "agentic.model"))]),
        "usage": row.get("usage") or row.get("usageDetails") or {},
        "direct_fallback": True,
    }


def _basic_trace_row(trace: Any) -> dict[str, Any]:
    if not isinstance(trace, dict):
        return {"raw": trace}
    return {
        "id": trace.get("id") or trace.get("traceId"),
        "name": trace.get("name"),
        "timestamp": trace.get("timestamp") or trace.get("createdAt"),
        "environment": trace.get("environment") or _deep_get(trace, ("metadata", "agentic.environment")),
        "harness": _deep_get(trace, ("metadata", "agentic.harness")),
        "provider": _deep_get(trace, ("metadata", "agentic.provider")),
        "model": _deep_get(trace, ("metadata", "agentic.model")),
        "usage": trace.get("usage") or trace.get("usageDetails"),
    }


def _trace_matches(trace: Any, filters: dict[str, Any]) -> bool:
    row = _basic_trace_row(trace)
    for key, expected in filters.items():
        if expected and str(row.get(key) or "").lower() != str(expected).lower():
            return False
    return True


def _deep_get(value: Any, path: tuple[str, ...]) -> Any:
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _compact_list(items: list[Any]) -> list[Any]:
    return [item for item in items if item not in (None, "")]


def _score_value(value: Any, data_type: str) -> Any:
    if data_type == "BOOLEAN":
        if isinstance(value, bool):
            return 1 if value else 0
        if str(value).lower() in ("true", "1"):
            return 1
        if str(value).lower() in ("false", "0"):
            return 0
        raise ValueError("BOOLEAN scores require one of true, false, 1, or 0")
    if data_type == "NUMERIC":
        return float(value)
    return str(value)


def _redact(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: f"{match.group(1)}{REDACTION}" if match.lastindex else REDACTION,
            redacted,
        )
    return redacted


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

    assert langfuse_trace_id_for_run("run-test") == "56e46cb6e46dc6d0ef3a439f691881dd"

    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "itmux"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys\n"
            "argv = sys.argv[1:]\n"
            "if '--fail-with-secret' in argv:\n"
            "    secret = 'sk' + '-lf-test-secret'\n"
            "    print(secret)\n"
            "    print('Author' + 'ization: ' + 'Basic ' + 'abc123secret', file=sys.stderr)\n"
            "    raise SystemExit(7)\n"
            "print(json.dumps({'ok': True, 'argv': argv}))\n",
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
                + _frame(
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {
                            "name": "agentic_langfuse_trace_discovery",
                            "arguments": {"harness": "codex", "limit": 3},
                        },
                    }
                )
                + _frame(
                    {
                        "jsonrpc": "2.0",
                        "id": 5,
                        "method": "tools/call",
                        "params": {
                            "name": "agentic_langfuse_scores",
                            "arguments": {"trace_id": "0" * 32, "name": "agentic.test"},
                        },
                    }
                )
                + _frame(
                    {
                        "jsonrpc": "2.0",
                        "id": 6,
                        "method": "tools/call",
                        "params": {
                            "name": "agentic_langfuse_score_feedback",
                            "arguments": {"run_id": "run-test", "name": "agentic.test", "value": True},
                        },
                    }
                )
                + _frame(
                    {
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "tools/call",
                        "params": {
                            "name": "agentic_langfuse_trace_discovery",
                            "arguments": {"harness": "--fail-with-secret"},
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
        discovery = json.loads(payloads[3]["result"]["content"][0]["text"])["argv"]
        assert discovery[:1] == ["langfuse-traces"]
        assert "--harness" in discovery and "codex" in discovery
        scores = json.loads(payloads[4]["result"]["content"][0]["text"])["argv"]
        assert scores[:1] == ["langfuse-scores"]
        assert "--trace-id" in scores and "0" * 32 in scores
        score = json.loads(payloads[5]["result"]["content"][0]["text"])["argv"]
        assert score[:1] == ["langfuse-score"]
        assert "--data-type" in score and "boolean" in score
        failed = json.loads(payloads[6]["result"]["content"][0]["text"])
        assert payloads[6]["result"]["isError"] is True
        assert REDACTION in failed["raw_stdout"]
        assert "Author" + "ization: Basic [REDACTED]" in failed["stderr"]
        assert "sk" + "-lf-test-secret" not in failed["raw_stdout"]
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
