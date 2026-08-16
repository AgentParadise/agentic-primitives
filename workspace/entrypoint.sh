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

# Anything already in AGENTIC_CAPABILITY_WITHHOLD before any adapter has run
# came from the substrate, not from a capability, so no capability owns it.
# 5.8 still withholds it from the agent; no finalizer gets it back.
__withhold_ambient="${AGENTIC_CAPABILITY_WITHHOLD:-}"

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
        # WHO DECLARED WHAT. AGENTIC_CAPABILITY_WITHHOLD (5.8) is one flat
        # list, so by the time 5.8 reads it, which capability asked for which
        # name is no longer knowable -- and every finalizer then received
        # every capability's withheld values, including other capabilities'
        # credentials. Attribution has to be captured here, where a single
        # adapter is the only thing that can have changed the variable: the
        # names this init.sh appended are the difference across the source.
        __withhold_before="${AGENTIC_CAPABILITY_WITHHOLD:-}"
        # shellcheck disable=SC1090
        if . "${__init}"; then
            eval "export ${__prefix}_READY=1"
        else
            echo "[entrypoint] ${__cap} adapter init failed (exit $?); doctor in 5.7 will surface the cause." >&2
        fi
        # Computed on BOTH branches: an init.sh that declared a name and then
        # failed still put that name in the environment, and 5.8 will withhold
        # it, so it still needs an owner.
        __withhold_after="${AGENTIC_CAPABILITY_WITHHOLD:-}"
        __withhold_delta="${__withhold_after#"${__withhold_before}"}"
        if [ -n "${__withhold_before}" ] && [ "${__withhold_delta}" = "${__withhold_after}" ] &&
           [ "${__withhold_after}" != "${__withhold_before}" ]; then
            # The documented contract is APPEND, never assign (see 5.8). An
            # adapter that assigned has already discarded earlier capabilities'
            # declarations from the variable, which nothing here can recover;
            # say so rather than silently mis-attributing what is left.
            echo "[entrypoint] warning: ${__cap} assigned AGENTIC_CAPABILITY_WITHHOLD instead of appending to it; earlier declarations were lost" >&2
            __withhold_delta="${__withhold_after}"
        fi
        eval "__WITHHOLD_FOR_${__prefix}=\${__withhold_delta}"
        unset __withhold_before __withhold_after __withhold_delta
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
# 5.8 Withhold declared contract variables from the agent
# -----------------------------------------------------------------------------
# init.sh is SOURCED (5.6), so everything it exports propagates all the way to
# CMD. For most of a contract that is the point. For a credential it is a
# defect: the session-store adapter's write token was exported into the
# environment of every command the agent ran, and the agent has no use for it
# at all. Only finalize.sh does, and finalize.sh runs after the agent exits.
#
# THE MECHANISM IS GENERIC, because ADR-040 s4 says adding a capability must
# cost zero entrypoint changes. Nothing here names a capability or a variable.
# A capability declares, from its own init.sh, which variables must not reach
# the agent:
#
#     AGENTIC_CAPABILITY_WITHHOLD="${AGENTIC_CAPABILITY_WITHHOLD:-} FOO BAR"
#     export AGENTIC_CAPABILITY_WITHHOLD
#
# Space-separated, appended rather than assigned so several capabilities
# compose. The lifecycle stashes each declared variable's value in a shell
# variable of THIS process (a plain variable, deliberately not exported, so no
# child inherits it), unsets the exported copy, and re-exports it only into the
# subshell THE DECLARING CAPABILITY'S finalizer runs in.
#
# SCOPED TO THE DECLARER, because this list is flat and a credential belongs to
# exactly one capability. Restoring the whole list before every finalizer meant
# an unrelated capability's finalizer ran with another capability's credential
# in its environment -- a smaller version of the leak this section exists to
# close, and one the subshell does nothing about (the subshell bounds the
# LIFETIME of the restore, not who sees it). Ownership is recorded in 5.6, per
# adapter, as the names that adapter appended; the restore below reads it back.
#
# Ordering is load-bearing. This runs AFTER 5.7, because the doctor legitimately
# needs the credential to check that the store is reachable, and BEFORE section
# 6 launches CMD, which is the process that must not see it. A consequence worth
# stating: an on-demand doctor re-run by the agent later will report the store
# unreachable if the store requires auth. That is correct. The agent genuinely
# no longer holds that credential.
#
# What this does NOT close: values the substrate injected with `docker run -e`
# also live in /proc/1/environ, which the agent runs as the same uid and can
# read. Unsetting a shell variable cannot scrub a process image that was set at
# exec time. Closing that residue is the host-side half's job (ADR-040 s1) --
# deliver the secret as a mounted file rather than an env var -- and it is
# recorded in ADR-040 s2 as a known limit rather than pretended away here.
__withheld_names=""
for __wn in ${AGENTIC_CAPABILITY_WITHHOLD:-}; do
    # A name is about to be eval'd on both sides of this. Validate it as a
    # shell identifier first, for the same reason 5.6 validates capability
    # names before they become part of an expansion.
    case "${__wn}" in
        [!A-Za-z_]* | *[!A-Za-z0-9_]*)
            echo "[entrypoint] warning: ignoring an invalid name in AGENTIC_CAPABILITY_WITHHOLD (not a shell identifier)" >&2
            continue
            ;;
    esac
    # Only stash what is actually set. Restoring a variable that was never
    # set would invent an empty one for finalize, and a duplicate entry (two
    # capabilities withholding the same name) hits this on its second pass
    # and is skipped rather than overwriting the stash with an empty value.
    eval "__wset=\${${__wn}+set}"
    [ "${__wset:-}" = "set" ] || continue
    eval "__WITHHELD_${__wn}=\${${__wn}}"
    unset "${__wn}"
    __withheld_names="${__withheld_names} ${__wn}"
