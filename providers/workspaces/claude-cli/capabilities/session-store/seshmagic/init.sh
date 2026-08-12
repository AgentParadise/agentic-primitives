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
#
# .capture-env is DATA, never shell. Tags are opaque orchestrator input that
# can contain anything (spaces, $(...), quotes) — a consumer that `source`s
# this file executes that input as a child of a process that may have
# SESSIONS_WRITE_TOKEN in scope. Consumers MUST parse the line (e.g.
# `cut -d= -f2-` on the SESSION_STORE_TAGS= line) and `export` the result
# themselves; they must never `.`/`source` this file. See this directory's
# README for the parse contract.
mkdir -p "${PART_DIR}"
rm -f "${PART_DIR}/.capture-env"
if [ -n "${AGENTIC_SESSION_STORE_TAGS:-}" ]; then
    # umask, not a post-hoc chmod: a post-hoc chmod leaves a window where the
    # file is created world-readable before the permission fix lands.
    (
        umask 077
        printf 'SESSION_STORE_TAGS=%s\n' "${AGENTIC_SESSION_STORE_TAGS}" \
            > "${PART_DIR}/.capture-env"
    )
fi

# --- Spool layout -------------------------------------------------------------
# Transcript roots live OUTSIDE $HOME. Bind-mounting under $HOME breaks the
# entrypoint: Docker creates the mount root-owned while we run as uid 1000
# (verified in EXP-07). Symlink instead.
#
# Guard against ~/.claude/projects or ~/.codex/sessions already existing as
# a REAL directory (a persisted $HOME, or a prior Claude Code run). Without
# this, `ln -sfn` nests the symlink inside the existing directory instead of
# replacing it (e.g. ~/.claude/projects/claude -> ...), and symlinks_correct
# then hard-fails the workspace with a confusing error. A pre-existing
# symlink (re-run of this adapter) or a non-existent path is left alone;
# `ln -sfn` replaces those correctly on its own.
mkdir -p "${PART_DIR}/claude" "${PART_DIR}/codex"
mkdir -p "${HOME}/.claude" "${HOME}/.codex"
[ -L "${HOME}/.claude/projects" ] || [ ! -e "${HOME}/.claude/projects" ] || rm -rf "${HOME}/.claude/projects"
[ -L "${HOME}/.codex/sessions" ] || [ ! -e "${HOME}/.codex/sessions" ] || rm -rf "${HOME}/.codex/sessions"
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
