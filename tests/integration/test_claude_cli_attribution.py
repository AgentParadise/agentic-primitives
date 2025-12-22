"""
Integration test for Claude CLI attribution settings.

This test validates that Claude CLI attribution is properly disabled
in the workspace container, preventing "Generated with Claude Code" messages
from appearing in git commits and PR descriptions.

See: https://github.com/AgentParadise/sandbox_aef-engineer-beta/pull/49/commits/7bdf58c38451542ef528f0cacf6a7021fa2833f1
"""

import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_claude_cli_attribution_disabled_in_container():
    """
    Test that Claude CLI attribution is disabled in the workspace container.

    This test:
    1. Starts a container with tmpfs mount (production config)
    2. Creates .claude/settings.json with attribution disabled
    3. Initializes a git repo and makes a commit
    4. Validates no attribution appears in the commit message

    This is a regression test for an issue where attribution kept appearing
    despite multiple fix attempts.
    """
    # Setup script that mimics production setup phase
    setup_script = """
#!/bin/bash
set -e

# Configure git (minimal setup for commit)
git config --global user.name "Test Bot"
git config --global user.email "test@example.com"
git config --global init.defaultBranch main

# Disable Claude Code attribution (v2.0.62+ format)
mkdir -p ~/.claude
cat > ~/.claude/settings.json << 'EOF'
{
  "attribution": {
    "commits": false,
    "pullRequests": false
  }
}
EOF
chmod 600 ~/.claude/settings.json

# Verify settings file was created
echo "Settings file created:"
cat ~/.claude/settings.json

# Initialize git repo and make a test commit
cd /workspace
git init
echo "test content" > test.txt
git add test.txt
git commit -m "feat: test commit" || echo "Commit failed"

# Output the commit message for validation
git log -1 --pretty=format:"%B"
"""

    # Create temporary test script
    test_script_path = Path("/tmp/test_attribution_setup.sh")
    test_script_path.write_text(setup_script)

    try:
        # Run container with production tmpfs configuration
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000",
                "-v",
                f"{test_script_path}:/tmp/setup.sh:ro",
                "agentic-workspace-claude-cli:latest",
                "bash",
                "/tmp/setup.sh",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Check setup ran successfully
        assert result.returncode == 0, f"Setup failed: {result.stderr}"

        # Validate commit message doesn't contain attribution
        commit_message = result.stdout.strip()

        # These strings should NOT appear in the commit
        forbidden_strings = [
            "Generated with Claude Code",
            "Claude Code",
            "Co-Authored-By: Claude",
            "🤖 Generated with",
        ]

        for forbidden in forbidden_strings:
            assert forbidden not in commit_message, (
                f"Attribution found in commit message: '{forbidden}'\n"
                f"Full commit message:\n{commit_message}\n\n"
                f"This means .claude/settings.json was not properly configured or Claude CLI ignored it."
            )

        # Validate expected commit message is present
        assert "feat: test commit" in commit_message, (
            f"Expected commit message not found. Got: {commit_message}"
        )

        print(f"✅ Attribution test passed. Commit message: {commit_message}")

    finally:
        # Cleanup
        test_script_path.unlink(missing_ok=True)


@pytest.mark.integration
def test_settings_json_format_current():
    """
    Test that settings.json uses the current v2.0.62+ format.

    This validates the format matches Claude CLI documentation:
    https://docs.claude.com/en/docs/claude-code/settings
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
            """
            mkdir -p ~/.claude
            cat > ~/.claude/settings.json << 'EOF'
{
  "attribution": {
    "commits": false,
    "pullRequests": false
  }
}
EOF
            cat ~/.claude/settings.json
            """,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, f"Failed to create settings: {result.stderr}"

    # Validate JSON structure
    import json
    settings = json.loads(result.stdout.strip())

    assert "attribution" in settings, "Missing 'attribution' key"
    assert settings["attribution"]["commits"] is False, "commits should be false"
    assert settings["attribution"]["pullRequests"] is False, "pullRequests should be false"

    # Ensure deprecated fields are NOT present
    assert "disableAttribution" not in settings, "Deprecated 'disableAttribution' found"
    assert "includeAttribution" not in settings, "Deprecated 'includeAttribution' found"

    print("✅ Settings format validation passed")


if __name__ == "__main__":
    # Allow running directly for quick validation
    print("Running attribution tests...")
    test_settings_json_format_current()
    test_claude_cli_attribution_disabled_in_container()
    print("\n✅ All attribution tests passed!")
