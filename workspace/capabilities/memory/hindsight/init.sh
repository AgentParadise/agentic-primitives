#!/usr/bin/env bash
# Hindsight memory provider adapter.
#
# Translates the AGENTIC_MEMORY_* contract (ADR-036) into the HINDSIGHT_*
# env vars the hindsight Claude Code plugin reads.
#
# Called by /opt/agentic/entrypoint.sh section 5.6 when
# AGENTIC_MEMORY_PROVIDER=hindsight. Sourced into the parent shell so the
# exports propagate to subsequent process spawns.
#
# Provider-specific failure modes are caught by
# /opt/agentic/capabilities/memory/doctor via this directory's `doctor.sh`
# (called from section 5.7).

# ERREXIT DOES NOT FIRE IN THIS FILE. Kept only for the case where somebody
# runs this script directly.
#
# entrypoint.sh 5.6 sources this file as the condition of an `if`
# (`if . "${__init}"; then`). Bash disables errexit for the whole command that
# forms such a condition, including a sourced script, so this `set -e` is
# inert in production. Verified directly:
#
#   $ printf 'set -e\nfalse\necho REACHED\n' > probe.sh
#   $ bash -c 'if . probe.sh; then echo "rc=0"; fi'
#   REACHED
#   rc=0
#
# A failing command here therefore does NOT stop the file, and a later
# successful command makes the source return zero, which the lifecycle records
# as a successful init. Every command below whose failure matters is checked
# explicitly and reports with `return 1`, which the `if` at 5.6 does see. Do
# not "fix" this by changing how 5.6 sources adapters: that call site is
# generic lifecycle code shared by every capability.
set -e

# --- This run's init-completion token -----------------------------------------
# Minted FIRST, before anything can fail, and written to the marker file LAST,
# after every consequential step has succeeded (see the end of this file). The
# doctor's init_complete check compares the two.
#
# WHY A TOKEN RATHER THAN JUST A FILE. $HOME can be persisted across
# containers, which is a supported configuration, so a marker whose only job
# was to exist would still be there on the next run: an init that failed
# before writing anything would be vouched for by its predecessor's file,
# which is the stale state this marker exists to detect, one layer up. A token
# that is fresh per run cannot do that.
#
# Clearing a previous run's marker here instead was considered and rejected:
# the clear is itself a write, and the case that matters most is exactly the
# one where writes fail, so a failed clear would leave the stale marker in
# place and pass.
#
# The value is assigned unconditionally, never defaulted from the environment,
# so a value injected into the container cannot stand in for one this adapter
# minted. It is not a secret, and an on-demand doctor re-run later needs it.
AGENTIC_MEMORY_INIT_TOKEN="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || true)"
if [ -z "${AGENTIC_MEMORY_INIT_TOKEN}" ]; then
    # No /proc (this file also runs outside the workspace image in tests).
    # $$ separates concurrent processes, the nanosecond clock separates
    # sequential ones, and $RANDOM covers a coarse `date` on a host without %N.
    AGENTIC_MEMORY_INIT_TOKEN="$$-$(date -u +%s%N 2>/dev/null)-${RANDOM}${RANDOM}"
fi
export AGENTIC_MEMORY_INIT_TOKEN

# Where that token is written on success. The name is restated in
# agentic_memory.contract as INIT_MARKER_BASENAME, because the doctor has to
# find the same file; the two spellings must agree. It is a capability-level
# artifact, not a hindsight one, so it goes in $HOME rather than in
# ~/.hindsight: every memory provider's adapter writes this same file.
__memory_init_marker="${HOME}/.agentic-memory-init-complete"

# --- Backend URL --------------------------------------------------------------
export HINDSIGHT_API_URL="${AGENTIC_MEMORY_URL}"

# --- Auth (optional) ----------------------------------------------------------
if [ -n "${AGENTIC_MEMORY_AUTH:-}" ]; then
    export HINDSIGHT_API_TOKEN="${AGENTIC_MEMORY_AUTH}"
