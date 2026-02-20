---
description: Git workflows — push, merge, PR lifecycle, worktrees, branch management, and CI integration. Invoke for any git operation beyond a simple commit.
argument-hint: "[push|merge|worktree|fetch|pr] [options]"
model: sonnet
allowed-tools: Bash, Read
---

# Git Workflows

Handles the full git collaboration lifecycle: pushing branches, waiting for CI, merging PRs, managing worktrees, and syncing remotes.

For individual granular git commands (explicit user control), see the `/sdlc:git_*` slash commands.

## Variables

ACTION: $1 || ""        # push | merge | worktree | fetch | pr | auto-detect
BRANCH: $2 || ""        # target branch (auto-detected if blank)
OPTIONS: $ARGUMENTS     # pass-through flags

## Workflow

### Detect intent

If ACTION is blank, infer from context:
- Staged commits ready → `push`
- PR open and CI green → `merge`
- Need isolated feature work → `worktree`
- Behind remote → `fetch`

### Push

1. Get current branch
2. Push to origin, setting upstream if needed (`git push -u origin <branch>`)
3. Wait for CI via `gh pr checks` — poll every 30s, timeout 600s
4. Report: ✅ CI passed / ❌ failed with details / ⚠️ timeout

### Merge PR

1. Verify current branch is not main/master
2. Check CI is green (`gh pr checks`) — block if failures
3. Check review status (`gh pr view --json reviewDecision`) — warn if not approved
4. Merge via `gh pr merge --squash` (default) or `--merge` / `--rebase`
5. Delete remote branch, pull main, delete local branch

### Worktree (isolated feature branches)

1. Determine worktree base dir (sibling to repo root, e.g. `../repo_worktrees/`)
2. Create branch: `git worktree add ../repo_worktrees/<name> -b <branch>`
3. Report the path — agent or human navigates there to work in isolation

### Fetch & sync

1. `git fetch --prune` to update remote refs
2. Report branches behind remote
3. If on main/master: `git pull --rebase`

### Set attributions

Configure commit author for bot/agent contexts:
```bash
git config user.name "<name>"
git config user.email "<email>"
```

## Report

```markdown
## Git: <action>

**Branch:** <branch>
**Remote:** origin

| Step | Status | Detail |
|------|--------|--------|
| Push | ✅/❌ | |
| CI   | ✅/❌/⚠️ | |
| Merge | ✅/❌/— | |

**Next:** <suggested next step>
```
