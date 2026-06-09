---
name: git-worktree
description: Create, list, inspect, and remove git worktrees in an isolated sibling directory so each agent session works in its own repo context. Use when the user wants to "create a worktree", "spin up a worktree", "work on a PR in isolation", "check out PR#N in a worktree", "list/clean up worktrees", "parallel branch workspace", or "isolated workspace for a feature". Triggers on "worktree", "git worktree", "isolated checkout", "sibling workspace", "parallel feature branch". Do NOT use for general push/merge/fetch/PR-lifecycle git work (use the `git` skill), for plain branch creation without a separate directory, or for a single simple commit (use `commit`).
---

# Git Worktree

## When to Use (and When NOT to Use)

Use when:
- You want a feature branch to live in its own directory so the current workspace stays untouched (parallel agent sessions, long-running experiments).
- You need to check out a PR's branch in isolation to test or build on it.
- You want to list, inspect (branch / changes / ahead-behind / PR), or clean up existing worktrees.

Do NOT use when:
- The operation is push, merge, fetch, or PR lifecycle — use the `git` skill.
- You just need a new branch in the same directory — `git checkout -b` is enough.
- You are committing staged changes — use `commit`.

## Input

- A git repository (the script resolves the toplevel itself).
- For `create`: a name, branch ref, or PR reference. Optional explicit branch and base branch.
- For `create`/`status` from a PR: `gh` authenticated for the repo (optional — falls back gracefully).

## Workflow

All actions are driven by the bundled script, which enforces the sibling-directory layout and `YYYYMMDD_<kebab-case>` naming. Pass the user's arguments straight through:

```bash
${CLAUDE_PLUGIN_ROOT}/skills/git-worktree/scripts/worktree.sh <action> [name] [branch] [base-branch]
```

1. **Parse intent into an action.** Map the request to one of `create`, `list`, `status`, `remove`. If ambiguous, ask which.
2. **Run the script** with the parsed arguments. It handles base-branch auto-detection (`origin/HEAD`), PR-ref lookup via `gh`, branch-prefix stripping for clean directory names, and existing-branch reuse (remote → local → new).
3. **For `remove`, confirm the target first** when the user gave a partial or fuzzy name — the script force-removes and prunes, which is hard to undo. It refuses ambiguous fuzzy matches and warns about uncommitted changes before removing, but still show `list` output and confirm before running.
4. **Report** the resulting path and branch. After `create`, tell the user to `cd` into the printed path to start working.

Input parsing the script applies on `create`:
- `PR#42` / `#42` → resolves the PR's head via `gh`, fetches `pull/42/head` into a local branch (works for fork PRs too), dir becomes `YYYYMMDD_<branch-without-prefix>`.
- `feat/foo` (or `fix/`, `chore/`, `hotfix/`, `release/`) → uses it as the branch, strips the prefix for the dir name.
- Plain text → kebab-cased as both dir slug and (by default) branch name.

## Output

- A worktree directory under `../<repo>_worktrees/` (on `create`), or a removed/listed/inspected worktree.
- Plain-text status to stdout; exit `0` on success, `1` on failure.
- No commits, no pushes — worktrees share the repo's `.git`, so all branches are visible across them.

## Outcomes we are looking for

- **Each agent session is isolated.** Concurrent work happens in separate directories with no checkout thrash on the main workspace.
- **Worktree names are predictable.** Every directory is `YYYYMMDD_<kebab-case>`, so listings sort chronologically and never collide with the repo itself.

## Recommended tools and practices (as of 2026-06-08)

### For: each agent session is isolated
- **Keep worktrees as siblings, never nested inside the repo.** The script enforces `../<repo>_worktrees/`; a worktree inside the repo confuses tooling and git status.
- **One worktree per concurrent task.** Pairs with parallel-agent dispatch — each agent gets its own directory and branch.

### For: predictable, low-friction cleanup
- **Remove worktrees when the branch merges.** Use `remove`, then verify with `list`; the script prunes stale metadata automatically.
- **Use `status` before cleanup** to spot uncommitted changes or unmerged commits in a worktree you are about to delete.

## References

- `scripts/worktree.sh`: the executable that performs all four actions. Self-contained; safe to run directly.
- The `git` skill (same plugin) covers push / merge / fetch / PR lifecycle and cross-references this skill for worktree work.
