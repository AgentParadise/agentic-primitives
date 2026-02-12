---
description: Manage git worktrees in isolated sibling directory
argument-hint: <create|list|status|remove> [name] [branch] [base-branch]
model: sonnet
allowed-tools: Bash
---

# Worktree

Manage git worktrees in a sibling directory to keep each Claude session in a single isolated repo context.

## Purpose

*Level 3 (Control Flow)*

Create, list, inspect, and remove git worktrees. Worktrees are stored in `../<repo-name>_worktrees/` as sibling directories so each agent context stays isolated.

## Variables

ACTION: $1                        # create, list, status, remove
NAME: $2                          # Worktree/branch name or PR#<N>
BRANCH: $3                        # Explicit branch (optional)
BASE_BRANCH: $4                   # Base branch override (optional)

## Instructions

- Always create worktrees in the sibling `_worktrees/` directory, never inside the repo
- Enforce `YYYYMMDD_<kebab-case-name>` directory naming
- Smart-parse NAME: PR references, branch prefixes, or plain text
- Auto-detect default branch via `git symbolic-ref refs/remotes/origin/HEAD`
- Strip common branch prefixes (`feat/`, `fix/`, `chore/`, `hotfix/`, `release/`) for cleaner dir names

## Workflow

### 1. Setup

```bash
REPO_NAME=$(basename "$(git rev-parse --show-toplevel)")
REPO_ROOT=$(git rev-parse --show-toplevel)
WORKTREE_DIR="$(dirname "$REPO_ROOT")/${REPO_NAME}_worktrees"
ACTION="$1"
DATE_PREFIX=$(date +%Y%m%d)

echo "=== Worktree Manager ==="
echo "Repo: ${REPO_NAME}"
echo "Worktree dir: ${WORKTREE_DIR}"

if [ -z "$ACTION" ]; then
  echo ""
  echo "Usage: /worktree <create|list|status|remove> [name] [branch] [base-branch]"
  echo ""
  echo "Actions:"
  echo "  create  <name>        Create worktree + feature branch"
  echo "  list                  List all worktrees"
  echo "  status                Show branch, changes, PR info per worktree"
  echo "  remove  <name>        Remove a worktree"
  exit 1
fi
```

### 2. Route Action

Dispatch to the matching action handler below.

### Action: create

Parse the input to determine the directory name and branch:

```bash
INPUT="$2"
EXPLICIT_BRANCH="$3"
EXPLICIT_BASE="$4"

if [ -z "$INPUT" ]; then
  echo "Usage: /worktree create <name|branch|PR#N>"
  exit 1
fi

# Auto-detect default branch
if [ -n "$EXPLICIT_BASE" ]; then
  BASE_BRANCH="$EXPLICIT_BASE"
else
  BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
  if [ -z "$BASE_BRANCH" ]; then
    BASE_BRANCH="main"
    echo "Could not detect default branch, falling back to: ${BASE_BRANCH}"
  fi
fi

# --- Smart input parsing ---

# PR reference: PR#<N> or #<N>
if echo "$INPUT" | grep -qE '^(PR)?#[0-9]+$'; then
  PR_NUM=$(echo "$INPUT" | grep -oE '[0-9]+')
  echo "Fetching branch for PR #${PR_NUM}..."
  PR_BRANCH=$(gh pr view "$PR_NUM" --json headRefName -q '.headRefName' 2>/dev/null)
  if [ -z "$PR_BRANCH" ]; then
    echo "Could not find PR #${PR_NUM}"
    exit 1
  fi
  BRANCH_NAME="$PR_BRANCH"
  # Strip prefix for dir name
  DIR_SLUG=$(echo "$PR_BRANCH" | sed -E 's|^(feat|fix|chore|hotfix|release)/||')
  WORKTREE_NAME="${DATE_PREFIX}_${DIR_SLUG}"
  echo "PR #${PR_NUM} -> branch: ${PR_BRANCH}"

# Branch-like input: feat/..., fix/..., etc.
elif echo "$INPUT" | grep -qE '^(feat|fix|chore|hotfix|release)/'; then
  BRANCH_NAME="$INPUT"
  DIR_SLUG=$(echo "$INPUT" | sed -E 's|^(feat|fix|chore|hotfix|release)/||')
  WORKTREE_NAME="${DATE_PREFIX}_${DIR_SLUG}"

# Plain text: use as name, create new branch
else
  # Enforce kebab-case
  DIR_SLUG=$(echo "$INPUT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')
  WORKTREE_NAME="${DATE_PREFIX}_${DIR_SLUG}"
  BRANCH_NAME="${EXPLICIT_BRANCH:-${DIR_SLUG}}"
fi

echo ""
echo "=== Creating Worktree ==="
echo "Directory: ${WORKTREE_NAME}"
echo "Branch: ${BRANCH_NAME}"
echo "Base: ${BASE_BRANCH}"

mkdir -p "$WORKTREE_DIR"
git fetch origin

# Check if branch already exists on remote
if git show-ref --verify --quiet "refs/remotes/origin/${BRANCH_NAME}" 2>/dev/null; then
  echo "Branch exists on remote, checking out..."
  git worktree add "$WORKTREE_DIR/$WORKTREE_NAME" "$BRANCH_NAME"
# Check if branch exists locally
elif git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}" 2>/dev/null; then
  echo "Branch exists locally, checking out..."
  git worktree add "$WORKTREE_DIR/$WORKTREE_NAME" "$BRANCH_NAME"
else
  echo "Creating new branch from origin/${BASE_BRANCH}..."
  git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR/$WORKTREE_NAME" "origin/$BASE_BRANCH"
fi

if [ $? -ne 0 ]; then
  echo "Worktree creation failed"
  exit 1
fi

echo ""
echo "Worktree created: ${WORKTREE_DIR}/${WORKTREE_NAME}"
echo "Branch: ${BRANCH_NAME} (from ${BASE_BRANCH})"
echo "Path: ${WORKTREE_DIR}/${WORKTREE_NAME}"
```

