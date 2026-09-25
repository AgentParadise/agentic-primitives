"""Actual Claude -> Codex -> Claude with an offline model fixture, no credentials."""

import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __package__:
    from .native_fixture_protocol import messages, responses
else:
    from native_fixture_protocol import messages, responses

from agentic_session_store.child_journal import ChildJournal
from agentic_session_store.install_child_hooks import install

ENABLED = os.environ.get("CLAUDE_NATIVE_TEST_BINARY") and os.environ.get(
    "CODEX_NATIVE_TEST_BINARY"
)


@unittest.skipUnless(ENABLED, "Set both pinned native test binaries")
def test_real_cross_harness_depth_three(tmp_path):
    for binary, version in (
        ("claude", "2.1.281 (Claude Code)"),
        ("codex", "codex-cli 0.156.1"),
    ):
        assert (
            subprocess.check_output([binary, "--version"], text=True).strip() == version
        )
    home = tmp_path / "home"
    home.mkdir()
    claude = home / ".claude"
    codex = home / ".codex"
    install(claude / "settings.json", harness="claude")
    install(codex / "config.toml")
    spool = tmp_path / "spool"
    path = spool / ".agentic-session-store/run/children.sqlite"
    path.parent.mkdir(parents=True)
    journal = ChildJournal(path)
    runner = os.environ.get("DELEGATE_NATIVE_TEST_BINARY")
    runner = (
        shlex.quote(runner)
        if runner
        else shlex.quote(sys.executable) + " -m agentic_session_store.delegate"
    )
    requests = {"claude": 0, "codex": 0}
    prelaunch = []
    diagnostics = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path.startswith("/v1/responses"):
                requests["codex"] += 1
                if requests["codex"] == 1:
                    prelaunch.append(
                        any(
                            c.intent.call.target_harness == "codex"
                            and c.intent.child_native_id is None
                            for c in journal.page().changes
                        )
                    )
                responses(
                    self,
                    runner
                    + " claude --prompt FIXTURE_FINAL --model claude-sonnet-4-5 --timeout 20"
                    if requests["codex"] == 1
                    else None,
                )
            else:
                requests["claude"] += 1
                diagnostics.extend(
                    str(block.get("content", ""))[-2000:]
                    for m in request.get("messages", [])
                    for block in m.get("content", [])
                    if isinstance(block, dict) and block.get("type") == "tool_result"
                )
                first = request.get("messages", [{}])[0].get("content", [])
                final = any(b.get("text") == "FIXTURE_FINAL" for b in first)
                if final:
                    prelaunch.append(
                        any(
                            c.intent.call.target_harness == "claude"
                            and c.intent.child_native_id is None
                            for c in journal.page().changes
                        )
                    )
                messages(
                    self,
                    runner + " codex --prompt FIXTURE_CODEX --timeout 30"
                    if requests["claude"] == 1
                    else None,
                )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # The test runs in a network-disabled disposable container. These are
    # fixture-local CLI policies, never installed by the delegation shim.
    import tomlkit

    document = tomlkit.parse((codex / "config.toml").read_text())
    document["model_provider"] = "fixture"
    document["approval_policy"] = "never"
    # syn-delegate passes --sandbox workspace-write, which overrides any
    # sandbox_mode here. The nested delegate must reach the loopback fixture.
    document["sandbox_workspace_write"] = {"network_access": True}
    document["model_providers"] = {
        "fixture": {
            "name": "fixture",
            "base_url": f"http://127.0.0.1:{server.server_port}/v1",
            "wire_api": "responses",
            "requires_openai_auth": False,
            "supports_websockets": False,
        }
    }
    document["shell_environment_policy"] = {"inherit": "all"}
    (codex / "config.toml").write_text(tomlkit.dumps(document))
    environment = {
        **os.environ,
        "HOME": str(home),
        "CLAUDE_CONFIG_DIR": str(claude),
        "CODEX_HOME": str(codex),
        "CODEX_SQLITE_HOME": str(codex),
        "ANTHROPIC_API_KEY": "fixture",
        "CODEX_API_KEY": "fixture",
        "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{server.server_port}",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "AGENTIC_SESSION_STORE_PROVIDER": "local",
        "AGENTIC_SESSION_STORE_SPOOL": str(spool),
        "AGENTIC_SESSION_STORE_PARTITION": "run",
        "AGENTIC_INVOCATION_ID": "invocation",
        "AGENTIC_ATTEMPT_ID": "attempt",
    }
    # What the workspace entrypoint does at startup: probe the real sandbox and
    # record the verdict. Without the Codex sandbox seccomp profile this reports
    # unavailable and syn-delegate refuses to launch Codex.
    probe = subprocess.run(
        [
            os.environ["CODEX_NATIVE_TEST_BINARY"],
            "sandbox",
            "-c",
            'sandbox_mode="workspace-write"',
            "--",
            "true",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    status = tmp_path / "codex-sandbox.json"
    status.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "available": probe.returncode == 0,
                "detail": probe.stderr[-300:],
            }
        )
    )
    environment["AGENTIC_CODEX_SANDBOX_STATUS"] = str(status)
    environment.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    environment.pop("CODEX_THREAD_ID", None)
    try:
        result = subprocess.run(
            [
                os.environ["CLAUDE_NATIVE_TEST_BINARY"],
                "-p",
                "FIXTURE_ROOT",
                "--model",
                "claude-sonnet-4-5",
                "--tools",
                "Bash",
                "--allowedTools",
                "Bash",
                "--output-format",
                "json",
                "--max-turns",
                "4",
            ],
            env=environment,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        root_id = json.loads(result.stdout)["session_id"]
        changes = ChildJournal(path).page().changes
        latest = {c.intent.child_invocation_id: c.intent for c in changes}
        assert len(latest) == 2, (changes, diagnostics, result.stderr)
        by_harness = {intent.call.target_harness: intent for intent in latest.values()}
        codex_child, claude_child = by_harness["codex"], by_harness["claude"]
        assert codex_child.call.harness == "claude"
        assert codex_child.call.parent_native_id == root_id
        assert claude_child.call.harness == "codex"
        assert claude_child.call.parent_native_id == codex_child.child_native_id
        assert (
            len({root_id, codex_child.child_native_id, claude_child.child_native_id})
            == 3
        )
        assert None not in {codex_child.child_native_id, claude_child.child_native_id}
        assert all(
            intent.status == "completed" and intent.exit_code == 0
            for intent in latest.values()
        ), changes
        assert prelaunch == [True, True]
        # Independent native files corroborate the runtime output bindings.
        native_codex = {
            json.loads(p.read_text().splitlines()[0])["payload"]["id"]
            for p in (codex / "sessions").rglob("*.jsonl")
        }
        assert codex_child.child_native_id in native_codex
        native_claude = {
            row["sessionId"]
            for p in (claude / "projects").rglob("*.jsonl")
            for line in p.read_text().splitlines()
            if (row := json.loads(line)).get("sessionId")
        }
        assert {root_id, claude_child.child_native_id} <= native_claude
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        test_real_cross_harness_depth_three(Path(directory))
    print("Pinned Claude -> Codex -> Claude passed")
