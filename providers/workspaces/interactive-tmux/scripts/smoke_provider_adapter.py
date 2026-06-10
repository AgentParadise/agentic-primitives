#!/usr/bin/env python3
"""Smoke test for the `agentic_isolation.WorkspaceProvider` adapter.

Proves the WorkspaceProvider contract path works end-to-end via this
provider — addresses EXP-05 codex cross-review Major 2 (no protocol parity)
and the dispatch requirement to run "one adapter-level test proving the
WorkspaceProvider contract path works end to end for at least claude."

What it exercises (all six protocol methods):

  1. create(config)         → spins a real container; verifies handle, id, metadata
  2. execute(...)           → docker-exec `echo hello`; checks exit_code/stdout
  3. write_file(...)        → writes a UTF-8 file into /workspace
  4. file_exists(...)       → confirms the write landed
  5. read_file(...)         → reads it back byte-equal
  6. destroy(...)           → cleanly stops the container; confirms removed

Then exercises ONE prompt round-trip through the `claude` pane via the
underlying `_handle: InteractiveTmuxWorkspace` to prove the agent-level
API is still reachable on top of the protocol adapter — this is the
"works end to end for at least claude" guarantee the dispatch asked for.

Run:
  PYTHONPATH=lib/python/agentic_isolation \\
    python3 providers/workspaces/interactive-tmux/scripts/smoke_provider_adapter.py

Pre-reqs are the same as scripts/smoke.sh (image built; ~/.claude /
~/.codex / ~/.gemini authed on host).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path


def _add_paths() -> None:
    """Make the agentic_isolation module + driver importable in-place."""
    here = Path(__file__).resolve()
    repo = here.parents[4]
    sys.path.insert(0, str(repo / "lib" / "python" / "agentic_isolation"))
    sys.path.insert(0, str(repo / "providers" / "workspaces" / "interactive-tmux" / "driver"))


_add_paths()

from agentic_isolation.config import WorkspaceConfig  # noqa: E402
from agentic_isolation.providers.base import WorkspaceProvider  # noqa: E402
from agentic_isolation.providers.interactive_tmux import (  # noqa: E402
    InteractiveTmuxProvider,
)


def _container_running(container_id: str) -> bool:
    """Return True if the docker container is currently running."""
    out = subprocess.run(
        ["docker", "ps", "--filter", f"name={container_id}", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=False,
    )
    return container_id in out.stdout


async def _run() -> int:
    failures: list[str] = []

    def fail(msg: str) -> None:
        print(f"  ✗ {msg}")
        failures.append(msg)

    def ok(msg: str) -> None:
        print(f"  ✓ {msg}")

    print("[adapter-smoke] constructing provider")
    provider = InteractiveTmuxProvider(
        # Reuse $HOME defaults but pin to claude only for speed — Major 2
        # parity is the goal, not all-three-agent coverage (that's smoke.sh).
        default_host_auth={
            "claude": Path("~/.claude").expanduser(),
            "codex": None,
            "gemini": None,
        },
        strict_startup=True,  # M1 default — fail loudly on bad startup
    )

    if not isinstance(provider, WorkspaceProvider):
        # Protocol is runtime_checkable; this would catch a signature drift.
        fail("provider does not satisfy WorkspaceProvider protocol")
        return 1
    ok("provider satisfies WorkspaceProvider protocol")

    config = WorkspaceConfig(
        provider="interactive-tmux",
        working_dir="/workspace",
        labels={"agents": "claude"},
    )

    print("[adapter-smoke] create(config)")
    workspace = await provider.create(config)
    if not workspace.id or not workspace.metadata.get("container"):
        fail(f"workspace metadata incomplete: {workspace.metadata}")
        return 1
    ok(f"workspace id={workspace.id}, container={workspace.metadata['container']}")
    if not _container_running(workspace.metadata["container"]):
        fail("container not running after create()")
        return 1
    ok("container is running after create()")

    try:
        print("[adapter-smoke] execute('echo hello-adapter')")
        result = await provider.execute(workspace, "echo hello-adapter", timeout=15)
        if result.exit_code != 0:
            fail(f"execute exit_code={result.exit_code} stderr={result.stderr!r}")
        elif "hello-adapter" not in result.stdout:
            fail(f"execute stdout missing token: {result.stdout!r}")
        else:
            ok(f"execute returned stdout={result.stdout!r} duration_ms={result.duration_ms:.1f}")

        print("[adapter-smoke] write_file('adapter_note.txt', 'from-adapter')")
        token = f"from-adapter-{os.getpid()}-{int(time.time())}"
        await provider.write_file(workspace, "adapter_note.txt", token)
        ok("write_file did not raise")

        print("[adapter-smoke] file_exists('adapter_note.txt')")
        exists = await provider.file_exists(workspace, "adapter_note.txt")
        if not exists:
            fail("file_exists returned False after write_file")
        else:
            ok("file_exists confirmed the write")

        exists_negative = await provider.file_exists(workspace, "definitely-not-there.txt")
        if exists_negative:
            fail("file_exists returned True for a path that should not exist")
        else:
            ok("file_exists correctly returned False for a missing path")

        print("[adapter-smoke] read_file('adapter_note.txt')")
        roundtrip = await provider.read_file(workspace, "adapter_note.txt")
        if roundtrip != token:
            fail(f"read_file roundtrip mismatch: wrote {token!r}, got {roundtrip!r}")
        else:
            ok(f"read_file roundtrip is byte-equal ({len(token)} bytes)")

        try:
            await provider.read_file(workspace, "definitely-not-there.txt")
            fail("read_file should have raised FileNotFoundError for missing path")
        except FileNotFoundError:
            ok("read_file raised FileNotFoundError for missing path")

        # One claude prompt round-trip through the underlying _handle proves
        # the agent-level API is still reachable on top of the adapter.
        print("[adapter-smoke] claude round-trip via _handle.send_message / await_completion")
        prompt_token = f"ADAPTER-CLAUDE-{os.getpid()}-{int(time.time())}"
        ws = workspace._handle
        ws.send_message("claude", f"Reply only with: {prompt_token}")
        await_result = await asyncio.get_running_loop().run_in_executor(
            None, lambda: ws.await_completion("claude", timeout=120),
        )
        if not hasattr(await_result, "reason"):
            fail(f"await_completion did not return AwaitResult: {await_result!r}")
        elif not await_result.ready:
            fail(
                f"claude await_completion not ready: reason={await_result.reason} "
                f"timed_out={await_result.timed_out} duration_ms={await_result.duration_ms:.1f}"
            )
        else:
            ok(
                f"await_completion ready: reason={await_result.reason} "
                f"duration_ms={await_result.duration_ms:.1f} "
                f"stable_polls_observed={await_result.stable_polls_observed}"
            )
            pane = ws.capture_response("claude")
            if f"● {prompt_token}" not in pane:
                fail(f"claude response marker `● {prompt_token}` not in pane")
            else:
                ok(f"claude pane contains `● {prompt_token}`")

    finally:
        print("[adapter-smoke] destroy(workspace)")
        container_name = workspace.metadata["container"]
        await provider.destroy(workspace)
        if _container_running(container_name):
            fail("container still running after destroy()")
        else:
            ok("container removed after destroy()")

    print()
    if failures:
        print(f"[adapter-smoke] FAIL — {len(failures)} step(s) failed:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[adapter-smoke] PASS — all 6 WorkspaceProvider methods + claude round-trip")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