### Action: list

```bash
echo ""
echo "=== Worktrees ==="
git worktree list
```

### Action: status

```bash
echo ""
echo "=== Worktree Status ==="

git worktree list --porcelain | grep '^worktree ' | sed 's/^worktree //' | while read -r WT_PATH; do
  echo ""
  echo "--- $(basename "$WT_PATH") ---"
  echo "Path: ${WT_PATH}"

  BRANCH=$(cd "$WT_PATH" && git branch --show-current 2>/dev/null)
  echo "Branch: ${BRANCH:-"(detached)"}"

  # Uncommitted changes
  CHANGES=$(cd "$WT_PATH" && git status --short 2>/dev/null | wc -l | tr -d ' ')
  if [ "$CHANGES" -gt 0 ]; then
    echo "Changes: ${CHANGES} file(s) modified"
  else
    echo "Changes: clean"
  fi

  # Ahead/behind
  AHEAD_BEHIND=$(cd "$WT_PATH" && git rev-list --left-right --count HEAD...@{u} 2>/dev/null)
  if [ -n "$AHEAD_BEHIND" ]; then
    AHEAD=$(echo "$AHEAD_BEHIND" | awk '{print $1}')
    BEHIND=$(echo "$AHEAD_BEHIND" | awk '{print $2}')
    echo "Ahead: ${AHEAD}  Behind: ${BEHIND}"
  fi

  # PR info
  if command -v gh &>/dev/null && [ -n "$BRANCH" ]; then
    PR_INFO=$(gh pr list --head "$BRANCH" --json number,state,title --jq '.[0] | "PR #\(.number) [\(.state)] \(.title)"' 2>/dev/null)
    if [ -n "$PR_INFO" ]; then
      echo "PR: ${PR_INFO}"
    else
      echo "PR: none"
    fi
  fi
done
```

### Action: remove

```bash
TARGET="$2"

if [ -z "$TARGET" ]; then
  echo "Usage: /worktree remove <name>"
  echo ""
  echo "Available worktrees:"
  git worktree list
  exit 1
fi

# Resolve full path — support both bare name and full path
if [ -d "$WORKTREE_DIR/$TARGET" ]; then
  WT_PATH="$WORKTREE_DIR/$TARGET"
elif [ -d "$TARGET" ]; then
  WT_PATH="$TARGET"
else
  # Try partial match on directory name
  MATCH=$(ls -d "$WORKTREE_DIR"/*"$TARGET"* 2>/dev/null | head -1)
  if [ -n "$MATCH" ]; then
    WT_PATH="$MATCH"
    echo "Matched: $(basename "$WT_PATH")"
  else
    echo "Worktree not found: ${TARGET}"
    echo ""
    echo "Available worktrees:"
    git worktree list
    exit 1
  fi
fi

echo "=== Removing Worktree ==="
echo "Path: ${WT_PATH}"

git worktree remove --force "$WT_PATH"

if [ $? -ne 0 ]; then
  echo "Failed to remove worktree"
  exit 1
fi

git worktree prune
echo "Worktree removed: $(basename "$WT_PATH")"
```

## Report

```markdown
## Worktree Operation Complete

**Action:** ${ACTION}
**Repo:** ${REPO_NAME}
**Worktree dir:** ${WORKTREE_DIR}

### Result

| Step | Status |
|------|--------|
| ${ACTION} | Done |

### Current Worktrees

<output of git worktree list>

### Next Steps

- After create: `cd <worktree-path>` and start working
- After remove: verify with `/worktree list`
- Use `/worktree status` to see branch and PR info across all worktrees
```

## Examples

### Example 1: Create from plain text
```
/worktree create auth-refactor
```
Creates `YYYYMMDD_auth-refactor` with branch `auth-refactor` from default base.

### Example 2: Create from PR
```
/worktree create PR#42
```
Fetches the branch for PR #42, creates worktree with date-prefixed dir name.

### Example 3: Create from branch name
```
/worktree create feat/user-settings
```
Uses `feat/user-settings` as branch, creates dir `YYYYMMDD_user-settings`.

### Example 4: Create with explicit base branch
```
/worktree create my-fix bugfix/login-error develop
```
Creates branch `bugfix/login-error` from `develop` in dir `YYYYMMDD_my-fix`.

### Example 5: List worktrees
```
/worktree list
```

### Example 6: Status of all worktrees
```
/worktree status
```
Shows branch, uncommitted changes, ahead/behind, and PR info for each worktree.

### Example 7: Remove a worktree
```
/worktree remove 20260212_auth-refactor
```
Force-removes the worktree and prunes stale entries.

## Integration Points

- Pairs with `/devops/push` for pushing from worktree branches
- Use `/devops/commit` inside a worktree for structured commits
- Worktrees share the same `.git` — all branches are visible across worktrees
