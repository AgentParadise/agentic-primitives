"""Integration tests for git observability hooks.

These tests exercise the actual shell hook scripts end-to-end by creating
real git repositories, installing the hooks, and running git commands.
Events emitted to stderr are captured and validated.

Requires: git CLI available in PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Path to the workspace hooks
HOOKS_DIR = Path(__file__).resolve().parents[4] / "plugins" / "workspace" / "hooks" / "git"

# Path to the agentic_events package
PACKAGE_DIR = Path(__file__).resolve().parents[1]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("git") is None,
        reason="git CLI not available",
    ),
]


def _install_hooks(repo_dir: Path) -> None:
    """Install the workspace git hooks into the repo's .git/hooks/."""
    hooks_dest = repo_dir / ".git" / "hooks"
    hooks_dest.mkdir(parents=True, exist_ok=True)
    for hook_name in ("post-commit", "post-rewrite", "post-merge", "pre-push"):
        src = HOOKS_DIR / hook_name
        if src.exists():
            dst = hooks_dest / hook_name
            shutil.copy2(src, dst)
            dst.chmod(dst.stat().st_mode | stat.S_IEXEC)


def _git(
    repo_dir: Path, *args: str, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    """Run a git command in the given repo, capturing stderr for event parsing."""
    env = os.environ.copy()
    # Ensure agentic_events is importable by the hook scripts
    env["PYTHONPATH"] = str(PACKAGE_DIR) + (
        (":" + env.get("PYTHONPATH", "")) if env.get("PYTHONPATH") else ""
    )
    env["CLAUDE_SESSION_ID"] = "test-integration"
    env["GIT_AUTHOR_NAME"] = "Test User"
    env["GIT_AUTHOR_EMAIL"] = "test@example.com"
    env["GIT_COMMITTER_NAME"] = "Test User"
    env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    if env_extra:
        env.update(env_extra)

    return subprocess.run(
        ["git", *args],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _parse_events(stderr: str) -> list[dict]:
    """Parse JSONL events from stderr output."""
    events = []
    for line in stderr.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _init_repo(tmp_path: Path) -> Path:
    """Create and initialize a git repo with hooks installed."""
    repo = tmp_path / "test-repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "test@example.com")
    _install_hooks(repo)
    return repo


class TestGitCommitHook:
    """Test the post-commit hook emits GIT_COMMIT events."""

    def test_basic_commit(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)

        # Create a file and commit
        (repo / "hello.txt").write_text("hello world\n")
        _git(repo, "add", "hello.txt")
        result = _git(repo, "commit", "-m", "initial commit")

        assert result.returncode == 0, f"git commit failed: {result.stderr}"
        events = _parse_events(result.stderr)
        commit_events = [e for e in events if e.get("event_type") == "git_commit"]
        assert len(commit_events) == 1

        ctx = commit_events[0]["context"]
        assert ctx["branch"] == "main"
        assert ctx["repo"] == "test-repo"
        assert ctx["message_preview"] == "initial commit"
        assert ctx["author"] == "Test User <test@example.com>"
        assert "sha" in ctx and len(ctx["sha"]) == 40

    def test_commit_with_changes_has_stats(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)

        # First commit
        (repo / "file.txt").write_text("line1\nline2\nline3\n")
        _git(repo, "add", "file.txt")
        _git(repo, "commit", "-m", "first")

        # Second commit with changes
        (repo / "file.txt").write_text("line1\nmodified\nline3\nnew line\n")
        _git(repo, "add", "file.txt")
        result = _git(repo, "commit", "-m", "modify file")

        events = _parse_events(result.stderr)
        commit_events = [e for e in events if e.get("event_type") == "git_commit"]
        assert len(commit_events) == 1

        ctx = commit_events[0]["context"]
        assert ctx["files_changed"] >= 1
        assert ctx["insertions"] >= 1 or ctx["deletions"] >= 1

    def test_commit_has_token_estimates(self, tmp_path: Path) -> None:
        """Verify estimated_tokens_added/removed are present (ADR-022)."""
        repo = _init_repo(tmp_path)

        (repo / "code.py").write_text("def hello():\n    return 'world'\n")
        _git(repo, "add", "code.py")
        _git(repo, "commit", "-m", "first")

        (repo / "code.py").write_text(
            "def hello():\n    return 'universe'\n\ndef goodbye():\n    pass\n"
        )
        _git(repo, "add", "code.py")
        result = _git(repo, "commit", "-m", "update code")

        events = _parse_events(result.stderr)
        commit_events = [e for e in events if e.get("event_type") == "git_commit"]
        assert len(commit_events) == 1

        ctx = commit_events[0]["context"]
        assert "estimated_tokens_added" in ctx
        assert "estimated_tokens_removed" in ctx
        assert isinstance(ctx["estimated_tokens_added"], int)
        assert isinstance(ctx["estimated_tokens_removed"], int)
        # There should be some tokens since we changed content
        assert ctx["estimated_tokens_added"] > 0 or ctx["estimated_tokens_removed"] > 0

    def test_session_id_propagated(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)

        (repo / "f.txt").write_text("x\n")
        _git(repo, "add", "f.txt")
        result = _git(repo, "commit", "-m", "test session id")

        events = _parse_events(result.stderr)
        commit_events = [e for e in events if e.get("event_type") == "git_commit"]
        assert len(commit_events) == 1
        assert commit_events[0]["session_id"] == "test-integration"


class TestGitRewriteHook:
    """Test the post-rewrite hook emits GIT_REWRITE events."""

    def test_amend_emits_rewrite(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)

        (repo / "file.txt").write_text("original\n")
        _git(repo, "add", "file.txt")
        _git(repo, "commit", "-m", "original commit")

        old_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

        (repo / "file.txt").write_text("amended\n")
        _git(repo, "add", "file.txt")
        result = _git(repo, "commit", "--amend", "-m", "amended commit")

        assert result.returncode == 0, f"amend failed: {result.stderr}"

        events = _parse_events(result.stderr)
        rewrite_events = [e for e in events if e.get("event_type") == "git_rewrite"]
        assert len(rewrite_events) >= 1

        ctx = rewrite_events[0]["context"]
        assert ctx["rewrite_type"] == "amend"
        assert len(ctx["mappings"]) >= 1
        assert ctx["mappings"][0]["old_sha"] == old_sha

    def test_rebase_emits_rewrite(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)

        # Create base commit
        (repo / "base.txt").write_text("base\n")
        _git(repo, "add", "base.txt")
        _git(repo, "commit", "-m", "base")

        # Create feature branch with commits
        _git(repo, "checkout", "-b", "feature")
        (repo / "feat1.txt").write_text("feat1\n")
        _git(repo, "add", "feat1.txt")
        _git(repo, "commit", "-m", "feat1")

        (repo / "feat2.txt").write_text("feat2\n")
        _git(repo, "add", "feat2.txt")
        _git(repo, "commit", "-m", "feat2")

        # Add a commit on main so rebase has work to do
        _git(repo, "checkout", "main")
        (repo / "main2.txt").write_text("main2\n")
        _git(repo, "add", "main2.txt")
        _git(repo, "commit", "-m", "main2")

        # Rebase feature onto main
        _git(repo, "checkout", "feature")
        result = _git(repo, "rebase", "main")

        assert result.returncode == 0, f"rebase failed: {result.stderr}"

        events = _parse_events(result.stderr)
        rewrite_events = [e for e in events if e.get("event_type") == "git_rewrite"]
        assert len(rewrite_events) >= 1

        ctx = rewrite_events[0]["context"]
        assert ctx["rewrite_type"] == "rebase"
        assert len(ctx["mappings"]) >= 2  # Two commits were rebased


class TestGitMergeHook:
    """Test the post-merge hook emits GIT_MERGE events."""

    def test_merge_emits_event(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)

        # Base commit on main
        (repo / "base.txt").write_text("base\n")
        _git(repo, "add", "base.txt")
        _git(repo, "commit", "-m", "base")

        # Create branch and add commits
        _git(repo, "checkout", "-b", "feature")
        (repo / "feature.txt").write_text("feature\n")
        _git(repo, "add", "feature.txt")
        _git(repo, "commit", "-m", "add feature")

        # Switch back to main and merge
        _git(repo, "checkout", "main")
        result = _git(repo, "merge", "feature", "--no-ff", "-m", "merge feature")

        assert result.returncode == 0, f"merge failed: {result.stderr}"

        events = _parse_events(result.stderr)
        merge_events = [e for e in events if e.get("event_type") == "git_merge"]
        assert len(merge_events) == 1

        ctx = merge_events[0]["context"]
        assert ctx["branch"] == "main"
        assert ctx["commits_merged"] >= 1
        assert ctx["is_squash"] is False
        assert len(ctx["merge_sha"]) == 40
