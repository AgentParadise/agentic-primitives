---
description: Manage git worktrees in isolated sibling directory
argument-hint: <create|list|status|remove> [name] [branch] [base-branch]
model: sonnet
allowed-tools: Bash, Skill
---

# Worktree

Thin entry point for the `sdlc:git-worktree` skill. The skill owns the logic
(parsing, naming, the executable); this command just routes a slash invocation
to it with the user's arguments.

## Action

Invoke the **`sdlc:git-worktree`** skill, passing `$ARGUMENTS` through as the
`<action> [name] [branch] [base-branch]` it expects. The skill drives
`scripts/worktree.sh` to create, list, inspect, or remove worktrees in the
sibling `../<repo>_worktrees/` directory.

If `$ARGUMENTS` is empty, ask which action the user wants
(`create`, `list`, `status`, `remove`).

## Examples

```
/sdlc:git_worktree create auth-refactor      # new branch + YYYYMMDD_auth-refactor dir
/sdlc:git_worktree create PR#42              # check out PR #42's branch in isolation
/sdlc:git_worktree create feat/user-settings # dir YYYYMMDD_user-settings, branch feat/user-settings
/sdlc:git_worktree list                      # list all worktrees
/sdlc:git_worktree status                    # branch, changes, ahead/behind, PR per worktree
/sdlc:git_worktree remove 20260608_auth-refactor
```

## Integration Points

- Pairs with `/sdlc:git_push` for pushing from worktree branches.
- Use `/sdlc:commit` inside a worktree for structured commits.
- The `git` skill cross-references this skill for worktree operations.
