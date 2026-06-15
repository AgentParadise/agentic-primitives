"""Typed event payloads for git observability hooks.

Zero external dependencies - stdlib dataclasses only.
These types are the single source of truth for git event structure.
Downstream consumers (syn-domain, syn-adapters, syn-api, dashboard) depend
on these field names flowing through the pipeline unchanged.

Usage:
    >>> payload = GitCommitPayload(sha="abc123", branch="main", message="fix bug")
    >>> payload.to_dict()
    {'operation': 'commit', 'sha': 'abc123', 'branch': 'main', 'message': 'fix bug'}
"""

from __future__ import annotations

from dataclasses import dataclass, fields


def _strip_empty(dc: object) -> dict[str, object]:
    """Serialize a dataclass, omitting falsy fields (empty string, 0, False, None).

    This matches the existing emitter behavior where the git hook methods
    only include fields that have truthy values in the JSONL context dict.
    The ``operation`` field is always included as it serves as the event
    type discriminator.
    """
    result: dict[str, object] = {}
    for f in fields(dc):  # type: ignore[arg-type]
        val = getattr(dc, f.name)
        if f.name == "operation" or val:
            result[f.name] = val
    return result


# ---------------------------------------------------------------------------
# Git event payloads
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GitCommitPayload:
    """Payload for git_commit events."""

    operation: str = "commit"
    sha: str = ""
    branch: str = ""
    repo: str = ""
    message: str = ""
    author: str = ""
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    estimated_tokens_added: int = 0
    estimated_tokens_removed: int = 0

    def to_dict(self) -> dict[str, object]:
        return _strip_empty(self)


@dataclass(frozen=True, slots=True)
class GitPushPayload:
    """Payload for git_push events."""

    operation: str = "push"
    remote: str = "origin"
    branch: str = ""
    sha: str = ""
    repo: str = ""
    remote_url: str = ""
    commits_count: int = 0
    commit_range: str = ""

    def to_dict(self) -> dict[str, object]:
        return _strip_empty(self)


@dataclass(frozen=True, slots=True)
class GitCheckoutPayload:
    """Payload for git_checkout events."""

    operation: str = "checkout"
    branch: str = ""
    prev_branch: str = ""
    sha: str = ""
    is_clone: bool = False
    repo: str = ""

    def to_dict(self) -> dict[str, object]:
        return _strip_empty(self)


@dataclass(frozen=True, slots=True)
class GitBranchChangedPayload:
    """Payload for git_branch_changed events."""

    operation: str = "branch_change"
    from_branch: str = ""
    to_branch: str = ""

    def to_dict(self) -> dict[str, object]:
        return _strip_empty(self)


@dataclass(frozen=True, slots=True)
class GitMergePayload:
    """Payload for git_merge events."""

    operation: str = "merge"
    branch: str = ""
    sha: str = ""
    repo: str = ""

    def to_dict(self) -> dict[str, object]:
        return _strip_empty(self)


@dataclass(frozen=True, slots=True)
class GitRewritePayload:
    """Payload for git_rewrite events."""

    operation: str = "rebase"
    sha: str = ""
    branch: str = ""
    repo: str = ""

    def to_dict(self) -> dict[str, object]:
        return _strip_empty(self)


@dataclass(frozen=True, slots=True)
class GitOperationPayload:
    """Payload for generic git_operation events."""

    operation: str = ""
    details: str = ""

    def to_dict(self) -> dict[str, object]:
        return _strip_empty(self)


# Union of all git payload types for type annotations
GitPayload = (
    GitCommitPayload
    | GitPushPayload
    | GitCheckoutPayload
    | GitBranchChangedPayload
    | GitMergePayload
    | GitRewritePayload
    | GitOperationPayload
)
