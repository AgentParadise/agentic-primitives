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
# Point a harness transcript root at the partition, preserving anything already
# there. `ln -sfn` does NOT replace an existing real directory: it creates the
# link inside it (~/.claude/projects/claude -> ...), which then fails
# symlinks_correct and hard-exits the workspace with a confusing error. The
# previous implementation solved that with `rm -rf`, which destroyed
# un-uploaded transcripts on any persisted $HOME (or any workspace where
# Claude Code had already run) at startup, BEFORE the exporter had ever run.
# Migrate instead, so a workspace that would have LOST its history instead
# gains it: the moved transcripts are swept and uploaded by this run's
# finalize.
#
# A pre-existing symlink (a re-run of this adapter) or a non-existent path is
# left to `ln -sfn`, which handles both correctly on its own.
__link_transcript_root() {
    local src="$1" dst="$2" label="$3"

    if [ -L "${src}" ] || [ ! -e "${src}" ]; then
        ln -sfn "${dst}" "${src}"
        return 0
    fi

    if [ ! -d "${src}" ]; then
        echo "[session-store] ${label}: ${src} exists and is not a directory; refusing to touch it" >&2
        return 1
    fi

    # Move contents, not the directory, so an existing partition is preserved.
    # Dotfiles included. An empty source is fine.
    #
    # `mv -n` never overwrites: a name collision leaves the source file in
    # place rather than clobbering either copy. Nothing here may become
    # `rm -rf` on a path that can hold user data.
    if ! find "${src}" -mindepth 1 -maxdepth 1 -exec mv -n -- {} "${dst}/" \; 2>/dev/null; then
        echo "[session-store] ${label}: migration of ${src} failed; leaving it untouched" >&2
        return 1
    fi

    # Only remove the source once it is provably empty. `rmdir` refuses
    # otherwise, which is exactly the safety property we want: if anything at
    # all survived the move, we report failure and delete nothing.
    if ! rmdir "${src}" 2>/dev/null; then
        echo "[session-store] ${label}: ${src} still has contents after migration; leaving it untouched" >&2
        return 1
    fi

    ln -sfn "${dst}" "${src}"
    echo "[session-store] ${label}: migrated existing transcripts into ${dst}" >&2
    return 0
}

__migrate_failed=0
mkdir -p "${PART_DIR}/claude" "${PART_DIR}/codex" || __migrate_failed=1
mkdir -p "${HOME}/.claude" "${HOME}/.codex" || __migrate_failed=1
__link_transcript_root "${HOME}/.claude/projects" "${PART_DIR}/claude" "claude" || __migrate_failed=1
__link_transcript_root "${HOME}/.codex/sessions"  "${PART_DIR}/codex"  "codex"  || __migrate_failed=1

export CLAUDE_PROJECTS_ROOT="${PART_DIR}/claude"
export CODEX_SESSIONS_ROOT="${PART_DIR}/codex"
export EXPORTER_STATE_FILE="${PART_DIR}/state.json"

# --- Deliberately NOT set -----------------------------------------------------
# SESSION_STORE_ORIGIN_HOST is left unset so the exporter reports the real
# hostname. The corpus uses origin_host for machine identity and per-machine
# cost attribution keys on it; overloading it with phase identity would
# corrupt that telemetry permanently.

# --- Exit status --------------------------------------------------------------
# This file is SOURCED by entrypoint.sh 5.6 inside an `if`, so a non-zero
# return is reported and then routed to the 5.7 doctor rather than killing
# the workspace here. That routing is what makes the failure legible: when a
# migration fails we deliberately did NOT create the symlink, so the doctor's
# symlinks_correct check fails and the operator gets a specific error naming
# the path, instead of a workspace that quietly ran with no capture.
unset -f __link_transcript_root
if [ "${__migrate_failed}" -ne 0 ]; then
    unset __migrate_failed
    echo "[session-store] transcript root migration failed; see the doctor output below" >&2
    return 1
fi
unset __migrate_failed
return 0
