#!/usr/bin/env bash
# SeshMagic session-store capability adapter.
#
# Translates the AGENTIC_SESSION_STORE_* contract (ADR-040) into the env
# SeshMagicSessionExporter reads. Sourced by /opt/agentic/entrypoint.sh
# section 5.6 so exports propagate to later process spawns.

# ERREXIT DOES NOT FIRE IN THIS FILE. Kept only for the case where somebody
# runs this script directly, and stated plainly so the next reader does not
# rebuild the assumption a previous one did.
#
# entrypoint.sh 5.6 sources this file as the condition of an `if`
# (`if . "${__init}"; then`). Bash disables errexit for the whole command that
# forms such a condition, including a sourced script, so every `set -e` below
# this line is inert in production. Verified directly:
#
#   $ printf 'set -e\nfalse\necho REACHED\n' > probe.sh
#   $ bash -c 'if . probe.sh; then echo "rc=0"; fi'
#   REACHED
#   rc=0
#
# So a failing command here does NOT stop the file, and a later successful
# command makes the source return zero, which the lifecycle records as a
# successful init. EVERY command below whose failure matters is therefore
# checked EXPLICITLY, and reports with `return 1` (which the `if` at 5.6 does
# see) or warns to stderr. The fix is not to change how 5.6 sources this file:
# that call site is generic lifecycle code shared by every capability, and the
# withhold-attribution diff around it depends on its current shape.
set -e

SPOOL="${AGENTIC_SESSION_STORE_SPOOL:-/spool}"
PARTITION="${AGENTIC_SESSION_STORE_PARTITION:-${HOSTNAME}}"
PART_DIR="${SPOOL}/${PARTITION}"

# --- Store endpoint -----------------------------------------------------------
export SESSION_STORE_URL="${AGENTIC_SESSION_STORE_URL}"
if [ -n "${AGENTIC_SESSION_STORE_AUTH:-}" ]; then
    export SESSIONS_WRITE_TOKEN="${AGENTIC_SESSION_STORE_AUTH}"

    # The write credential is for the EXPORTER, which runs in finalize.sh
    # after the agent has exited. The agent itself never needs it, and this
    # file is SOURCED, so without this declaration both the orchestrator's
    # copy and the derived exporter copy stay exported into the environment
    # of every single command the agent runs.
    #
    # AGENTIC_CAPABILITY_WITHHOLD is the lifecycle's generic mechanism
    # (entrypoint.sh 5.8, ADR-040 s2): the named variables are stashed out of
    # the environment before CMD launches and restored only into the subshell
    # each finalizer runs in. APPEND, never assign, so capabilities compose.
    #
    # Both names are listed. Withholding only the derived SESSIONS_WRITE_TOKEN
    # would leave the same secret in the agent's environment under the
    # contract variable it arrived in.
    AGENTIC_CAPABILITY_WITHHOLD="${AGENTIC_CAPABILITY_WITHHOLD:-} AGENTIC_SESSION_STORE_AUTH SESSIONS_WRITE_TOKEN"
    export AGENTIC_CAPABILITY_WITHHOLD
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
# Persist the opaque tag string in this adapter's own metadata namespace (see
# the two-directories section below for why it is NOT written next to the
# transcripts) so any later sweep is self-describing. This layer still assigns
# no meaning to the value; it just writes the string down.
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
# --- Two directories, two owners ----------------------------------------------
# WHERE TRANSCRIPTS GO and WHERE ADAPTER METADATA GOES are separate questions
# with separate answers, because they have separate owners.
#
#   Transcripts: ${SPOOL}/${PARTITION}/{claude,codex}. This is where the
#   harnesses write, so it is not negotiable, and the operator may point SPOOL
#   and PARTITION at a directory that already holds their data -- the reported
#   configuration was SPOOL=/workspace PARTITION=repos, an existing mount. The
#   ONLY things this adapter does to that directory are `mkdir -p` and creating
#   the two subdirectories it symlinks the harness roots to. It writes no file
#   of its own there and it removes nothing from it, ever.
#
#   Adapter metadata (.capture-env, the exporter's state file): a RESERVED
#   namespace, ${SPOOL}/.agentic-session-store/${PARTITION}/. Unnamespaced
#   metadata writes into the transcript partition were the defect: with the
#   configuration above, an operator's own `.capture-env` in /workspace/repos
#   was destroyed by this adapter before the doctor ever ran, and a `state.json`
#   of theirs would have been overwritten.
#
# The namespace carries an OWNERSHIP MARKER, and a namespace that is missing
# the marker while holding something else, or carrying a marker this adapter
# does not recognise, is REFUSED LOUDLY. It is never emptied, overwritten or
# reused. Refusing costs a workspace start, which is recoverable; overwriting
# somebody else's file is not.
# Checked, not bare: without a writable partition there is nowhere for a
# transcript to land, so continuing would produce a workspace that reports a
# successful init and captures nothing.
if ! mkdir -p "${PART_DIR}"; then
    echo "[session-store] cannot create the transcript partition ${PART_DIR};" \
         "nothing would be captured. Check that the spool is mounted and" \
         "writable by uid $(id -u), or point AGENTIC_SESSION_STORE_SPOOL" \
         "somewhere that is." >&2
    return 1