fi

# --- Bank scoping -------------------------------------------------------------
# HINDSIGHT_BANK_ID env override is honored only when dynamicBankId=false
# (verified empirically in agentic-memory's bank-derivation-modes probe).
# Force static bank-id mode so the contract's namespace actually takes effect.
export HINDSIGHT_DYNAMIC_BANK_ID=false
export HINDSIGHT_BANK_ID="${AGENTIC_MEMORY_NAMESPACE}"

# --- Optional rich config -----------------------------------------------------
# AGENTIC_MEMORY_CONFIG_JSON is the escape hatch for adapter-specific config
# the core contract doesn't model (e.g. recallAdditionalBanks). Written to
# the path the hindsight plugin already knows how to read.
#
# Both steps are checked. A silently failed write leaves the plugin reading
# whatever config was there before (or none), so the operator's requested
# banks are quietly not in scope for recall, and the run looks fine.
if [ -n "${AGENTIC_MEMORY_CONFIG_JSON:-}" ]; then
    __hindsight_config_dir="${HOME}/.hindsight"
    if ! mkdir -p "${__hindsight_config_dir}"; then
        echo "[memory] cannot create ${__hindsight_config_dir};" \
             "AGENTIC_MEMORY_CONFIG_JSON would be silently ignored." >&2
        unset __hindsight_config_dir
        return 1
    fi
    if ! printf '%s' "${AGENTIC_MEMORY_CONFIG_JSON}" \
         > "${__hindsight_config_dir}/claude-code.json"; then
        echo "[memory] could not write ${__hindsight_config_dir}/claude-code.json;" \
             "the run would use stale or absent memory config rather than the" \
             "one supplied. Check that the path is writable by uid $(id -u)." >&2
        unset __hindsight_config_dir
        return 1
    fi
    unset __hindsight_config_dir
fi

# --- Record that this init completed ------------------------------------------
# LAST, and reached only when every step above returned success, because the
# doctor's init_complete check reads this file as a statement that all of them
# did. Anything added to this adapter belongs ABOVE this write: a marker
# written before the work it vouches for is worse than no marker, since it
# turns a detectable failure into a pass.
#
# The name is classified before either write touches it. A symlink here is not
# a file this adapter wrote, so `>` would truncate whatever it points at and
# `rm -f` would drop the link; both are refusals instead, with nothing removed.
if [ -L "${__memory_init_marker}" ] ||
   { [ -e "${__memory_init_marker}" ] && [ ! -f "${__memory_init_marker}" ]; }; then
    echo "[memory] ${__memory_init_marker} exists and is not a regular file" \
         "this adapter could have written; refusing to replace it. Nothing was" \
         "modified." >&2
    unset __memory_init_marker
    return 1
fi

# umask so the file is never briefly world-readable, `set -o noclobber`
# (O_CREAT|O_EXCL) so a name planted here after the classification above fails
# the open instead of being followed, the previous run's marker removed first
# because O_EXCL will not truncate one, and the subshell's status checked
# explicitly because errexit is inert in this file. Both options are set
# inside the subshell only: this file is sourced, so setting either in the
# parent would persist into the entrypoint and every later command it runs.
# O_EXCL constrains the final component only; a parent directory swapped for a
# symlink is still resolved normally, so this is not a write that cannot
# escape $HOME.
if ! (
    umask 077
    set -o noclobber
    rm -f "${__memory_init_marker}" &&
        printf '%s\n' "${AGENTIC_MEMORY_INIT_TOKEN}" > "${__memory_init_marker}"
); then
    echo "[memory] could not write ${__memory_init_marker}, so nothing can" \
         "distinguish this run's initialization from a previous one's. Check" \
         "that ${HOME} is writable by uid $(id -u). Failing the init rather" \
         "than starting a workspace whose doctor would have no way to tell" \
         "that it had." >&2
    unset __memory_init_marker
    return 1
fi
unset __memory_init_marker
return 0
