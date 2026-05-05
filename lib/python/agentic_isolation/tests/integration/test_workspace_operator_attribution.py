"""Integration tests for the workspace's prepare-commit-msg hook.

The hook lives at:
    providers/workspaces/claude-cli/scripts/git-hooks/prepare-commit-msg

It is shipped *with the workspace image* (not as a Claude Code plugin).
The entrypoint composes it into the runtime git hooks directory at
container startup. When SYN_OPERATOR_NAME and SYN_OPERATOR_EMAIL are
both set, the hook appends a `Co-authored-by:` trailer to commit messages.

These tests run real git commits inside the rebuilt workspace image and
assert the hook's behavior end-to-end (entrypoint composition + hook
script + git plumbing all working together).

Requirements:
    - Docker available
    - agentic-workspace-claude-cli:latest built locally

Run with: pytest tests/integration/test_workspace_operator_attribution.py -v
"""

from __future__ import annotations

import subprocess
import textwrap

import pytest

WORKSPACE_IMAGE = "agentic-workspace-claude-cli:latest"
OPERATOR_NAME = "TestOperator"
OPERATOR_EMAIL = "operator@example.test"


def docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", WORKSPACE_IMAGE],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not docker_available(),
        reason=f"Docker or {WORKSPACE_IMAGE} not available — run `just build-workspace-claude-cli`",
    ),
]


