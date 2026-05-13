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
# Provider-specific failure modes are caught by /opt/agentic/memory/doctor
# via this directory's `doctor.sh` (called from section 5.7).

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
if [ -n "${AGENTIC_MEMORY_CONFIG_JSON:-}" ]; then
    mkdir -p "${HOME}/.hindsight"
    printf '%s' "${AGENTIC_MEMORY_CONFIG_JSON}" > "${HOME}/.hindsight/claude-code.json"
fi
