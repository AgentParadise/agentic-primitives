#!/usr/bin/env bash
# SeshMagic session-store capability adapter.
#
# Translates the AGENTIC_SESSION_STORE_* contract (ADR-040) into the env
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
# can contain anything (spaces, $(...), quotes, newlines) - a consumer that
# `source`s this file executes that input as a child of a process that may
# have SESSIONS_WRITE_TOKEN in scope. Consumers MUST parse the line and
# `export` the result themselves; they must never `.`/`source` this file. See
# this directory's README for the parse contract.
#
# The value is base64-encoded. The record is line-oriented and the tag string
# is opaque, so a tag containing a NEWLINE (e.g. a multi-line
# "workflow:w1\nphase:p2") was silently truncated at the first line by any
# read-one-line consumer, losing exactly the attribution this file exists to
# preserve. base64 makes the encoded value a single line of [A-Za-z0-9+/=]
# by construction, so the record stays line-oriented and the parse stays
# trivial, and it cannot reintroduce shell interpretation: there is no
# character in the base64 alphabet that means anything to a shell.
# --- Record that WE created this partition directory --------------------------
# finalize.sh deletes the partition after a successful upload, and this marker
# is the only evidence it has that the directory is ours to delete. It is
# written ONLY when the directory did not already exist.
#
# That distinction is the whole point, so do not "simplify" this to an
# unconditional write. With AGENTIC_SESSION_STORE_SPOOL=/workspace and
# AGENTIC_SESSION_STORE_PARTITION=repos, PART_DIR is a directory the operator
# bind-mounted and filled with their own data. We are about to mkdir -p into
# it, symlink into it, and sweep it - all non-destructive. Marking it here
# would additionally license finalize.sh to `rm -rf` it, which is how an
# unrelated mounted directory was destroyed during review.
#
# The marker persists on the spool volume, which is what lets a recovery sweep
# of a partition left behind by a SIGKILLed container still prune: that
# directory was created by this capability too, just on an earlier run.
#
# Like .capture-env, this file is DATA and is never sourced. Nothing reads its
# contents; only its existence is meaningful. The text is for a human who
# finds it in a spool volume.
if [ -d "${PART_DIR}" ]; then
    __part_dir_is_ours=0
else
    __part_dir_is_ours=1
fi

mkdir -p "${PART_DIR}"

if [ "${__part_dir_is_ours}" -eq 1 ]; then
    printf '%s\n' \
        "# Created by the agentic session-store capability (ADR-040)." \
        "# Its presence authorizes finalize.sh to remove this directory after" \
        "# a confirmed upload. Delete it to make that partition permanent." \
        > "${PART_DIR}/.agentic-partition"
fi
unset __part_dir_is_ours

rm -f "${PART_DIR}/.capture-env"
if [ -n "${AGENTIC_SESSION_STORE_TAGS:-}" ]; then
    # umask, not a post-hoc chmod: a post-hoc chmod leaves a window where the
    # file is created world-readable before the permission fix lands.
    (
        umask 077
        # `printf '%s'` (no trailing newline) so the encoded bytes are exactly
        # the tag string, and `tr -d '\n'` because GNU base64 wraps its output
        # at 76 columns, which would put the record back on multiple lines.
        printf 'SESSION_STORE_TAGS_B64=%s\n' \
            "$(printf '%s' "${AGENTIC_SESSION_STORE_TAGS}" | base64 | tr -d '\n')" \
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
    local entry base mv_failed=0

    if [ -L "${src}" ] || [ ! -e "${src}" ]; then
        ln -sfn "${dst}" "${src}" || return 1
        return 0
    fi

    if [ ! -d "${src}" ]; then
        echo "[session-store] ${label}: ${src} exists and is not a directory; refusing to touch it" >&2
        return 1
    fi

    # Move the CONTENTS, not the directory, so an existing partition is
    # preserved. Dotfiles included. An empty source is fine.
    #
    # `mv -n` never overwrites: a name collision leaves the source file in
    # place rather than clobbering either copy. Nothing in this function may
    # become `rm -rf` on a path that can hold user data.
    #
    # WHAT THIS LOOP'S EXIT-STATUS CHECK DOES AND DOES NOT CATCH. Verified
    # against GNU coreutils 9.1 in this image, not inferred from the docs:
    # `mv -n` exits 0 and prints NOTHING when it skips a collision, and exits
    # non-zero with a diagnostic only on a hard error (permission denied, and
    # such). So mv_failed catches hard errors ONLY. Collisions are invisible
    # here and are caught solely by the `rmdir` below. Do not reword this into
    # a claim that the loop detects collisions.
    #
    # mv's stderr is deliberately NOT sent to /dev/null, so the hard-error
    # case names the offending path. The collision case, which mv reports
    # nothing about, is named by the `ls -A` in the rmdir branch instead.
    #
    # The entry list is expanded UP FRONT by the globs rather than streamed
    # from `find -exec`: moving entries out of a directory while find is
    # mid-readdir on it leaves entry visibility unspecified by POSIX, and a
    # skipped entry would produce a spurious hard-fail on a large
    # ~/.claude/projects. (It could not lose data even then, since a skipped
    # entry simply stays put and rmdir below catches it.)
    for entry in "${src}"/* "${src}"/.*; do
        base="${entry##*/}"
        case "${base}" in
            . | ..) continue ;;
        esac
        # Also skips a non-matching glob, which expands to itself literally.
        [ -e "${entry}" ] || [ -L "${entry}" ] || continue
        mv -n -- "${entry}" "${dst}/" || mv_failed=1
    done

    if [ "${mv_failed}" -ne 0 ]; then
        echo "[session-store] ${label}: migration of ${src} failed (see the mv error above); leaving it untouched" >&2
        return 1
    fi

    # The authoritative check, and the one the safety property actually rests
    # on. `rmdir` removes the source only once it is provably empty and
    # refuses otherwise. That is a property of the filesystem rather than of
    # an exit code, so it catches everything the loop above cannot see,
    # including the silent `mv -n` collision skip. If a single entry survived,
    # we report failure and delete nothing. List what survived: on a collision
    # mv said nothing, so this is the operator's only pointer to the file that
    # blocked the migration, and the recovery is manual.
    if ! rmdir "${src}" 2>/dev/null; then
        echo "[session-store] ${label}: ${src} still has contents after migration; leaving it untouched" >&2
        echo "[session-store] ${label}: surviving entries in ${src}:" >&2
        ls -A -- "${src}" >&2 2>/dev/null || true
        return 1
    fi

    ln -sfn "${dst}" "${src}" || return 1
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
