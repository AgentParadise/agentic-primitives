#!/bin/bash
# =============================================================================
# Agentic Workspace Entrypoint
# =============================================================================
#
# This script runs when the container starts (AFTER any tmpfs mounts).
# It configures the workspace from environment variables, then execs to CMD.
#
# Plugin Architecture (ADR-033):
#   Plugins are baked into /opt/agentic/plugins/ at build time. This entrypoint
#   discovers them and builds --plugin-dir flags for Claude CLI. Each plugin
#   directory contains .claude-plugin/plugin.json and hooks/hooks.json using
#   ${CLAUDE_PLUGIN_ROOT} for portable path resolution.
#
# Environment Variables (provided by orchestrator):
#   CLAUDE_CODE_OAUTH_TOKEN - OAuth token for Claude CLI (preferred, cheaper)
#   ANTHROPIC_API_KEY       - Claude API key (fallback if no OAuth token)
#   GIT_AUTHOR_NAME         - Git commit author name (required for git ops)
#   GIT_AUTHOR_EMAIL        - Git commit author email (required for git ops)
#   GITHUB_TOKEN            - GitHub token for git push (optional)
#   SYN_OPERATOR_NAME       - Operator display name for Co-authored-by trailer (optional)
#   SYN_OPERATOR_EMAIL      - Operator email matching a verified GitHub account (optional)
#
# This script is the SINGLE SOURCE OF TRUTH for workspace configuration.
# Orchestrators should NOT have hardcoded setup scripts.
#
# See: agentic-primitives/docs/adrs/033-plugin-native-workspace-images.md
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# 1. Claude CLI Configuration
# -----------------------------------------------------------------------------
# Create ~/.claude/settings.json with LSP plugins enabled.
# This must be done HERE because /home/agent is a tmpfs mount that wipes
# anything baked into the Docker image.
#
# NOTE: Hooks are NO LONGER configured here. They are loaded automatically
# via --plugin-dir flags from the baked-in plugins at /opt/agentic/plugins/.
# This ensures identical hook behavior between local and Docker environments.
#
# LSP plugins (pyright-lsp, typescript-lsp, rust-analyzer-lsp) are enabled by
# default. The LSP servers are LAZY — they only start when Claude encounters
# files in the matching language, so enabling all three does not waste memory
# when only a subset of languages is present in the workspace.

mkdir -p ~/.claude

cat > ~/.claude/settings.json << 'EOF'
{
  "attribution": {
    "commit": "",
    "pr": ""
  },
  "enabledPlugins": {
    "pyright-lsp@claude-plugins-official": true,
    "typescript-lsp@claude-plugins-official": true,
    "rust-analyzer-lsp@claude-plugins-official": true
  }
}
EOF

chmod 600 ~/.claude/settings.json

# -----------------------------------------------------------------------------
# 2. Plugin Discovery (ADR-033)
# -----------------------------------------------------------------------------
# Scan /opt/agentic/plugins/ for valid plugin directories and build
# --plugin-dir flags. A valid plugin has .claude-plugin/plugin.json.
# These flags are stored in AGENTIC_PLUGIN_FLAGS for the orchestrator
# to append when invoking claude CLI.

PLUGIN_FLAGS=""
PLUGINS_DIR="${AGENTIC_PLUGINS_DIR:-/opt/agentic/plugins}"

