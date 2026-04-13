"""Tests for git event types and emitter methods."""

import io
import json

import pytest

from agentic_events import EventEmitter, EventType
from agentic_events.payloads import (
    GitBranchChangedPayload,
    GitCheckoutPayload,
    GitCommitPayload,
    GitMergePayload,
    GitOperationPayload,
    GitPushPayload,
    GitRewritePayload,
)

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


class TestGitPayloads:
    """Tests for typed payload dataclasses."""

    def test_commit_payload_to_dict_strips_defaults(self):
        payload = GitCommitPayload(sha="abc123", branch="main", message="fix bug")
        d = payload.to_dict()
        assert d == {"operation": "commit", "sha": "abc123", "branch": "main", "message": "fix bug"}
        assert "repo" not in d
        assert "files_changed" not in d

    def test_commit_payload_with_metadata(self):
        payload = GitCommitPayload(
            sha="abc",
            branch="main",
            repo="myrepo",
            files_changed=3,
            insertions=10,
            deletions=2,
        )
        d = payload.to_dict()
        assert d["files_changed"] == 3
        assert d["insertions"] == 10
        assert d["deletions"] == 2
        assert d["repo"] == "myrepo"

    def test_push_payload_strips_defaults(self):
        payload = GitPushPayload(branch="main", sha="abc123")
        d = payload.to_dict()
        assert d == {"operation": "push", "remote": "origin", "branch": "main", "sha": "abc123"}

    def test_checkout_payload(self):
        payload = GitCheckoutPayload(branch="feat", sha="abc", is_clone=True, operation="clone")
        d = payload.to_dict()
        assert d["operation"] == "clone"
        assert d["is_clone"] is True

    def test_branch_changed_payload(self):
        payload = GitBranchChangedPayload(from_branch="main", to_branch="feat")
        d = payload.to_dict()
        assert d == {"operation": "branch_change", "from_branch": "main", "to_branch": "feat"}

    def test_merge_payload(self):
        payload = GitMergePayload(branch="main", sha="abc")
        d = payload.to_dict()
        assert d == {"operation": "merge", "branch": "main", "sha": "abc"}

    def test_rewrite_payload(self):
        payload = GitRewritePayload(operation="amend", sha="abc")
        d = payload.to_dict()
        assert d == {"operation": "amend", "sha": "abc"}

    def test_generic_operation_payload(self):
        payload = GitOperationPayload(operation="stash")
        d = payload.to_dict()
        assert d == {"operation": "stash"}

    def test_empty_payload_only_has_operation(self):
        payload = GitCommitPayload()
        d = payload.to_dict()
        assert d == {"operation": "commit"}

    def test_payloads_are_frozen(self):
        payload = GitCommitPayload(sha="abc")
        with pytest.raises(AttributeError):
            payload.sha = "def"  # type: ignore[misc]


