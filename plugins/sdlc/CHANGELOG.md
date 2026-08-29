# Changelog

## 1.4.1
- Apply current ruff formatting to `hooks/validators/security/file.py` and `hooks/validators/security/python.py` (line wrapping only, no behavior change). CI installed ruff unpinned, so a newer ruff release turned the hook-format check red without any code change; the workflow now pins `ruff==0.14.6`.

## 1.4.0
- Add `git-worktree` skill: create/list/status/remove worktrees in a sibling `<repo>_worktrees/` dir, backed by `scripts/worktree.sh`
- `git_worktree` command is now a thin wrapper that invokes the `git-worktree` skill
- `git` skill cross-references `git-worktree` for worktree operations
- Robustness (from Codex review of #198): `create PR#N` fetches `pull/N/head` so fork PRs check out the actual PR code; `remove` refuses ambiguous fuzzy matches and warns on uncommitted changes; `status` guards against stale/missing worktree dirs under `set -e`

## 1.0.0
- Consolidated from core/security, devops/git, devops/config, qa/quality, testing/expert, review/prioritize, and workflow/merge-cycle
