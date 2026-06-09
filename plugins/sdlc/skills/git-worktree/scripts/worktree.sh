#!/usr/bin/env bash
# Manage git worktrees in a sibling `<repo>_worktrees/` directory so each agent
# session stays in an isolated repo context.
#
# Usage: worktree.sh <create|list|status|remove> [name] [branch] [base-branch]
#   create <name|branch|PR#N> [branch] [base]  Create worktree + feature branch
#   list                                       List all worktrees
#   status                                     Branch, changes, ahead/behind, PR per worktree
#   remove <name|path>                         Remove a worktree and prune
#
# Naming: worktree dirs are forced to `YYYYMMDD_<kebab-case-name>`.
# Output is plain text; exit 0 on success, 1 on failure.
set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_NAME=$(basename "$REPO_ROOT")
WORKTREE_DIR="$(dirname "$REPO_ROOT")/${REPO_NAME}_worktrees"
DATE_PREFIX=$(date +%Y%m%d)

ACTION="${1:-}"

usage() {
  cat <<EOF
=== Worktree Manager ===
Repo: ${REPO_NAME}
Worktree dir: ${WORKTREE_DIR}

Usage: worktree.sh <create|list|status|remove> [name] [branch] [base-branch]

Actions:
  create  <name>        Create worktree + feature branch
  list                  List all worktrees
  status                Show branch, changes, PR info per worktree
  remove  <name>        Remove a worktree
EOF
}

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g; s/--*/-/g; s/^-//; s/-$//'
}

strip_prefix() {
  echo "$1" | sed -E 's|^(feat|fix|chore|hotfix|release)/||'
}

cmd_create() {
  local input="${1:-}" explicit_branch="${2:-}" explicit_base="${3:-}"
  if [ -z "$input" ]; then
    echo "Usage: worktree.sh create <name|branch|PR#N>" >&2
    exit 1
  fi

  # Auto-detect default base branch unless overridden
  local base_branch
  if [ -n "$explicit_base" ]; then
    base_branch="$explicit_base"
  else
    base_branch=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' || true)
    if [ -z "$base_branch" ]; then
      base_branch="main"
      echo "Could not detect default branch, falling back to: ${base_branch}"
    fi
  fi

  local branch_name dir_slug worktree_name

  if echo "$input" | grep -qE '^(PR)?#[0-9]+$'; then
    # PR reference: PR#<N> or #<N>
    local pr_num pr_branch
    pr_num=$(echo "$input" | grep -oE '[0-9]+')
    echo "Fetching branch for PR #${pr_num}..."
    pr_branch=$(gh pr view "$pr_num" --json headRefName -q '.headRefName' 2>/dev/null || true)
    if [ -z "$pr_branch" ]; then
      echo "Could not find PR #${pr_num}" >&2
      exit 1
    fi
    branch_name="$pr_branch"
    dir_slug=$(strip_prefix "$pr_branch")
    worktree_name="${DATE_PREFIX}_${dir_slug}"
    echo "PR #${pr_num} -> branch: ${pr_branch}"
  elif echo "$input" | grep -qE '^(feat|fix|chore|hotfix|release)/'; then
    # Branch-like input: feat/..., fix/..., etc.
    branch_name="$input"
    dir_slug=$(strip_prefix "$input")
    worktree_name="${DATE_PREFIX}_${dir_slug}"
  else
    # Plain text: use as name, create new branch
    dir_slug=$(slugify "$input")
    worktree_name="${DATE_PREFIX}_${dir_slug}"
    branch_name="${explicit_branch:-${dir_slug}}"
  fi

  echo ""
  echo "=== Creating Worktree ==="
  echo "Directory: ${worktree_name}"
  echo "Branch: ${branch_name}"
  echo "Base: ${base_branch}"

  mkdir -p "$WORKTREE_DIR"
  git fetch origin

  if git show-ref --verify --quiet "refs/remotes/origin/${branch_name}" 2>/dev/null; then
    echo "Branch exists on remote, checking out..."
    git worktree add "$WORKTREE_DIR/$worktree_name" "$branch_name"
  elif git show-ref --verify --quiet "refs/heads/${branch_name}" 2>/dev/null; then
    echo "Branch exists locally, checking out..."
    git worktree add "$WORKTREE_DIR/$worktree_name" "$branch_name"
  else
    echo "Creating new branch from origin/${base_branch}..."
    git worktree add -b "$branch_name" "$WORKTREE_DIR/$worktree_name" "origin/$base_branch"
  fi

  echo ""
  echo "Worktree created: ${WORKTREE_DIR}/${worktree_name}"
  echo "Branch: ${branch_name} (from ${base_branch})"
  echo "Path: ${WORKTREE_DIR}/${worktree_name}"
}

