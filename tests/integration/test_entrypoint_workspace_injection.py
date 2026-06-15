"""Integration tests for the workspace injection entrypoint section.

Mirrors the pattern in test_entrypoint_lsp_settings.py — runs the
real workspace container against a synthetic /etc/agentic/workspace/
bind-mount and asserts the resulting /workspace/ + ~/.claude/agents
state.

See spec: docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md
"""

import subprocess
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


@pytest.mark.integration
def test_entrypoint_rejects_context_path_traversal(tmp_path: Path):
    """AGENTIC_WORKSPACE_CONTEXT must select a file by safe name only."""
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    result = _run(
        ["sh", "-c", "test -f /workspace/CLAUDE.md && cat /workspace/CLAUDE.md || echo NO_CTX"],
        extra_mounts=[f"{workspace_dir}:/etc/agentic/workspace:ro"],
        env={"AGENTIC_WORKSPACE_CONTEXT": "../../etc/passwd"},
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "NO_CTX" in result.stdout
    assert "root:" not in result.stdout


@pytest.mark.integration
def test_entrypoint_copies_workspace_plugins(tmp_path: Path):
    """A plugin under /etc/agentic/workspace/plugins/<name>/ with a valid
    manifest should be copied to /workspace/.agentic-plugins/<name>/ and
    its --plugin-dir flag appended to AGENTIC_PLUGIN_FLAGS."""
    ws = tmp_path / "workspace"
    plugin = ws / "plugins" / "demo-plugin" / ".claude-plugin"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text('{"name":"demo-plugin","version":"0.1.0"}\n')

    result = _run(
        ["sh", "-c", "ls /workspace/.agentic-plugins/ && echo SEP && echo \"$AGENTIC_PLUGIN_FLAGS\""],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    listing, _, flags = result.stdout.partition("SEP")
    assert "demo-plugin" in listing
    assert "--plugin-dir /workspace/.agentic-plugins/demo-plugin" in flags


@pytest.mark.integration
def test_entrypoint_copies_loose_subagents(tmp_path: Path):
    """A loose subagent at /etc/agentic/workspace/agents/<name>.md should
    be copied to ~/.claude/agents/<name>.md verbatim."""
    ws = tmp_path / "workspace"
    agents = ws / "agents"
    agents.mkdir(parents=True)
    (agents / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Test reviewer\ntools: [Read]\n---\n\nYou are a test.\n"
    )

    result = _run(
        ["cat", "/home/agent/.claude/agents/reviewer.md"],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "name: reviewer" in result.stdout
    assert "You are a test" in result.stdout


@pytest.mark.integration
def test_entrypoint_filters_plugins_by_env(tmp_path: Path):
    """AGENTIC_WORKSPACE_PLUGINS=foo:bar should copy only foo+bar, not
    a third plugin baz that's also present."""
    ws = tmp_path / "workspace"
    for name in ["foo", "bar", "baz"]:
        d = ws / "plugins" / name / ".claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(f'{{"name":"{name}","version":"0.1.0"}}\n')

    result = _run(
        ["ls", "/workspace/.agentic-plugins/"],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
        env={"AGENTIC_WORKSPACE_PLUGINS": "foo:bar"},
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    listing = set(result.stdout.split())
    assert "foo" in listing
    assert "bar" in listing
    assert "baz" not in listing, f"baz should be filtered out, listing={listing}"


@pytest.mark.integration
def test_entrypoint_skips_when_no_workspace_mount():
    """Without /etc/agentic/workspace/ bind-mounted, the new section is a
    no-op: /workspace/CLAUDE.md does not exist and AGENTIC_PLUGIN_FLAGS
    contains only the baked-in plugins (observability, sdlc, workspace)."""
    result = _run(
        ["sh", "-c", "test -f /workspace/CLAUDE.md && echo HAS_CTX || echo NO_CTX; echo \"FLAGS=$AGENTIC_PLUGIN_FLAGS\""],
    )

    assert result.returncode == 0, f"container failed: {result.stderr}"
    assert "NO_CTX" in result.stdout, f"unexpected /workspace/CLAUDE.md: {result.stdout}"
    # Baked-in plugins should still be present in the flags.
    assert "--plugin-dir /opt/agentic/plugins/observability" in result.stdout


@pytest.mark.integration
def test_entrypoint_skips_invalid_plugin_dir(tmp_path: Path):
    """A 'plugin' directory lacking .claude-plugin/plugin.json must NOT
    be copied and must NOT be added to AGENTIC_PLUGIN_FLAGS."""
    ws = tmp_path / "workspace"
    (ws / "plugins" / "garbage").mkdir(parents=True)
    # No .claude-plugin/plugin.json inside garbage/

    result = _run(
        ["sh", "-c", "ls /workspace/.agentic-plugins/ 2>&1 || true; echo \"FLAGS=$AGENTIC_PLUGIN_FLAGS\""],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0
    assert "garbage" not in result.stdout


@pytest.mark.integration
def test_entrypoint_appends_to_agentic_plugin_flags_does_not_replace(tmp_path: Path):
    """When a per-workspace plugin is injected, AGENTIC_PLUGIN_FLAGS must
    contain BOTH the baked-in plugins AND the new one — appending, not
    replacing."""
    ws = tmp_path / "workspace"
    d = ws / "plugins" / "extra" / ".claude-plugin"
    d.mkdir(parents=True)
    (d / "plugin.json").write_text('{"name":"extra","version":"0.1.0"}\n')

    result = _run(
        ["sh", "-c", "echo \"$AGENTIC_PLUGIN_FLAGS\""],
        extra_mounts=[f"{ws}:/etc/agentic/workspace:ro"],
    )

    assert result.returncode == 0
    flags = result.stdout
    # Baked-in plugins present
    assert "/opt/agentic/plugins/observability" in flags
    assert "/opt/agentic/plugins/sdlc" in flags
    assert "/opt/agentic/plugins/workspace" in flags
    # New per-workspace plugin appended
    assert "/workspace/.agentic-plugins/extra" in flags