done
unset __wn __wset
# The declaration itself is a list of names, not a secret, but it has no
# reader after this point and an env var nobody reads is one more thing to
# explain.
unset AGENTIC_CAPABILITY_WITHHOLD
if [ -n "${__withheld_names}" ]; then
    echo "[entrypoint] withheld from the agent, restored for the declaring capability's finalize:${__withheld_names}" >&2
fi
if [ -n "${__withhold_ambient}" ]; then
    echo "[entrypoint] note: AGENTIC_CAPABILITY_WITHHOLD arrived already set, so those names belong to no capability; they are withheld from the agent and restored for no finalizer" >&2
fi

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
# on the signal path, where `docker stop -t` is already ticking: this wrapper
# was signalled AND the wait returned above 128 because of it. An agent that
# merely exits with a status above 128 is not that path, and gets the clean
# budget. On an ordinary agent exit nothing is waiting on us. A
# single tight bound applied to both would kill a legitimate multi-second
# transcript sweep on every normal run, so for a heavy user no sweep would ever
# complete. Callers pass the value for their path.
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
        # Restore only THIS capability's withheld names, and only in a
        # SUBSHELL. The two guards answer two different questions, and the
        # comment here used to claim the second one answered both:
        #
        #   the subshell bounds WHEN: the export lives exactly as long as this
        #   finalizer, so it is not still in scope for later ones. The agent
        #   has already exited, so nothing the agent runs is a child of it.
        #
        #   the per-capability list bounds WHO: a capability's finalizer sees
        #   the names its own init.sh declared and no others. Without it, every
        #   finalizer ran with every other capability's credentials in its
        #   environment, which the subshell does nothing about.
        eval "__cap_withheld=\${__WITHHOLD_FOR_${__prefix}:-}"
        (
            for __wn in ${__cap_withheld}; do
                # Restore only names 5.8 actually stashed. That list holds
                # validated shell identifiers only, so this membership test is
                # also what keeps an unvalidated name out of the eval below.
                case " ${__withheld_names} " in
                    *" ${__wn} "*)
                        eval "export ${__wn}=\"\${__WITHHELD_${__wn}}\""
                        ;;
                esac
            done
            "${__fin}"
        ) || true
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
# DID THIS WRAPPER ITSELF GET SIGNALLED? Set by the trap bodies below, and
# read by the classification after the wait.
#
# The two questions "was the agent torn down" and "did the agent exit with a
# status above 128" are not the same question, and the code below used to
# treat them as one. `wait` reports a signalled child as 128+signum, but a
# process may also just exit with a status in that range: `exit 200` is a
# perfectly ordinary exit, and 200 > 128. Classifying it as signalled gave a
# normal run the tight signal-path finalize budget and a kill escalation, with
# no stop deadline in play at all, which for the session-store capability
# means a sweep cut short and transcripts left un-uploaded.
#
# This flag is the direct evidence, not an inference from a number. There is
# exactly one way `docker stop` (or a Ctrl-C) reaches this wrapper, and that
# is a signal delivered to PID 1, which runs one of these traps. It can only
# fire while this shell is blocked in the `wait` below, because that is where
# this shell spends the agent's entire lifetime.
__signal_received=0
# Forward the signal actually received, not always TERM: under
# `docker run -it` job control is off, the child shares PID 1's process
# group and already receives the tty's SIGINT directly. Also sending it a
# synthesized SIGTERM would mean Ctrl-C -- how Claude Code interrupts
# generation -- kills the whole session instead of just the current turn.
#
# `|| true` ON BOTH, for the same reason the escalation block below has one,
# and this is the sibling that fix missed. `set -e` is in force INSIDE a trap
# body: if the child exits just before the signal lands, `kill` fails with
# ESRCH and the shell exits from within the handler, at PID 1, skipping every
# finalizer. Reproduced directly, not inferred:
#
#   bash -c 'set -e; trap "kill -TERM 999999 2>/dev/null" USR1; kill -USR1 $$;
#            sleep 0.05; echo TRAP_SURVIVED'   -> aborted, rc=1, no output
#
# The `2>/dev/null` only hides the diagnostic; it does not change the status.
# Any trap body added here later needs the same guard.
# The flag is set FIRST in each body, before the kill that may fail: a plain
# assignment cannot fail, so it is recorded whatever the kill then does.
trap '__signal_received=1; kill -TERM "${__child}" 2>/dev/null || true' TERM
trap '__signal_received=1; kill -INT "${__child}" 2>/dev/null || true' INT
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
#
# BOTH CONDITIONS, and neither alone is the test.
#
#   `-gt 128` alone was the bug. It is true of a signalled child AND of an
#   agent that simply exited with a status in that range, and `exit 200` then
#   took the signal path: the tight finalize budget plus a kill escalation, on
#   a run where nothing was tearing the container down and no `docker stop -t`
#   was ticking. The budgets are asymmetric by measurement (see
#   __FINALIZE_BUDGET_SIGNAL_S), so misclassifying a clean exit does not just
#   mislabel it, it cuts the sweep short.
#
#   The flag alone is not the test either. It says a signal reached this
#   wrapper, not that the wait ended because of one, and the escalation below
#   only makes sense for a `wait` that returned while the child may still be
#   alive.
#
# Together they are exactly the signal path: `wait` returns >128 the instant a
# trap runs, so a signal that reached this wrapper and a wait that ended above
# 128 is that wait being interrupted by that signal. Every currently signalled
# case is classified the same way it was before; the only run whose
# classification changes is the one with no signal anywhere in it.
#
# A child killed by a signal nothing routed through this wrapper (an external
# `kill -9` on the agent, or the OOM killer) takes the clean path now. That is
# correct rather than incidental: no stop grace is running, so there is no
# deadline to stay inside, and the child is already dead, so there is nothing
# to escalate to.
__signaled=0
if [ "${__rc}" -gt 128 ] && [ "${__signal_received}" -eq 1 ]; then
    __signaled=1
    __n=0
    # `sleep ... || true`: the same class again, one line further on. Under
    # `docker run -it` the container shares a process group with the tty, so a
    # Ctrl-C lands on `sleep` as well as on PID 1. An interrupted `sleep`
    # returns non-zero, and as the loop body's last command that is fatal under
    # `set -e` -- the wrapper would exit here, before any finalizer runs, on the
    # one path where the agent is already being torn down.
    while kill -0 "${__child}" 2>/dev/null && [ "${__n}" -lt "${__TERM_GRACE_TICKS}" ]; do
        sleep 0.1 || true
        __n=$((__n + 1))
    done
    # Escalate to SIGKILL once the grace expires. Written as `if`/`|| true`
    # rather than the shorter `kill -0 ... && kill -KILL ...`, because that
    # form is a `set -e` race with NO safe outcome: if the child dies BETWEEN
    # the two calls, `kill -0` succeeds, `kill -KILL` fails with ESRCH, and
    # the whole AND-list is then the last command of the script's current
    # list, so `set -e` aborts the wrapper right here -- before finalizers
    # run. Capture is silently skipped and the container exits non-zero with
    # no explanation.
    #
    # The bug is invisible to the obvious test by construction, which is why
    # it survived review: child already gone -> `kill -0` fails, the `&&`
    # short-circuits, and a failed *condition* is exempt from `set -e`, so it
    # passes. Child still alive -> both calls succeed, so it passes. Only the
    # race in between fails, and hand-testing exercises exactly the two cases
    # that pass.
    #
    # Both guards below are load-bearing: the `if` makes the liveness probe a
    # condition (exempt), and `|| true` makes the kill itself non-fatal for
    # the same race, one instruction later.
    if kill -0 "${__child}" 2>/dev/null; then
        kill -KILL "${__child}" 2>/dev/null || true
    fi
    if wait "${__child}" 2>/dev/null; then __rc=0; else __rc=$?; fi
fi

if [ "${__signaled}" -eq 1 ]; then
    __run_finalizers "${__FINALIZE_BUDGET_SIGNAL_S}"
else
    __run_finalizers "${__FINALIZE_BUDGET_CLEAN_S}"
fi
exit "${__rc}"
