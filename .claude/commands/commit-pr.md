# /commit-pr - Commit, Push, and Create Pull Request

Automated workflow for committing changes, pushing to remote, and creating a pull request with proper formatting and checks.

## Prerequisites

- [ ] Changes are complete and tested
- [ ] QA checks pass (`/qa` command)
- [ ] Working on a feature branch (not `main`)

## Workflow

### Step 1: Check Current State

Run these commands in parallel:

```bash
# Git status and diff
git status --short
git diff --stat

# Recent commits (for message style reference)
git log --oneline -5

# Current branch
git branch --show-current
```

### Step 2: Stage Changes

Stage only relevant changes, excluding:
- Temporary files
- Draft project plans
- Build artifacts
- Cache files
- Screenshots from testing

```bash
# Stage specific files
git add <files...>

# Or stage all (then unstage unwanted)
git add .
git reset <unwanted_files...>
```

### Step 3: Create Feature Branch (if on main)

```bash
# Create and switch to feature branch
git checkout -b feature/<feature-name>
```

Use descriptive branch names:
- `feature/ui-feedback-module`
- `fix/api-error-handling`
- `docs/update-readme`

### Step 4: Commit with Conventional Commit Format

**Format:** `type(scope): description`

**Types:**
- `feat`: New features
- `fix`: Bug fixes
- `docs`: Documentation
- `style`: Formatting changes (no code change)
- `refactor`: Code restructuring
- `test`: Test changes
- `chore`: Maintenance/build changes

**Example commit using HEREDOC for proper formatting:**

```bash
git commit -m "$(cat <<'EOF'
feat(ui-feedback): add reusable feedback module with React widget

This commit introduces a self-contained UI feedback module that can be plugged
into multiple user interfaces. The module consists of:

Backend (Python/FastAPI):
- PostgreSQL storage with in-memory fallback for development
- CRUD endpoints for feedback items with media attachments

Frontend (React):
- FeedbackProvider context with configuration
- FeedbackWidget floating button with menu
- FeedbackModal with compact UX

Note: Element highlighting in Pin mode is still in progress.
EOF
)"
```

### Step 5: Push to Remote

```bash
# Push with upstream tracking
git push -u origin <branch-name>
```

### Step 6: Create Pull Request

Use `gh` CLI to create PR with proper formatting:

```bash
gh pr create --title "feat(scope): short description" --body "$(cat <<'EOF'
## Summary
- Bullet point 1
- Bullet point 2
- Bullet point 3

## Features
### Backend
- Feature description
- Another feature

### Frontend
- UI feature
- Component description

## Known Issues
- Any known limitations or WIP items

## Test Plan
- [x] QA pipeline passed (lint, type-check, tests)
- [x] Manual testing of feature X
- [ ] Further testing needed for Y
EOF
)"
```

### Step 7: Monitor CI Checks

```bash
# Check PR status
gh pr checks <pr-number>

# View CI logs if failed
gh run view <run-id> --log-failed
```

### Step 8: Address Review Comments

```bash
# List comments
gh pr view <pr-number> --json comments

# Make fixes, commit, push
git add .
git commit -m "fix: address review comments"
git push
```

## Commit Message Guidelines

### Good Examples

```
feat(auth): add JWT token refresh mechanism

Implements automatic token refresh when access token expires.
This prevents users from being logged out unexpectedly.

- Add refreshToken endpoint
- Implement token interceptor
- Add refresh retry logic with exponential backoff
```

```
fix(api): resolve race condition in concurrent requests

Multiple simultaneous requests could cause data corruption
when updating the same resource.

- Add optimistic locking with version field
- Return 409 on conflict
```

### Bad Examples

```
❌ update code
❌ fix bug
❌ wip
❌ changes
```

## PR Description Template

```markdown
## Summary
Brief description of what this PR does (1-3 bullet points)

## Changes
### Category 1
- Specific change
- Another change

### Category 2
- Change description

## Breaking Changes
- List any breaking changes (or "None")

## Test Plan
- [x] Unit tests pass
- [x] Manual testing completed
- [ ] Performance testing (if applicable)

## Screenshots
(If applicable, add screenshots or videos)

## Related Issues
Fixes #123
Related to #456
```

## Checklist Before Creating PR

- [ ] Branch is up to date with main
- [ ] All tests pass locally (`/qa` command)
- [ ] Code follows project style guidelines
- [ ] Commit messages follow conventional format
- [ ] PR description is complete
- [ ] No sensitive data in commits

## Troubleshooting

### CI Failed

```bash
# Check which job failed
gh pr checks <pr-number>

# Get logs for failed job
gh run view <run-id> --log-failed

# Common fixes:
# - Lock file out of sync: npm install / pnpm install
# - Type errors: fix types and push
# - Lint errors: run formatter and push
```

### Need to Amend Commit

```bash
# Amend last commit (no new message)
git commit --amend --no-edit

# Amend with new message
git commit --amend -m "new message"

# Force push (be careful!)
git push --force-with-lease
```

### Wrong Branch

```bash
# Create branch from current state
git checkout -b feature/correct-name

# Reset main to upstream
git checkout main
git reset --hard origin/main
```

---

**Always run `/qa` before this workflow to ensure code quality.**