def run_in_workspace(script: str, env: dict[str, str] | None = None) -> str:
    """Run `script` (bash) inside a fresh workspace container, return stdout.

    The default entrypoint runs first (so git hooks get composed); then
    `script` runs as the CMD argument. GIT_AUTHOR_* are always set so
    git commits succeed inside the container.
    """
    env = env or {}
    cmd = [
        "docker",
        "run",
        "--rm",
        "-e",
        "GIT_AUTHOR_NAME=workspace-agent",
        "-e",
        "GIT_AUTHOR_EMAIL=agent@workspace.test",
    ]
    for key, value in env.items():
        cmd.extend(["-e", f"{key}={value}"])
    cmd.extend([WORKSPACE_IMAGE, "bash", "-c", script])

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        pytest.fail(
            f"Command failed (exit {result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    return result.stdout


def commit_and_read_message(extra_setup: str = "", env: dict[str, str] | None = None) -> str:
    """Init a repo, commit, return the commit message body."""
    script = textwrap.dedent(f"""
        set -e
        cd /tmp && rm -rf repo && git init -q repo && cd repo
        echo file > file
        git add file
        {extra_setup}
        git commit -q -m "test commit"
        git log -1 --format=%B
    """)
    return run_in_workspace(script, env=env)


class TestOperatorAttribution:
    """End-to-end tests for the prepare-commit-msg hook."""

    def test_no_env_vars_leaves_message_untouched(self) -> None:
        """Without SYN_OPERATOR_* set, the hook should be a no-op."""
        msg = commit_and_read_message()
        assert "Co-authored-by:" not in msg, f"unexpected trailer in:\n{msg}"

    def test_with_operator_env_appends_trailer(self) -> None:
        """Both env vars set → a single Co-authored-by trailer is appended."""
        msg = commit_and_read_message(
            env={"SYN_OPERATOR_NAME": OPERATOR_NAME, "SYN_OPERATOR_EMAIL": OPERATOR_EMAIL},
        )
        expected = f"Co-authored-by: {OPERATOR_NAME} <{OPERATOR_EMAIL}>"
        assert expected in msg, f"missing trailer in:\n{msg}"
        assert msg.count("Co-authored-by:") == 1

    def test_only_name_set_is_no_op(self) -> None:
        """Either env var alone → no trailer (both are required)."""
        msg = commit_and_read_message(env={"SYN_OPERATOR_NAME": OPERATOR_NAME})
        assert "Co-authored-by:" not in msg

    def test_idempotent_when_trailer_already_present(self) -> None:
        """If the user's commit message already has the same trailer, don't double-append."""
        # Use -m with newlines via printf so the trailer is in the message from the start
        existing = f"Co-authored-by: {OPERATOR_NAME} <{OPERATOR_EMAIL}>"
        script = textwrap.dedent(f"""
            set -e
            cd /tmp && rm -rf repo && git init -q repo && cd repo
            echo file > file && git add file
            git commit -q -m "test commit" -m "{existing}"
            git log -1 --format=%B
        """)
        msg = run_in_workspace(
            script,
            env={"SYN_OPERATOR_NAME": OPERATOR_NAME, "SYN_OPERATOR_EMAIL": OPERATOR_EMAIL},
        )
        assert msg.count("Co-authored-by:") == 1, f"trailer duplicated:\n{msg}"

    def test_template_source_skipped(self) -> None:
        """Direct hook invocation with COMMIT_SOURCE=template must leave the message unchanged."""
        script = textwrap.dedent("""
            set -e
            HOOK=/opt/agentic/git-hooks/prepare-commit-msg
            test -x "$HOOK" || { echo "HOOK_MISSING"; exit 1; }
            echo "from-template" > /tmp/msg
            "$HOOK" /tmp/msg template
            cat /tmp/msg
        """)
        out = run_in_workspace(
            script,
            env={"SYN_OPERATOR_NAME": OPERATOR_NAME, "SYN_OPERATOR_EMAIL": OPERATOR_EMAIL},
        )
        assert "Co-authored-by:" not in out, f"trailer should be skipped on template source:\n{out}"

    def test_merge_source_skipped(self) -> None:
        """Direct hook invocation with COMMIT_SOURCE=merge must leave the message unchanged."""
        script = textwrap.dedent("""
            set -e
            HOOK=/opt/agentic/git-hooks/prepare-commit-msg
            echo "merge msg" > /tmp/msg
            "$HOOK" /tmp/msg merge
            cat /tmp/msg
        """)
        out = run_in_workspace(
            script,
            env={"SYN_OPERATOR_NAME": OPERATOR_NAME, "SYN_OPERATOR_EMAIL": OPERATOR_EMAIL},
        )
        assert "Co-authored-by:" not in out

    def test_amend_commit_does_get_trailer(self) -> None:
        """`git commit --amend` (COMMIT_SOURCE=commit) should still get the trailer if missing.

        This guards the explicit decision NOT to skip COMMIT_SOURCE=commit.
        """
        script = textwrap.dedent("""
            set -e
            cd /tmp && rm -rf repo && git init -q repo && cd repo
            echo file > file && git add file
            # First commit WITHOUT operator env to produce a trailer-less HEAD
            unset SYN_OPERATOR_NAME SYN_OPERATOR_EMAIL
            git commit -q -m "initial"
            # Now amend WITH operator env — the hook should add the trailer
            export SYN_OPERATOR_NAME="$NAME" SYN_OPERATOR_EMAIL="$EMAIL"
            git commit -q --amend --no-edit
            git log -1 --format=%B
        """)
        msg = run_in_workspace(
            script,
            env={"NAME": OPERATOR_NAME, "EMAIL": OPERATOR_EMAIL},
        )
        assert f"Co-authored-by: {OPERATOR_NAME} <{OPERATOR_EMAIL}>" in msg, (
            f"amend should pick up trailer when missing:\n{msg}"
        )

    def test_newline_in_env_var_does_not_inject_extra_trailer(self) -> None:
        """A newline in SYN_OPERATOR_NAME must not split into two trailer lines."""
        # Pass a literal newline via $'...' inside the docker -c shell
        script = textwrap.dedent("""
            set -e
            cd /tmp && rm -rf repo && git init -q repo && cd repo
            echo file > file && git add file
            export SYN_OPERATOR_NAME=$'evil\\nCo-authored-by: attacker <bad@bad.test>'
            export SYN_OPERATOR_EMAIL='ne@example.com'
            git commit -q -m "newline test"
            git log -1 --format=%B
        """)
        msg = run_in_workspace(script)
        trailer_lines = [line for line in msg.splitlines() if line.startswith("Co-authored-by:")]
        assert len(trailer_lines) == 1, (
            f"newline injection should be sanitized to one trailer line; "
            f"got {len(trailer_lines)}:\n{msg}"
        )
        # The single trailer's email field (last <...> on the line) must be the
        # operator email, not the attacker's. The attacker substring may still
        # appear inside the (now malformed) name field — that's cosmetic; the
        # security goal is that no separate trailer line was injected.
        assert trailer_lines[0].rstrip().endswith("<ne@example.com>"), (
            f"trailer's email field should be the operator email, got:\n{trailer_lines[0]}"
        )