class TestGitCommitEmitter:
    """Tests for git_commit emitter method."""

    def test_basic_commit(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_commit(message="fix: resolve bug")

        assert event["event_type"] == "git_commit"
        git = event["context"]["git"]
        assert git["operation"] == "commit"
        assert git["message"] == "fix: resolve bug"

    def test_commit_with_sha_and_branch(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_commit(message="feat: add feature", sha="abc1234", branch="main")

        git = event["context"]["git"]
        assert git["sha"] == "abc1234"
        assert git["branch"] == "main"

    def test_commit_message_truncated(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        long_msg = "x" * 500
        event = emitter.git_commit(message=long_msg)

        assert len(event["context"]["git"]["message"]) == 200

    def test_commit_empty_message(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_commit()

        assert event["event_type"] == "git_commit"
        git = event["context"]["git"]
        assert "message" not in git  # empty string stripped by to_dict()

    def test_commit_jsonl_output(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        emitter.git_commit(message="test")

        output.seek(0)
        parsed = json.loads(output.readline())
        assert parsed["event_type"] == "git_commit"
        assert "git" in parsed["context"]

    def test_commit_metadata_flows_to_payload(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_commit(
            message="fix",
            sha="abc",
            branch="main",
            repo="myrepo",
            files_changed=3,
            insertions=10,
            deletions=2,
            author="neural",
        )

        git = event["context"]["git"]
        assert git["repo"] == "myrepo"
        assert git["files_changed"] == 3
        assert git["insertions"] == 10
        assert git["deletions"] == 2
        assert git["author"] == "neural"

    def test_commit_unknown_metadata_goes_to_metadata_key(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_commit(message="fix", custom_field="custom_value")

        # Unknown kwargs should flow to metadata, not context.git
        assert event.get("metadata", {}).get("custom_field") == "custom_value"
        assert "custom_field" not in event["context"]["git"]


class TestGitPushEmitter:
    """Tests for git_push emitter method."""

    def test_basic_push(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_push(remote="origin", branch="main")

        assert event["event_type"] == "git_push"
        git = event["context"]["git"]
        assert git["operation"] == "push"
        assert git["remote"] == "origin"
        assert git["branch"] == "main"

    def test_push_defaults(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_push()

        git = event["context"]["git"]
        assert git["remote"] == "origin"
        # branch="" is stripped by to_dict()
        assert "branch" not in git

    def test_push_with_sha_and_repo(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_push(branch="main", sha="abc123", repo="myrepo")

        git = event["context"]["git"]
        assert git["sha"] == "abc123"
        assert git["repo"] == "myrepo"


class TestGitBranchChangedEmitter:
    """Tests for git_branch_changed emitter method."""

    def test_branch_change(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_branch_changed(from_branch="main", to_branch="feature-x")

        assert event["event_type"] == "git_branch_changed"
        git = event["context"]["git"]
        assert git["operation"] == "branch_change"
        assert git["from_branch"] == "main"
        assert git["to_branch"] == "feature-x"

    def test_branch_change_partial(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_branch_changed(to_branch="develop")

        git = event["context"]["git"]
        assert git["to_branch"] == "develop"
        assert "from_branch" not in git  # empty string stripped


class TestGitOperationEmitter:
    """Tests for git_operation (generic) emitter method."""

    def test_generic_operation(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_operation(operation="pull", details="git pull origin main")

        assert event["event_type"] == "git_operation"
        git = event["context"]["git"]
        assert git["operation"] == "pull"
        assert git["details"] == "git pull origin main"

    def test_operation_details_truncated(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        long_details = "x" * 1000
        event = emitter.git_operation(operation="log", details=long_details)

        assert len(event["context"]["git"]["details"]) == 500

    def test_operation_no_details(self):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_operation(operation="stash")

        assert "details" not in event["context"]["git"]

    @pytest.mark.parametrize(
        "op", ["pull", "merge", "rebase", "stash", "fetch", "clone", "log", "diff", "status"]
    )
    def test_various_operations(self, op):
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-git", output=output)

        event = emitter.git_operation(operation=op)

        assert event["context"]["git"]["operation"] == op


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

    def test_git_events_have_structured_context(self):
        """All git events must have context.git sub-object."""
        output = io.StringIO()
        emitter = EventEmitter(session_id="test-struct", output=output)

        emitter.git_commit(sha="a1b2", message="fix")
        emitter.git_push(branch="main", sha="a1b2")
        emitter.git_checkout(branch="feat", sha="c3d4")
        emitter.git_branch_changed(from_branch="main", to_branch="feat")
        emitter.git_merge(branch="main", merge_sha="e5f6")
        emitter.git_rewrite(rewrite_type="rebase", sha="g7h8")
        emitter.git_operation(operation="stash")

        output.seek(0)
        for line in output.readlines():
            event = json.loads(line)
            assert "git" in event["context"], f"{event['event_type']} missing context.git"
            git = event["context"]["git"]
            assert "operation" in git, f"{event['event_type']} missing git.operation"