fi

__META_ROOT="${SPOOL}/.agentic-session-store"
__META_MARKER="${__META_ROOT}/.owner"
# Version the marker so a future layout change is a refusal rather than a
# silent reinterpretation of files written under the old one.
__META_MARKER_ID="agentic-session-store-metadata-v1"
META_DIR="${__META_ROOT}/${PARTITION}"

# Claim the reserved namespace, or fail. Every failure path here reports and
# returns non-zero WITHOUT deleting, truncating or overwriting anything.
__claim_metadata_namespace() {
    if [ -e "${__META_ROOT}" ] && [ ! -d "${__META_ROOT}" ]; then
        echo "[session-store] ${__META_ROOT} exists and is not a directory;" \
             "this adapter reserves that name for its own metadata and will" \
             "not replace what is there. Move it, or point" \
             "AGENTIC_SESSION_STORE_SPOOL at a different root." >&2
        return 1
    fi

    if [ ! -d "${__META_ROOT}" ]; then
        mkdir -p "${__META_ROOT}" || return 1
    fi

    if [ -e "${__META_MARKER}" ]; then
        # A marker that is not a regular file, or holds anything other than
        # this adapter's id, means the namespace belongs to something else.
        if [ ! -f "${__META_MARKER}" ] ||
           [ "$(head -1 "${__META_MARKER}" 2>/dev/null)" != "${__META_MARKER_ID}" ]; then
            echo "[session-store] ${__META_ROOT} carries a foreign or unreadable" \
                 "ownership marker; refusing to write adapter metadata into a" \
                 "namespace this adapter does not own. Nothing was modified." >&2
            return 1
        fi
    else
        # No marker. Claiming an EMPTY directory is safe; claiming one that
        # already has contents would be taking over a directory somebody else
        # created under the reserved name.
        if [ -n "$(ls -A -- "${__META_ROOT}" 2>/dev/null)" ]; then
            echo "[session-store] ${__META_ROOT} exists, has contents and carries no" \
                 "ownership marker; refusing to claim a namespace this adapter did" \
                 "not create. Nothing was modified." >&2
            return 1
        fi
        printf '%s\n' "${__META_MARKER_ID}" > "${__META_MARKER}" || return 1
    fi

    mkdir -p "${META_DIR}" || return 1
    if [ ! -d "${META_DIR}" ]; then
        echo "[session-store] ${META_DIR} is not a directory; refusing to write" \
             "adapter metadata. Nothing was modified." >&2
        return 1
    fi
    return 0
}

if ! __claim_metadata_namespace; then
    # Return before ANY of the layout work below. No symlink is created, so
    # 5.7's symlinks_correct check fails and the operator gets the specific
    # error above plus a named path, rather than a workspace that quietly
    # captured nothing.
    unset -f __claim_metadata_namespace
    echo "[session-store] adapter metadata namespace unavailable; see the doctor output below" >&2
    return 1
fi
unset -f __claim_metadata_namespace