if [ -d "$PLUGINS_DIR" ]; then
    for plugin_dir in "$PLUGINS_DIR"/*/; do
        if [ -f "${plugin_dir}.claude-plugin/plugin.json" ]; then
            plugin_name=$(basename "$plugin_dir")
            PLUGIN_FLAGS="${PLUGIN_FLAGS} --plugin-dir ${plugin_dir%/}"
            echo "[entrypoint] Discovered plugin: ${plugin_name}" >&2
        fi
    done
fi

# Export for orchestrator use (e.g., agentic-isolation can read this)
export AGENTIC_PLUGIN_FLAGS="${PLUGIN_FLAGS}"

# Also write to a file for easy sourcing by scripts
echo "${PLUGIN_FLAGS}" > /tmp/.agentic-plugin-flags

# -----------------------------------------------------------------------------
# 3. Git Configuration
# -----------------------------------------------------------------------------
# Configure git identity from environment variables.
# These are required for any git commit/push operations.

if [ -n "${GIT_AUTHOR_NAME}" ]; then
    git config --global user.name "${GIT_AUTHOR_NAME}"
    git config --global user.email "${GIT_AUTHOR_EMAIL:-agent@agentic.local}"
    git config --global init.defaultBranch main
fi

# Install workspace git hooks globally (ADR-043).
#
# core.hooksPath is a git global config that overrides the per-repo .git/hooks/
# directory. Setting it here (at container startup) means our hooks fire for
# EVERY repo cloned or initialized inside this container — including repos
# cloned by the agent mid-task.
#
# Two contributing sources, composed into a single runtime directory:
#   1. /opt/agentic/git-hooks/                          — workspace-shipped
#      hooks. Owned by the claude-cli provider itself (this dir is baked in
#      by the Dockerfile from providers/workspaces/claude-cli/scripts/git-hooks/).
#      Currently: prepare-commit-msg for operator Co-authored-by attribution
#      (driven by SYN_OPERATOR_NAME / SYN_OPERATOR_EMAIL env vars; no-op when
#      either is unset).
#   2. /opt/agentic/plugins/observability/hooks/git/    — event-emission hooks
#      from the observability plugin (post-commit, pre-push, post-merge,
#      post-rewrite, post-checkout). These emit JSONL to stderr; the docker
#      exec stream in AgenticEventStreamAdapter merges stderr→stdout, and
#      WorkflowExecutionEngine stores the events in TimescaleDB.
#
# Workspace-shipped hooks are linked first so any future name collision
# resolves in favor of the observability event emitters (rare, but explicit).
GIT_HOOKS_DIR="${HOME}/.git-hooks"
mkdir -p "${GIT_HOOKS_DIR}"

for src_dir in \
    /opt/agentic/git-hooks \
    "${AGENTIC_PLUGINS_DIR:-/opt/agentic/plugins}/observability/hooks/git"; do
    [ -d "${src_dir}" ] || continue
    for src in "${src_dir}"/*; do
        [ -f "${src}" ] || continue
        name=$(basename "${src}")
        case "${name}" in install.py|*.md|*.txt) continue ;; esac
        ln -sf "${src}" "${GIT_HOOKS_DIR}/${name}"
    done
done

if [ -n "$(ls -A "${GIT_HOOKS_DIR}" 2>/dev/null)" ]; then
    git config --global core.hooksPath "${GIT_HOOKS_DIR}"
    echo "[entrypoint] Workspace git hooks composed at ${GIT_HOOKS_DIR}" >&2
fi

# Also set committer identity (git uses both for commits)
if [ -n "${GIT_COMMITTER_NAME:-}" ]; then
    export GIT_COMMITTER_NAME
    export GIT_COMMITTER_EMAIL="${GIT_COMMITTER_EMAIL:-${GIT_AUTHOR_EMAIL:-agent@agentic.local}}"
elif [ -n "${GIT_AUTHOR_NAME}" ]; then
    export GIT_COMMITTER_NAME="${GIT_AUTHOR_NAME}"
    export GIT_COMMITTER_EMAIL="${GIT_AUTHOR_EMAIL:-agent@agentic.local}"
fi

# -----------------------------------------------------------------------------
# 4. GitHub Credentials
# -----------------------------------------------------------------------------
# Store GitHub token in git credential helper and gh CLI config.
# This persists credentials for git push after env vars are cleared.

if [ -n "${GITHUB_TOKEN}" ]; then
    # Git credential helper
    git config --global credential.helper store
    echo "https://x-access-token:${GITHUB_TOKEN}@github.com" > ~/.git-credentials
    chmod 600 ~/.git-credentials

    # GitHub CLI config
    mkdir -p ~/.config/gh
    cat > ~/.config/gh/hosts.yml << GHEOF
github.com:
    oauth_token: ${GITHUB_TOKEN}
    user: ${GIT_AUTHOR_NAME:-agent}
    git_protocol: https
GHEOF
    chmod 600 ~/.config/gh/hosts.yml
fi

# -----------------------------------------------------------------------------
# 5. Workspace Directories
# -----------------------------------------------------------------------------
# Ensure workspace directories exist (should be pre-created in image,
# but verify in case of custom mounts)

mkdir -p /workspace/artifacts/input
mkdir -p /workspace/artifacts/output
mkdir -p /workspace/repos

# Create writable CARGO_HOME for the agent user
# The Rust toolchain binaries live in /usr/local/cargo/bin (read-only, on PATH),
# but cargo needs a writable CARGO_HOME for registry index, git checkouts, etc.
mkdir -p ~/.cargo

# -----------------------------------------------------------------------------
# 5.5 Workspace Context Composition
# -----------------------------------------------------------------------------
# Universal inbound seam — copies orchestrator-supplied context, plugins,
# and subagents from /etc/agentic/workspace/ (bind-mounted read-only) into
# the agent-visible workspace + Claude config locations. Skips silently when
# the bind-mount is absent so existing deployments stay backwards-compatible.
#
# See: docs/workspace.md and ADR-035 for the contract this implements.

# --- Configuration constants ---------------------------------------------
readonly INJECT_MOUNT="/etc/agentic/workspace"
readonly INJECT_MOUNT_PLUGINS="${INJECT_MOUNT}/plugins"
readonly INJECT_MOUNT_AGENTS="${INJECT_MOUNT}/agents"

readonly INJECT_TARGET_CONTEXT="/workspace/CLAUDE.md"
readonly INJECT_TARGET_PLUGINS="/workspace/.agentic-plugins"
readonly INJECT_TARGET_AGENTS="${HOME}/.claude/agents"

readonly INJECT_DEFAULT_CONTEXT="CLAUDE.md"
readonly INJECT_PLUGIN_MANIFEST=".claude-plugin/plugin.json"

# --- Helpers --------------------------------------------------------------
# Reject any name containing '/' or '..' so plugin/agent names supplied
# via env can't escape the intended mount via path traversal. Caller
# pipes a stream of names through this filter.
__inject_safe_filter() {
    while IFS= read -r name; do
        [ -n "${name}" ] || continue
        case "${name}" in
            *[!a-zA-Z0-9._-]*|*..*|.*|"") continue ;;
        esac
        printf '%s\n' "${name}"
    done
}

__inject_names() {
    local explicit="$1" dir="$2" strip_ext="${3:-}"
    if [ -n "${explicit}" ]; then
        printf '%s\n' "${explicit}" | tr ':' '\n' | __inject_safe_filter
        return
    fi
    [ -d "${dir}" ] || return
    for f in "${dir}"/*${strip_ext}; do
        [ -e "${f}" ] || continue
        local base; base="$(basename "${f}")"
        [ -n "${strip_ext}" ] && base="${base%${strip_ext}}"
        printf '%s\n' "${base}" | __inject_safe_filter
    done
}

__inject_safe_context() {
    local context="$1"
    case "${context}" in
        *[!a-zA-Z0-9._-]*|*..*|.*|"") return 1 ;;
    esac
    return 0
}

__capability_provider_safe() {
    local provider="$1"
    case "${provider}" in
        *[!a-zA-Z0-9._-]*|*..*|.*|"") return 1 ;;
    esac
    return 0
}

# --- Actions --------------------------------------------------------------
if [ -d "${INJECT_MOUNT}" ]; then
    ctx_name="${AGENTIC_WORKSPACE_CONTEXT:-${INJECT_DEFAULT_CONTEXT}}"
    if __inject_safe_context "${ctx_name}" && [ -f "${INJECT_MOUNT}/${ctx_name}" ]; then
        ctx_src="${INJECT_MOUNT}/${ctx_name}"
        cp "${ctx_src}" "${INJECT_TARGET_CONTEXT}"
        # 600 because orchestrators may embed credentials or
        # private guidance in the workspace context. Matches the mode
        # used for ~/.claude/settings.json and ~/.git-credentials above.
        chmod 600 "${INJECT_TARGET_CONTEXT}"
    fi

    if [ -d "${INJECT_MOUNT_PLUGINS}" ]; then
        mkdir -p "${INJECT_TARGET_PLUGINS}"
        while IFS= read -r plugin; do
            [ -n "${plugin}" ] || continue
            src="${INJECT_MOUNT_PLUGINS}/${plugin}"
            [ -f "${src}/${INJECT_PLUGIN_MANIFEST}" ] || continue
            # rm first → idempotent across re-runs when /workspace is a
            # persistent named volume. Without the rm, `cp -a src dst`
            # against an existing dst/ creates a nested dst/<basename>/
            # tree instead of overwriting.
            rm -rf "${INJECT_TARGET_PLUGINS}/${plugin}"
            cp -a "${src}" "${INJECT_TARGET_PLUGINS}/${plugin}"
            AGENTIC_PLUGIN_FLAGS="${AGENTIC_PLUGIN_FLAGS} --plugin-dir ${INJECT_TARGET_PLUGINS}/${plugin}"
        done < <(__inject_names "${AGENTIC_WORKSPACE_PLUGINS:-}" "${INJECT_MOUNT_PLUGINS}")
        export AGENTIC_PLUGIN_FLAGS
    fi

    if [ -d "${INJECT_MOUNT_AGENTS}" ]; then
        mkdir -p "${INJECT_TARGET_AGENTS}"
        while IFS= read -r agent; do
            [ -n "${agent}" ] || continue
            src="${INJECT_MOUNT_AGENTS}/${agent}.md"
            [ -f "${src}" ] || continue
            cp "${src}" "${INJECT_TARGET_AGENTS}/${agent}.md"
        done < <(__inject_names "${AGENTIC_WORKSPACE_AGENTS:-}" "${INJECT_MOUNT_AGENTS}" ".md")
    fi
fi

# -----------------------------------------------------------------------------
# 5.6 Capability adapter initialization
# -----------------------------------------------------------------------------
# Per ADR-040. Each registered capability translates its AGENTIC_<CAP>_*
# contract into provider-native env. No-op when a capability's provider is
# unset. Section 5.7 hard-fails if a provider is set but misconfigured.
#
# Deviation from the generic template: a successful `. "${__init}"` also
# exports "${__prefix}_READY=1" (e.g. AGENTIC_MEMORY_READY=1). This mirrors
# the memory primitive's pre-existing, tested contract (ADR-036) — adapters
# and downstream tooling read that var to know initialization succeeded —
# so migrating memory into this generic loop must not drop it.

__capability_env_prefix() {
    printf 'AGENTIC_%s' "$(printf '%s' "$1" | tr '[:lower:]-' '[:upper:]_')"
}

# Capability *names* (registry entries in AGENTIC_CAPABILITIES) are a
# narrower charset than provider names: lowercase letters, digits, hyphen.
# __capability_provider_safe's charset (a-zA-Z0-9._-) is too wide here — a
# name containing e.g. "." survives it, gets uppercased into a prefix like
# "AGENTIC_A.B", and the eval'd `${AGENTIC_A.B_PROVIDER:-}` is a bash bad
# substitution that kills the whole entrypoint under `set -e`. Reject
# anything but the safe charset before a prefix is ever built.
__capability_name_safe() {
    case "$1" in
        *[!a-z0-9-]*|"") return 1 ;;
    esac
    return 0
}

# Warn (do not fail) when a *_PROVIDER var is set for a capability that
# isn't in AGENTIC_CAPABILITIES. Pre-refactor, setting AGENTIC_MEMORY_PROVIDER
# alone was sufficient to activate memory; post-refactor it also requires
# "memory" to be listed in the registry. A narrower AGENTIC_CAPABILITIES
# (deliberate or accidental) now silently drops the capability with no
# signal, which conflicts with "opting in is opting into loud failure" —
# this is the one path where a misconfiguration produces no signal at all.
# Not a hard fail: the operator may have disabled the capability on purpose.
__registered_prefixes=""
for __cap in ${AGENTIC_CAPABILITIES:-}; do
    __capability_name_safe "${__cap}" || continue
    __registered_prefixes="${__registered_prefixes} $(__capability_env_prefix "${__cap}")"
done
for __varname in $(compgen -v | grep -E '^AGENTIC_[A-Z0-9_]+_PROVIDER$' || true); do
    __cand_prefix="${__varname%_PROVIDER}"
    case " ${__registered_prefixes} " in
        *" ${__cand_prefix} "*) ;;
        *)
            eval "__cand_value=\${${__varname}:-}"
            if [ -n "${__cand_value}" ] && [ "${__cand_value}" != "none" ]; then
                echo "[entrypoint] warning: ${__varname} is set but its capability is not in AGENTIC_CAPABILITIES (${AGENTIC_CAPABILITIES:-<empty>}); it will be ignored." >&2
            fi
            ;;
    esac
done
unset __varname __cand_prefix __cand_value __registered_prefixes

for __cap in ${AGENTIC_CAPABILITIES:-}; do
    __capability_name_safe "${__cap}" || continue
    __prefix="$(__capability_env_prefix "${__cap}")"
    eval "__provider=\${${__prefix}_PROVIDER:-}"
    [ -n "${__provider}" ] && [ "${__provider}" != "none" ] || continue

    if ! __capability_provider_safe "${__provider}"; then
        # Deliberately do NOT echo ${__provider} here: a path-traversal
        # payload (e.g. "../../../workspace/evil") would otherwise leak the
        # attempted escape target into the log/audit stream verbatim.
        echo "[entrypoint] invalid ${__cap} provider name (rejected before path resolution)" >&2
        exit 1
    fi

    __init="/opt/agentic/capabilities/${__cap}/${__provider}/init.sh"
    if [ -f "${__init}" ]; then
        echo "[entrypoint] ${__cap} adapter: ${__provider}" >&2
        # shellcheck disable=SC1090
        if . "${__init}"; then
            eval "export ${__prefix}_READY=1"
        else
            echo "[entrypoint] ${__cap} adapter init failed (exit $?); doctor in 5.7 will surface the cause." >&2
        fi
    else
        echo "[entrypoint] no ${__cap} adapter for provider: ${__provider}" >&2
        exit 1
    fi
done

# -----------------------------------------------------------------------------
# 5.7 Capability doctor preflight
# -----------------------------------------------------------------------------
# Hard-fail on any check failure. Opting into a capability is opting into
# loud failure, and failing here is free because no agent work has happened.

for __cap in ${AGENTIC_CAPABILITIES:-}; do
    __capability_name_safe "${__cap}" || continue
    __prefix="$(__capability_env_prefix "${__cap}")"
    eval "__provider=\${${__prefix}_PROVIDER:-}"
    [ -n "${__provider}" ] && [ "${__provider}" != "none" ] || continue

    __audit_dir="${AGENTIC_CAPABILITY_AUDIT_DIR:-/var/agentic/${__cap}-doctor}"
    mkdir -p "${__audit_dir}" 2>/dev/null || true
    __audit_file="${__audit_dir}/$(date -u +%Y-%m-%d).jsonl"

    if /opt/agentic/capabilities/"${__cap}"/doctor --json >> "${__audit_file}"; then
        echo "[entrypoint] ${__cap} doctor: pass (audit: ${__audit_file})" >&2
    else
        echo "[entrypoint] ${__cap} doctor: FAIL (audit: ${__audit_file})" >&2
        echo "[entrypoint] Unset ${__prefix}_PROVIDER to bypass the ${__cap} capability." >&2
        exit 1
    fi
done

# -----------------------------------------------------------------------------
# 6. Execute CMD
# -----------------------------------------------------------------------------
# Wrapper rather than exec, so capability finalize hooks get a post-agent
# moment. The agent's exit code is preserved exactly; finalize cannot change
# it. See ADR-040 and EXP-08 for why this is not `exec "$@"`.

# $1 = seconds each finalizer may spend, exported as AGENTIC_FINALIZE_BUDGET_S.
#
# The budget is asymmetric because the deadline only exists on one path. This
# function is called on BOTH exits, but the escalation window below only runs
# when the agent's status is >128, i.e. the signal path, where `docker stop -t`
# is already ticking. On an ordinary agent exit nothing is waiting on us. A
# single tight bound applied to both would kill a legitimate multi-second
# transcript sweep on every normal run, so it would never prune, which for a
# heavy user is a permanent never-prune. Callers pass the value for their path.
__run_finalizers() {
    AGENTIC_FINALIZE_BUDGET_S="${1}"
    export AGENTIC_FINALIZE_BUDGET_S
    for __cap in ${AGENTIC_CAPABILITIES:-}; do
        # __capability_name_safe (narrow [a-z0-9-] charset), not
        # __capability_provider_safe: the latter's wider charset
        # (a-zA-Z0-9._-) lets a name like "a.b" through, which then
        # uppercases into an invalid prefix (AGENTIC_A.B) and blows up the
        # eval below with a bash bad-substitution under `set -e` -- the
        # exact bug 5.6/5.7 above guard against for the same loop variable.
        __capability_name_safe "${__cap}" || continue
        __prefix="$(__capability_env_prefix "${__cap}")"
        eval "__provider=\${${__prefix}_PROVIDER:-}"
        [ -n "${__provider}" ] && [ "${__provider}" != "none" ] || continue
        # 5.6 rejects an unsafe provider name and exits before CMD ever
        # runs -- but only on the *hard*-fail path. Its init-failure branch
        # (unreadable/missing init.sh, adapter returning non-zero) only
        # warns and continues, so an unsafe provider string can still be
        # sitting in "${__provider}" when we get here. One more check is
        # cheap; a path built from an unvalidated provider name is not.
        __capability_provider_safe "${__provider}" || continue
        __fin="/opt/agentic/capabilities/${__cap}/${__provider}/finalize.sh"
        [ -f "${__fin}" ] || continue
        "${__fin}" || true
    done
}

# Coupled with lib/python/agentic_isolation/agentic_isolation/providers/
# docker.py's `docker stop -t 5` (see the matching comment there). This
# MUST stay strictly below that grace, with headroom for finalize's own
# work (a real transcript upload, not just process teardown) to run
# afterward -- if the two ever tie, docker's own SIGKILL can land in the
# same instant as this loop's, and finalize never gets to run at all.
# 15 x 0.1s = 1.5s leaves ~3.5s for finalize after the kill.
readonly __TERM_GRACE_TICKS=15

# Finalizer budgets, in seconds, for the two exit paths (see __run_finalizers).
# SIGNAL: measured 2026-08-14, escalation completes at ~1.66s for a stubborn
# agent, leaving ~3.3s of docker.py's `docker stop -t 5`. 2s finishes at ~3.66s,
# a 1.3s margin; 3s would leave 0.34s, too thin.
# CLEAN: no stop grace is running, so this bound exists only to stop a wedged
# finalizer hanging the run forever, not to hit a deadline.
readonly __FINALIZE_BUDGET_SIGNAL_S=2
readonly __FINALIZE_BUDGET_CLEAN_S=120

"$@" <&0 &
__child=$!
# Forward the signal actually received, not always TERM: under
# `docker run -it` job control is off, the child shares PID 1's process
# group and already receives the tty's SIGINT directly. Also sending it a
# synthesized SIGTERM would mean Ctrl-C -- how Claude Code interrupts
# generation -- kills the whole session instead of just the current turn.
trap 'kill -TERM "${__child}" 2>/dev/null' TERM
trap 'kill -INT "${__child}" 2>/dev/null' INT
# `set -e` is in effect for this whole script (line 30). A bare
# `wait "${__child}"; __rc=$?` is a classic set -e trap: if the child exits
# non-zero, `wait`'s own non-zero status is a simple command not shielded by
# `if`/`&&`/`||`, so the shell exits right there -- `__rc=$?` never runs and
# finalize never fires. Guard both waits with `if` (exempt from -e) so a
# failing/ signaled child is captured, not fatal to the wrapper itself.
if wait "${__child}"; then __rc=0; else __rc=$?; fi

# A trapped signal makes the first wait return >128. Do NOT simply wait
# again: EXP-08 measured that a plain second wait blocks on a child that
# has not died, burns the entire stop grace, gets SIGKILLed, and never
# runs finalize at all. Bound the wait and escalate.
# Recorded BEFORE the escalation block, which reassigns __rc from the second
# wait: by the time finalizers run, __rc no longer says which path we took.
__signaled=0
if [ "${__rc}" -gt 128 ]; then
    __signaled=1
    __n=0
    while kill -0 "${__child}" 2>/dev/null && [ "${__n}" -lt "${__TERM_GRACE_TICKS}" ]; do
        sleep 0.1
        __n=$((__n + 1))
    done
    kill -0 "${__child}" 2>/dev/null && kill -KILL "${__child}" 2>/dev/null
    if wait "${__child}" 2>/dev/null; then __rc=0; else __rc=$?; fi
fi

if [ "${__signaled}" -eq 1 ]; then
    __run_finalizers "${__FINALIZE_BUDGET_SIGNAL_S}"
else
    __run_finalizers "${__FINALIZE_BUDGET_CLEAN_S}"
fi
exit "${__rc}"
