"""Protocol conformance tests for the LangFuse MCP server.

These tests deliberately do NOT import the server's own framing helpers. They
speak the wire protocol the way a real MCP client does: newline-delimited
JSON-RPC over stdio, one message per line.

That independence is the point. The server previously used LSP-style
`Content-Length` header framing, and its bundled self-test used the same
helper to build requests, so the self-test round-tripped happily while every
real client timed out. A test that borrows the implementation's framing cannot
detect a framing bug.

Reference: https://modelcontextprotocol.io/specification/draft/basic/transports
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SERVER = REPO_ROOT / "plugins" / "observability" / "mcp" / "langfuse_server.py"


def _speak(requests: list[dict], env_extra: dict[str, str] | None = None) -> list[dict]:
    """Send newline-delimited JSON-RPC to the server and parse its replies."""
    env = dict(os.environ)
    env.pop("LANGFUSE_BASE_URL", None)
    env.pop("LANGFUSE_PUBLIC_KEY", None)
    env.pop("LANGFUSE_SECRET_KEY", None)
    env.update(env_extra or {})
    stdin = "".join(json.dumps(request) + "\n" for request in requests)
    completed = subprocess.run(
        [sys.executable, str(SERVER)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    return [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]


def test_server_file_exists() -> None:
    assert SERVER.is_file(), f"MCP server not found at {SERVER}"


class TestStdioFraming:
    def test_initialize_gets_a_response(self) -> None:
        """A newline-delimited initialize must be answered.

        This is the exact request shape a real client sends. Under the old
        Content-Length framing the server read this line as a header, found no
        content-length, and exited without writing a byte.
        """
        replies = _speak([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])
        assert replies, "server produced no response to a newline-delimited initialize"
        assert replies[0]["id"] == 1
        assert replies[0]["result"]["protocolVersion"]

    def test_response_is_one_json_object_per_line(self) -> None:
        """No Content-Length headers may appear in the output stream."""
        replies = _speak([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])
        assert len(replies) == 1
        assert replies[0]["jsonrpc"] == "2.0"

    def test_multiple_requests_are_answered_in_order(self) -> None:
        replies = _speak(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
        )
        assert [reply["id"] for reply in replies] == [1, 2]

    def test_tools_list_returns_tools(self) -> None:
        replies = _speak(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ]
        )
        tools = replies[1]["result"]["tools"]
        assert tools and all("name" in tool for tool in tools)

    def test_server_version_matches_plugin_manifest(self) -> None:
        manifest = json.loads(
            (REPO_ROOT / "plugins" / "observability" / ".claude-plugin" / "plugin.json").read_text()
        )
        replies = _speak([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}])
        assert replies[0]["result"]["serverInfo"]["version"] == manifest["version"]


class TestOriginIsNotCallerControlled:
    """The LangFuse origin must come from server config, never a tool argument.

    `_langfuse_request` attaches LANGFUSE_SECRET_KEY as Basic auth to whatever
    origin is resolved. If a caller could choose that origin, injected tool
    arguments would exfiltrate the credentials to an arbitrary host.
    """

    @staticmethod
    def _resolve(base_url, configured: str | None):
        sys.path.insert(0, str(SERVER.parent))
        try:
            import importlib

            module = importlib.import_module("langfuse_server")
            importlib.reload(module)
            previous = os.environ.get("LANGFUSE_BASE_URL")
            if configured is None:
                os.environ.pop("LANGFUSE_BASE_URL", None)
            else:
                os.environ["LANGFUSE_BASE_URL"] = configured
            try:
                return module._langfuse_api_base_url(base_url)
            finally:
                if previous is None:
                    os.environ.pop("LANGFUSE_BASE_URL", None)
                else:
                    os.environ["LANGFUSE_BASE_URL"] = previous
        finally:
            sys.path.remove(str(SERVER.parent))

    def test_foreign_origin_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="forbidden"):
            self._resolve("https://attacker.example", "https://langfuse.internal")

    def test_configured_origin_is_used_when_no_override(self) -> None:
        assert self._resolve(None, "https://langfuse.internal") == "https://langfuse.internal"

    def test_matching_override_is_accepted(self) -> None:
        assert (
            self._resolve("https://langfuse.internal/", "https://langfuse.internal")
            == "https://langfuse.internal"
        )

    def test_otel_suffix_is_normalized_before_comparison(self) -> None:
        assert (
            self._resolve(
                "https://langfuse.internal/api/public/otel/v1/traces",
                "https://langfuse.internal",
            )
            == "https://langfuse.internal"
        )

    def test_override_is_rejected_when_nothing_is_configured(self) -> None:
        """An unset LANGFUSE_BASE_URL must not let the caller supply one.

        The credentials live in separate env vars, so an unconfigured origin
        plus a caller-supplied one is still a live exfiltration path.
        """
        with pytest.raises(ValueError, match="LANGFUSE_BASE_URL"):
            self._resolve("https://attacker.example", None)
