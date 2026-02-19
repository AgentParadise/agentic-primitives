"""Integration tests for git detection in the observability handler (observe.py).

Tests the _extract_git_subcmd and _emit_git_event functions that detect
git operations from Bash tool invocations and emit rich git-specific events.
"""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_events import EventEmitter

pytestmark = pytest.mark.unit

# Load observe.py as a module for unit testing its internal functions
OBSERVE_PATH = (
    Path(__file__).parent.parent.parent.parent.parent
    / "plugins"
    / "observability"
    / "hooks"
    / "handlers"
    / "observe.py"
)


@pytest.fixture
def observe_module():
    """Load the observe.py handler as a module."""
    if not OBSERVE_PATH.exists():
        pytest.skip(f"observe.py not found at {OBSERVE_PATH}")
    spec = importlib.util.spec_from_file_location("observe", OBSERVE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def emitter():
    """Create an emitter writing to a StringIO buffer."""
    output = io.StringIO()
    return EventEmitter(session_id="test-git-hooks", output=output), output


# ============================================================================
# _extract_git_subcmd tests
# ============================================================================


class TestExtractGitSubcmd:
    """Tests for git subcommand extraction from Bash tool events."""

    def test_git_commit(self, observe_module):
        event = {"tool_name": "Bash", "tool_input": "git commit -m 'fix bug'"}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        assert subcmd == "commit"

    def test_git_push(self, observe_module):
        event = {"tool_name": "Bash", "tool_input": "git push origin main"}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        assert subcmd == "push"

    def test_git_checkout(self, observe_module):
        event = {"tool_name": "Bash", "tool_input": "git checkout -b feature"}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        assert subcmd == "checkout"

    def test_git_switch(self, observe_module):
        event = {"tool_name": "Bash", "tool_input": "git switch develop"}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        assert subcmd == "switch"

    def test_git_status(self, observe_module):
        event = {"tool_name": "Bash", "tool_input": "git status"}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        assert subcmd == "status"

    def test_non_git_command(self, observe_module):
        event = {"tool_name": "Bash", "tool_input": "ls -la"}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        assert subcmd is None

    def test_non_bash_tool(self, observe_module):
        event = {"tool_name": "Write", "tool_input": "git commit"}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        assert subcmd is None

    def test_git_in_pipeline(self, observe_module):
        event = {"tool_name": "Bash", "tool_input": "cd repo && git pull origin main"}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        assert subcmd == "pull"

    def test_empty_tool_input(self, observe_module):
        event = {"tool_name": "Bash", "tool_input": ""}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        assert subcmd is None

    def test_dict_tool_input(self, observe_module):
        """tool_input can be a dict (e.g. {"command": "git status"})."""
        event = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        subcmd, cmd = observe_module._extract_git_subcmd(event)
        # str(dict) contains "git status" so it should match
        assert subcmd == "status"


# ============================================================================
# _emit_git_event tests
# ============================================================================


class TestEmitGitEvent:
    """Tests for git-specific event emission."""

    def test_emit_commit_with_message(self, observe_module, emitter):
        em, output = emitter
        # Monkey-patch the module's emitter
        observe_module._emit_git_event(em, "commit", "git commit -m 'fix: resolve bug'")
        output.seek(0)
        event = json.loads(output.readline())
        assert event["event_type"] == "git_commit"
        assert event["context"]["message"] == "fix: resolve bug"

    def test_emit_commit_no_message(self, observe_module, emitter):
        em, output = emitter
        observe_module._emit_git_event(em, "commit", "git commit --amend")
        output.seek(0)
        event = json.loads(output.readline())
        assert event["event_type"] == "git_commit"

    def test_emit_push_with_remote_branch(self, observe_module, emitter):
        em, output = emitter
        observe_module._emit_git_event(em, "push", "git push origin feature-x")
        output.seek(0)
        event = json.loads(output.readline())
        assert event["event_type"] == "git_push"
        assert event["context"]["remote"] == "origin"
        assert event["context"]["branch"] == "feature-x"

    def test_emit_push_bare(self, observe_module, emitter):
        em, output = emitter
        observe_module._emit_git_event(em, "push", "git push")
        output.seek(0)
        event = json.loads(output.readline())
        assert event["context"]["remote"] == "origin"

    def test_emit_checkout_branch(self, observe_module, emitter):
        em, output = emitter
        observe_module._emit_git_event(em, "checkout", "git checkout develop")
        output.seek(0)
        event = json.loads(output.readline())
        assert event["event_type"] == "git_branch_changed"
        assert event["context"]["to_branch"] == "develop"

    def test_emit_switch_branch(self, observe_module, emitter):
        em, output = emitter
        observe_module._emit_git_event(em, "switch", "git switch -c new-branch")
        output.seek(0)
        event = json.loads(output.readline())
        assert event["event_type"] == "git_branch_changed"

    def test_emit_generic_pull(self, observe_module, emitter):
        em, output = emitter
        observe_module._emit_git_event(em, "pull", "git pull origin main")
        output.seek(0)
        event = json.loads(output.readline())
        assert event["event_type"] == "git_operation"
        assert event["context"]["operation"] == "pull"

    def test_emit_generic_rebase(self, observe_module, emitter):
        em, output = emitter
        observe_module._emit_git_event(em, "rebase", "git rebase main")
        output.seek(0)
        event = json.loads(output.readline())
        assert event["event_type"] == "git_operation"
        assert event["context"]["operation"] == "rebase"

    def test_emit_generic_stash(self, observe_module, emitter):
        em, output = emitter
        observe_module._emit_git_event(em, "stash", "git stash pop")
        output.seek(0)
        event = json.loads(output.readline())
        assert event["event_type"] == "git_operation"
        assert event["context"]["operation"] == "stash"


# ============================================================================
# Handler subprocess tests (never-block contract)
# ============================================================================


class TestObserveHandlerNeverBlocks:
    """The observe.py handler must NEVER block — exit 0, no stdout output."""

    def _run_handler(self, event: dict | str | None) -> dict:
        if not OBSERVE_PATH.exists():
            pytest.skip(f"observe.py not found at {OBSERVE_PATH}")

        if event is None:
            input_bytes = b""
        elif isinstance(event, str):
            input_bytes = event.encode()
        else:
            input_bytes = json.dumps(event).encode()

        result = subprocess.run(
            [sys.executable, str(OBSERVE_PATH)],
            input=input_bytes,
            capture_output=True,
            timeout=10,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.decode(),
            "stderr": result.stderr.decode(),
        }

    def test_exit_zero_on_valid_event(self):
        event = {
            "session_id": "test-001",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": "git commit -m 'test'",
            "tool_use_id": "toolu_001",
        }
        result = self._run_handler(event)
        assert result["returncode"] == 0
        # stdout has JSONL events (hook events are on stdout for stream capture)
        # stderr must be empty (never writes non-event data to stderr)
        assert result["stderr"] == ""

    def test_exit_zero_on_empty_input(self):
        result = self._run_handler(None)
        assert result["returncode"] == 0
        assert result["stdout"] == ""

    def test_exit_zero_on_malformed_json(self):
        result = self._run_handler("{{not json")
        assert result["returncode"] == 0
        assert result["stdout"] == ""

    def test_exit_zero_on_unknown_hook(self):
        event = {"session_id": "x", "hook_event_name": "UnknownHook"}
        result = self._run_handler(event)
        assert result["returncode"] == 0
        assert result["stdout"] == ""

    def test_git_commit_emits_to_stdout(self):
        event = {
            "session_id": "test-stdout",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": "git commit -m 'hello'",
            "tool_use_id": "toolu_stdout",
        }
        result = self._run_handler(event)
        assert result["returncode"] == 0
        assert result["stderr"] == ""  # nothing on stderr
        # stdout should have JSONL events (tool_started + git_commit)
        lines = [line for line in result["stdout"].strip().split("\n") if line.strip()]
        assert len(lines) >= 2  # tool_started + git_commit
        types = [json.loads(line)["event_type"] for line in lines]
        assert "tool_execution_started" in types
        assert "git_commit" in types

    def test_git_push_emits_to_stdout(self):
        event = {
            "session_id": "test-push",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": "git push origin main",
            "tool_use_id": "toolu_push",
        }
        result = self._run_handler(event)
        assert result["returncode"] == 0
        lines = [line for line in result["stdout"].strip().split("\n") if line.strip()]
        types = [json.loads(line)["event_type"] for line in lines]
        assert "git_push" in types

    def test_non_git_bash_no_git_events(self):
        event = {
            "session_id": "test-nongit",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": "ls -la",
            "tool_use_id": "toolu_ls",
        }
        result = self._run_handler(event)
        lines = [line for line in result["stdout"].strip().split("\n") if line.strip()]
        types = [json.loads(line)["event_type"] for line in lines]
        assert "tool_execution_started" in types
        assert not any(t.startswith("git_") for t in types)


# ============================================================================
# Parallel plugin compatibility
# ============================================================================


class TestParallelPluginCompatibility:
    """Verify observability plugin can run alongside SDLC plugin."""

    SDLC_HANDLERS = (
        Path(__file__).parent.parent.parent.parent.parent
        / "plugins"
        / "sdlc"
        / "hooks"
        / "handlers"
    )

    def test_both_plugins_handle_same_event_independently(self):
        """Both plugins process the same PreToolUse event without conflict."""
        if not OBSERVE_PATH.exists():
            pytest.skip("observe.py not found")
        sdlc_handler = self.SDLC_HANDLERS / "pre-tool-use.py"
        if not sdlc_handler.exists():
            pytest.skip("SDLC pre-tool-use.py not found")

        event = {
            "session_id": "test-parallel",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "tool_use_id": "toolu_parallel",
        }
        input_bytes = json.dumps(event).encode()

        # Run both handlers
        obs_result = subprocess.run(
            [sys.executable, str(OBSERVE_PATH)],
            input=input_bytes,
            capture_output=True,
            timeout=10,
        )
        sdlc_result = subprocess.run(
            [sys.executable, str(sdlc_handler)],
            input=input_bytes,
            capture_output=True,
            timeout=10,
        )

        # Observability: exit 0, no stderr (events go to stdout for stream capture, never blocks)
        assert obs_result.returncode == 0
        assert obs_result.stderr.decode().strip() == ""

        # SDLC: exit 0, safe command allowed (no deny output)
        assert sdlc_result.returncode == 0

    def test_observability_never_blocks_dangerous_command(self):
        """Even for dangerous commands, observability only observes — SDLC blocks."""
        if not OBSERVE_PATH.exists():
            pytest.skip("observe.py not found")

        event = {
            "session_id": "test-dangerous",
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": "rm -rf /",
            "tool_use_id": "toolu_danger",
        }
        input_bytes = json.dumps(event).encode()

        obs_result = subprocess.run(
            [sys.executable, str(OBSERVE_PATH)],
            input=input_bytes,
            capture_output=True,
            timeout=10,
        )

        # Observability MUST NOT block — events on stdout (JSONL), no stderr, exit 0
        assert obs_result.returncode == 0
        assert obs_result.stderr.decode().strip() == ""
