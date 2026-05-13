"""Integration tests for the workspace injection entrypoint section.

Mirrors the pattern in test_entrypoint_lsp_settings.py — runs the
real workspace container against a synthetic /etc/agentic/workspace/
bind-mount and asserts the resulting /workspace/ + ~/.claude/agents
state.

See spec: docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md
"""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

IMAGE = "agentic-workspace-claude-cli:latest"


def _run(args: list[str], extra_mounts: list[str] | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run an arbitrary command in the workspace container with a tmpfs
    home dir (matches LSP test pattern). Optionally bind-mount extra
    paths and pass env vars. Returns the completed process."""
    cmd = [
        "docker", "run", "--rm",
        "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000",
    ]
    for m in extra_mounts or []:
        cmd.extend(["-v", m])
    for k, v in (env or {}).items():
        cmd.extend(["-e", f"{k}={v}"])
    cmd.append(IMAGE)
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


@pytest.mark.integration
def test_entrypoint_copies_workspace_context_md(tmp_path: Path):
    """Bind-mount a workspace dir with a CLAUDE.md; the entrypoint must
    copy it verbatim to /workspace/CLAUDE.md."""
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    (workspace_dir / "CLAUDE.md").write_text("# Test workspace\n\nHello from the test.\n")

    result = _run(
        ["cat", "/workspace/CLAUDE.md"],
        extra_mounts=[f"{workspace_dir}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "Test workspace" in result.stdout
    assert "Hello from the test" in result.stdout
