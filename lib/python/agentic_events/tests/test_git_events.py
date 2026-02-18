"""Tests for git event types and emitter methods."""

import io
import json

import pytest

from agentic_events import EventEmitter, EventType

pytestmark = pytest.mark.unit


class TestGitEventTypes:
    """Verify git event types exist and have correct values."""

    def test_git_commit_type(self):
        assert EventType.GIT_COMMIT == "git_commit"

    def test_git_push_type(self):
        assert EventType.GIT_PUSH == "git_push"

    def test_git_branch_changed_type(self):
        assert EventType.GIT_BRANCH_CHANGED == "git_branch_changed"

    def test_git_operation_type(self):
        assert EventType.GIT_OPERATION == "git_operation"


class TestGitCommitEmitter:
    """Tests for git_commit emitter method."""

    def test_basic_commit(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_commit(message="fix: resolve bug")

        assert event["event_type"] == "git_commit"
        assert event["context"]["operation"] == "commit"
        assert event["context"]["message"] == "fix: resolve bug"

    def test_commit_with_sha_and_branch(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_commit(message="feat: add feature", sha="abc1234", branch="main")

        assert event["context"]["sha"] == "abc1234"
        assert event["context"]["branch"] == "main"

    def test_commit_message_truncated(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        long_msg = "x" * 500
        event = emitter.git_commit(message=long_msg)

        assert len(event["context"]["message"]) == 200

    def test_commit_empty_message(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_commit()

        assert event["event_type"] == "git_commit"
        assert "message" not in event["context"]

    def test_commit_jsonl_output(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        emitter.git_commit(message="test")

        output.seek(0)
        parsed = json.loads(output.readline())
        assert parsed["event_type"] == "git_commit"


class TestGitPushEmitter:
    """Tests for git_push emitter method."""

    def test_basic_push(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_push(remote="origin", branch="main")

        assert event["event_type"] == "git_push"
        assert event["context"]["operation"] == "push"
        assert event["context"]["remote"] == "origin"
        assert event["context"]["branch"] == "main"

    def test_push_defaults(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_push()

        assert event["context"]["remote"] == "origin"
        assert event["context"]["branch"] == ""


class TestGitBranchChangedEmitter:
    """Tests for git_branch_changed emitter method."""

    def test_branch_change(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_branch_changed(from_branch="main", to_branch="feature-x")

        assert event["event_type"] == "git_branch_changed"
        assert event["context"]["operation"] == "branch_change"
        assert event["context"]["from_branch"] == "main"
        assert event["context"]["to_branch"] == "feature-x"

    def test_branch_change_partial(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_branch_changed(to_branch="develop")

        assert event["context"]["to_branch"] == "develop"
        assert event["context"]["from_branch"] == ""


class TestGitOperationEmitter:
    """Tests for git_operation (generic) emitter method."""

    def test_generic_operation(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_operation(operation="pull", details="git pull origin main")

        assert event["event_type"] == "git_operation"
        assert event["context"]["operation"] == "pull"
        assert event["context"]["details"] == "git pull origin main"

    def test_operation_details_truncated(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        long_details = "x" * 1000
        event = emitter.git_operation(operation="log", details=long_details)

        assert len(event["context"]["details"]) == 500

    def test_operation_no_details(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_operation(operation="stash")

        assert "details" not in event["context"]

    @pytest.mark.parametrize("op", ["pull", "merge", "rebase", "stash", "fetch", "clone", "log", "diff", "status"])
    def test_various_operations(self, op):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_operation(operation=op)

        assert event["context"]["operation"] == op


class TestGitEventsIntegration:
    """Integration tests: git events mixed with regular events produce valid JSONL."""

    def test_mixed_events_jsonl(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-mix", output=output)

        emitter.session_started()
        emitter.tool_started("Bash", "toolu_1", "git commit -m 'fix'")
        emitter.git_commit(message="fix")
        emitter.tool_completed("Bash", "toolu_1", success=True, duration_ms=50)
        emitter.tool_started("Bash", "toolu_2", "git push origin main")
        emitter.git_push(remote="origin", branch="main")
        emitter.tool_completed("Bash", "toolu_2", success=True, duration_ms=200)
        emitter.session_completed()

        output.seek(0)
        lines = output.readlines()
        assert len(lines) == 8

        types = []
        for line in lines:
            event = json.loads(line)
            assert "event_type" in event
            assert "timestamp" in event
            assert event["session_id"] == "test-mix"
            types.append(event["event_type"])

        assert "git_commit" in types
        assert "git_push" in types
        assert "session_started" in types
        assert "session_completed" in types
