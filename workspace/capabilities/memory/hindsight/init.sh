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