cmd_list() {
  echo ""
  echo "=== Worktrees ==="
  git worktree list
}

cmd_status() {
  echo ""
  echo "=== Worktree Status ==="

  git worktree list --porcelain | grep '^worktree ' | sed 's/^worktree //' | while read -r wt_path; do
    echo ""
    echo "--- $(basename "$wt_path") ---"
    echo "Path: ${wt_path}"

    local branch changes ahead_behind ahead behind pr_info
    branch=$(cd "$wt_path" && git branch --show-current 2>/dev/null || true)
    echo "Branch: ${branch:-"(detached)"}"

    changes=$(cd "$wt_path" && git status --short 2>/dev/null | wc -l | tr -d ' ')
    if [ "$changes" -gt 0 ]; then
      echo "Changes: ${changes} file(s) modified"
    else
      echo "Changes: clean"
    fi

    ahead_behind=$(cd "$wt_path" && git rev-list --left-right --count HEAD...@{u} 2>/dev/null || true)
    if [ -n "$ahead_behind" ]; then
      ahead=$(echo "$ahead_behind" | awk '{print $1}')
      behind=$(echo "$ahead_behind" | awk '{print $2}')
      echo "Ahead: ${ahead}  Behind: ${behind}"
    fi

    if command -v gh &>/dev/null && [ -n "$branch" ]; then
      pr_info=$(gh pr list --head "$branch" --json number,state,title \
        --jq 'if length == 0 then "none" else "PR #\(.[0].number) [\(.[0].state)] \(.[0].title)" end' 2>/dev/null || true)
      if [ -n "$pr_info" ]; then
        echo "PR: ${pr_info}"
      else
        echo "PR: none"
      fi
    fi
  done
}

cmd_remove() {
  local target="${1:-}"
  if [ -z "$target" ]; then
    echo "Usage: worktree.sh remove <name>" >&2
    echo ""
    echo "Available worktrees:" >&2
    git worktree list >&2
    exit 1
  fi

  local wt_path match
  if [ -d "$WORKTREE_DIR/$target" ]; then
    wt_path="$WORKTREE_DIR/$target"
  elif [ -d "$target" ]; then
    wt_path="$target"
  else
    match=$(ls -d "$WORKTREE_DIR"/*"$target"* 2>/dev/null | head -1 || true)
    if [ -n "$match" ]; then
      wt_path="$match"
      echo "Matched: $(basename "$wt_path")"
    else
      echo "Worktree not found: ${target}" >&2
      echo ""
      echo "Available worktrees:" >&2
      git worktree list >&2
      exit 1
    fi
  fi

  echo "=== Removing Worktree ==="
  echo "Path: ${wt_path}"

  git worktree remove --force "$wt_path"
  git worktree prune
  echo "Worktree removed: $(basename "$wt_path")"
}

case "$ACTION" in
  create) cmd_create "${2:-}" "${3:-}" "${4:-}" ;;
  list)   cmd_list ;;
  status) cmd_status ;;
  remove) cmd_remove "${2:-}" ;;
  ""|-h|--help|help) usage; [ -z "$ACTION" ] && exit 1 || exit 0 ;;
  *) echo "Unknown action: ${ACTION}" >&2; echo ""; usage >&2; exit 1 ;;
esac
