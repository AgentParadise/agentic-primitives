#!/usr/bin/env bash
# SeshMagic session-store capability adapter.
#
# Translates the AGENTIC_SESSION_STORE_* contract (ADR-038) into the env
# SeshMagicSessionExporter reads. Sourced by /opt/agentic/entrypoint.sh
# section 5.6 so exports propagate to later process spawns.

set -e

SPOOL="${AGENTIC_SESSION_STORE_SPOOL:-/spool}"
PARTITION="${AGENTIC_SESSION_STORE_PARTITION:-${HOSTNAME}}"
PART_DIR="${SPOOL}/${PARTITION}"

# --- Store endpoint -----------------------------------------------------------
export SESSION_STORE_URL="${AGENTIC_SESSION_STORE_URL}"
if [ -n "${AGENTIC_SESSION_STORE_AUTH:-}" ]; then
    export SESSIONS_WRITE_TOKEN="${AGENTIC_SESSION_STORE_AUTH}"
fi

# --- Correlation tags ---------------------------------------------------------
# Opaque. This layer assigns no meaning; the orchestrator supplies workflow/phase.
if [ -n "${AGENTIC_SESSION_STORE_TAGS:-}" ]; then
    export SESSION_STORE_TAGS="${AGENTIC_SESSION_STORE_TAGS}"
fi

# --- Make the partition self-describing --------------------------------------
# EXP-08 arm A5: the partition PATH records which sweep a transcript belongs
# to, but the tags come from the environment at sweep time. A recovery sweep
# after a container is SIGKILLed has no such environment, and measurably
# uploads the session with NO TAGS AT ALL - the exact misattribution the
# partitioned spool was supposed to prevent.
#
# Persist the opaque tag string next to the transcripts so any later sweep is
# self-describing. This layer still assigns no meaning to the value; it just
# writes the string down.
mkdir -p "${PART_DIR}"
if [ -n "${AGENTIC_SESSION_STORE_TAGS:-}" ]; then
    printf 'SESSION_STORE_TAGS=%s\n' "${AGENTIC_SESSION_STORE_TAGS}" \
        > "${PART_DIR}/.capture-env"
    chmod 600 "${PART_DIR}/.capture-env"
fi

# --- Spool layout -------------------------------------------------------------
# Transcript roots live OUTSIDE $HOME. Bind-mounting under $HOME breaks the
# entrypoint: Docker creates the mount root-owned while we run as uid 1000
# (verified in EXP-07). Symlink instead.
mkdir -p "${PART_DIR}/claude" "${PART_DIR}/codex"
mkdir -p "${HOME}/.claude" "${HOME}/.codex"
ln -sfn "${PART_DIR}/claude" "${HOME}/.claude/projects"
ln -sfn "${PART_DIR}/codex"  "${HOME}/.codex/sessions"

export CLAUDE_PROJECTS_ROOT="${PART_DIR}/claude"
export CODEX_SESSIONS_ROOT="${PART_DIR}/codex"
export EXPORTER_STATE_FILE="${PART_DIR}/state.json"

# --- Deliberately NOT set -----------------------------------------------------
# SESSION_STORE_ORIGIN_HOST is left unset so the exporter reports the real
# hostname. The corpus uses origin_host for machine identity and per-machine
# cost attribution keys on it; overloading it with phase identity would
# corrupt that telemetry permanently.