# .capture-env lives in the namespace claimed immediately above, so both of
# the writes below touch a path this adapter has just PROVEN it owns. The
# `rm -f` removes exactly one file this adapter wrote, inside that namespace;
# it is not a prune, it cannot reach a transcript, and it exists because a
# reused partition must never serve a previous run's tags.
#
# EVERY STEP BELOW IS CHECKED, and a failure ends the adapter with `return 1`.
# This is the write whose silent failure costs the most: the session still
# uploads, but with the wrong tags or none, and nothing says so. The operator
# is building a corpus to run learning loops over, so a misattributed row is
# expensive and unfindable after the fact. Failing the init instead costs a
# workspace start, which is recoverable.
__CAPTURE_ENV="${META_DIR}/.capture-env"
if [ -n "${AGENTIC_SESSION_STORE_TAGS:-}" ]; then
    # Encode in two checked steps rather than one pipeline inside the printf
    # below. A pipeline reports only its LAST command's status, so a failing
    # `base64` in `$(... | base64 | tr -d '\n')` would have produced an empty
    # substitution and a perfectly well-formed record claiming the run had no
    # tags. Splitting it makes each stage's status visible without turning on
    # pipefail, which is a shell option this file cannot set: it is sourced,
    # so the setting would persist into the entrypoint and every later
    # command in it.
    #
    # `printf '%s'` (no trailing newline) so the encoded bytes are exactly the
    # tag string, and `tr -d '\n'` because GNU base64 wraps its output at 76
    # columns, which would put the record back on multiple lines.
    if ! __tags_b64_wrapped="$(printf '%s' "${AGENTIC_SESSION_STORE_TAGS}" | base64)" ||
       ! __tags_b64="$(printf '%s' "${__tags_b64_wrapped}" | tr -d '\n')" ||
       [ -z "${__tags_b64}" ]; then
        unset __tags_b64_wrapped __tags_b64
        echo "[session-store] failed to encode the correlation tags for" \
             "${__CAPTURE_ENV}; a recovery sweep would upload this session" \
             "with no tags at all, so the adapter is failing instead." >&2
        return 1
    fi
    unset __tags_b64_wrapped

    # umask, not a post-hoc chmod: a post-hoc chmod leaves a window where the
    # file is created world-readable before the permission fix lands.
    #
    # The subshell's status is the redirect's: if the file cannot be opened,
    # printf never runs and the subshell exits non-zero.
    if ! (
        umask 077
        printf 'SESSION_STORE_TAGS_B64=%s\n' "${__tags_b64}" > "${__CAPTURE_ENV}"
    ); then
        unset __tags_b64
        echo "[session-store] could not write ${__CAPTURE_ENV}; this run's" \
             "sessions would be uploaded with the wrong tags or none, and" \
             "nothing later would report it. Check that the directory is" \
             "writable by uid $(id -u)." >&2
        return 1
    fi
    unset __tags_b64
else
    # A reused partition must never serve a PREVIOUS run's tags, so a stale
    # record that survives is misattribution just as surely as a failed write.
    # `rm -f` is silent on an absent file, so the check is on the outcome
    # rather than on the exit status.
    rm -f "${__CAPTURE_ENV}" 2>/dev/null || true
    if [ -e "${__CAPTURE_ENV}" ]; then
        echo "[session-store] this run has no tags but a previous run's" \
             "${__CAPTURE_ENV} could not be removed; a recovery sweep would" \
             "attribute these sessions to the earlier run. Refusing to start" \
             "rather than mislabel them." >&2
        return 1
    fi
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
# A non-existent path is left to `ln -sfn`, which handles it on its own.
#
# AN EXISTING SYMLINK IS NOT AUTOMATICALLY OURS. `ln -sfn` replaces one
# silently, and that is right for a re-run of this adapter (the link already
# points into the spool) but wrong for a link the operator made: retargeting
# it does not delete their transcripts, but it does silently stop capturing
# where they said to capture, and nothing in the doctor output would say so.
# So a link already pointing into ${SPOOL}, or a dangling one (its target does
# not exist, so nothing can be orphaned), is replaced; anything else is
# refused loudly and left exactly as it is.
__link_transcript_root() {
    local src="$1" dst="$2" label="$3"
    local entry base mv_failed=0 target spool_real

    if [ -L "${src}" ] && [ ! -e "${src}" ]; then
        # Dangling: the link resolves to nothing, so replacing it can orphan
        # nothing.
        ln -sfn "${dst}" "${src}" || return 1
        return 0
    fi

    if [ -L "${src}" ]; then
        target="$(readlink -f "${src}" 2>/dev/null || true)"
        # Compare against the spool BOTH as configured and as resolved: a
        # spool reached through a symlink (or a bind mount presented under a
        # different name) would otherwise make this adapter refuse its own
        # link on the second run.
        spool_real="$(readlink -f "${SPOOL}" 2>/dev/null || true)"
        if [ "${target}" != "${dst}" ] &&
           [ "${target#"${SPOOL}"/}" = "${target}" ] &&
           { [ -z "${spool_real}" ] || [ "${target#"${spool_real}"/}" = "${target}" ]; }; then
            echo "[session-store] ${label}: ${src} is a symlink to ${target}," \
                 "which is outside ${SPOOL}; refusing to retarget a link this" \
                 "adapter did not create. Remove it, or point" \
                 "AGENTIC_SESSION_STORE_SPOOL at that tree." >&2
            return 1
        fi
        ln -sfn "${dst}" "${src}" || return 1
        return 0
    fi

    if [ ! -e "${src}" ]; then
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
# The exporter's state file is ADAPTER METADATA, not a transcript, so it goes
# in the reserved namespace with .capture-env rather than into a partition
# directory the operator may own. The exporter treats this purely as a path to
# read and write, so relocating it changes nothing for it; finalize.sh derives
# both directories from this one variable (see its header).
export EXPORTER_STATE_FILE="${META_DIR}/state.json"

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
