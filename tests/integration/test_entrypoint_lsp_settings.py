"""
Integration test for entrypoint-generated LSP plugin settings.

Validates that the workspace entrypoint writes ~/.claude/settings.json
with the expected LSP plugins enabled by default.

The entrypoint is the source of truth for runtime settings because
/home/agent is a tmpfs mount that wipes anything baked into the image.
"""

import json
import subprocess

import pytest


@pytest.mark.integration
def test_entrypoint_enables_lsp_plugins():
    """
    Test that the entrypoint creates settings.json with LSP plugins enabled.

    This test starts the container (which runs entrypoint.sh), then
    inspects the generated ~/.claude/settings.json to verify the expected
    plugins are present and enabled.
    """
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000",
            "agentic-workspace-claude-cli:latest",
            "cat",
            "/home/agent/.claude/settings.json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"Container failed: {result.stderr}"

    settings = json.loads(result.stdout.strip())

    # Verify enabledPlugins section exists
    assert "enabledPlugins" in settings, (
        "Missing 'enabledPlugins' in settings.json. "
        "The entrypoint must write LSP plugin enables."
    )

    # Verify all three LSP plugins are enabled
    expected_plugins = {
        "pyright-lsp@claude-plugins-official": True,
        "typescript-lsp@claude-plugins-official": True,
        "rust-analyzer-lsp@claude-plugins-official": True,
    }

    for plugin, expected_value in expected_plugins.items():
        assert settings["enabledPlugins"].get(plugin) == expected_value, (
            f"Plugin '{plugin}' should be {expected_value} in enabledPlugins. "
            f"Got: {settings['enabledPlugins'].get(plugin)}"
        )


@pytest.mark.integration
def test_lifecycle_hooks_declared_by_plugins():
    """
    Test that the workspace's lifecycle hooks are declared plugin-natively.

    Since the v3 plugin-native image (ADR-033/034), hooks are no longer
    injected into ~/.claude/settings.json by the entrypoint; each plugin
    ships its own hooks/hooks.json. The observability plugin declares the
    full lifecycle set, so this verifies the hooks the workspace relies on
    are wired into the image.
    """
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "agentic-workspace-claude-cli:latest",
            "cat",
            "/opt/agentic/plugins/observability/hooks/hooks.json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"Container failed: {result.stderr}"

    config = json.loads(result.stdout.strip())
    hooks = config.get("hooks", {})

    expected_hooks = [
        "PreToolUse",
        "PostToolUse",
        "SessionStart",
        "SessionEnd",
        "Stop",
        "SubagentStop",
    ]

    for hook in expected_hooks:
        assert hook in hooks, (
            f"Missing '{hook}' in observability plugin hooks.json. "
            f"Found: {list(hooks.keys())}"
        )


@pytest.mark.integration
def test_entrypoint_creates_cargo_home():
    """
    Test that the entrypoint creates a writable CARGO_HOME for the agent user.

    CARGO_HOME must be writable so cargo can manage its registry index
    and git checkouts at runtime.
    """
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000",
            "agentic-workspace-claude-cli:latest",
            "sh",
            "-c",
            "test -d ~/.cargo && test -w ~/.cargo && echo 'writable'",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, f"Container failed: {result.stderr}"
    assert "writable" in result.stdout, (
        "~/.cargo is not writable by the agent user. "
        "Rust builds will fail without a writable CARGO_HOME."
    )


if __name__ == "__main__":
    print("Running entrypoint LSP settings tests...")
    test_entrypoint_enables_lsp_plugins()
    test_lifecycle_hooks_declared_by_plugins()
    test_entrypoint_creates_cargo_home()
    print("\nAll entrypoint settings tests passed!")
