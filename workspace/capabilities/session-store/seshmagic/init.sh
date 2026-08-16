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

# --- This run's init-completion token -----------------------------------------
# Minted FIRST, before anything can fail, and written to the marker file LAST,
# after every consequential step has succeeded (see the end of this file). The
# doctor at entrypoint.sh 5.7 compares the two.
#
# WHY A TOKEN RATHER THAN JUST A FILE. The spool outlives the container by
# design, so a marker whose only job was to exist would still be there on the
# next run: an init that failed before writing anything would be vouched for by
# its predecessor's file, which is the stale state this marker exists to
# detect, one layer up. A token that is fresh per run cannot do that, on a
# persisted spool or a persisted $HOME.
#
# Clearing a previous run's marker here instead was considered and rejected:
# the clear is itself a write, and the case that matters most is exactly the
# one where writes fail, so a failed clear would leave the stale marker in
# place and pass.
#
# The value is assigned unconditionally, never defaulted from the environment,
# so a value injected into the container cannot stand in for one this adapter
# minted. It is not a secret and is deliberately not withheld from the agent:
# an on-demand doctor re-run later needs it to say anything true.
AGENTIC_SESSION_STORE_INIT_TOKEN="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || true)"
if [ -z "${AGENTIC_SESSION_STORE_INIT_TOKEN}" ]; then
    # No /proc (this file also runs outside the workspace image in tests).
    # $$ separates concurrent processes, the nanosecond clock separates
    # sequential ones, and $RANDOM covers a coarse `date` on a host without
    # %N.
    AGENTIC_SESSION_STORE_INIT_TOKEN="$$-$(date -u +%s%N 2>/dev/null)-${RANDOM}${RANDOM}"
fi
export AGENTIC_SESSION_STORE_INIT_TOKEN

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
    if [ -L "${__META_ROOT}" ]; then
        # Checked BEFORE the -d test below, because -d follows a link: a
        # symlink to a directory passes that test, and the marker would then
        # be read from, and possibly written to, whatever it points at. The
        # spool root itself may legitimately be a link or a bind mount
        # presented under another name; the reserved name under it may not,
        # because nothing but this adapter is supposed to create it.
        echo "[session-store] ${__META_ROOT} is a symlink; this adapter reserves" \
             "that name for its own metadata and will not write through a link" \
             "it did not create. Nothing was modified. Remove it, or point" \
             "AGENTIC_SESSION_STORE_SPOOL at a different root." >&2
        return 1
    fi

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
        # The marker is created with O_CREAT|O_EXCL, exactly as `.capture-env`
        # is below and for the same reason. The two tests above are CHECKS, and
        # a check has a window after it: a plain `>` here would FOLLOW a symlink
        # planted at this name in that window and truncate whatever it points
        # at, which is the unnamespaced-write defect committed by the very code
        # that exists to prevent it. `set -o noclobber` makes `>` refuse ANY
        # existing final component, a symlink included, dangling or not, so the
        # open fails and nothing is followed, truncated or created elsewhere.
        # It buys nothing ABOVE the name: O_EXCL constrains the final component
        # only and the kernel still resolves ${__META_ROOT} normally, so a root
        # swapped for a symlink after the `-L` test at the top of this function
        # is still followed. That remaining window is the same class as the two
        # recorded in the "WHAT IS NOT PROVEN" block below, and it is not closed
        # here either. This is not a write that cannot escape; it is a write
        # that cannot be REDIRECTED BY ITS OWN NAME.
        #
        # The option is set INSIDE this subshell only. This file is SOURCED, so
        # setting it in the parent would persist into the entrypoint and every
        # later command it runs; same reason as the `.capture-env` write below.
        #
        # The status is checked EXPLICITLY because errexit is inert here (see
        # the file header). The subshell's status is the redirect's: if the open
        # fails, printf never runs. Nothing is removed to make room, on this
        # path or any other: a name that appears here is not one this adapter
        # wrote, and its contents are not read or echoed.
        if ! (
            set -o noclobber
            printf '%s\n' "${__META_MARKER_ID}" > "${__META_MARKER}"
        ); then
            echo "[session-store] could not create the ownership marker" \
                 "${__META_MARKER}; either something created that name after this" \
                 "adapter found the namespace empty, in which case the namespace" \
                 "is not this adapter's to claim, or ${__META_ROOT} is not" \
                 "writable by uid $(id -u). Refusing: nothing was written," \
                 "followed or removed." >&2
            return 1
        fi
    fi

    return 0
}

# THE MARKER PROVES ONE DIRECTORY. THE WRITES HAPPEN IN ANOTHER.
#
# Everything above proves ownership of exactly ${__META_ROOT}. Every metadata
# write lands in ${META_DIR}, which is ${__META_ROOT}/${PARTITION}, and
# PARTITION is a multi-component relative path (contract.py accepts any
# relative path with no `..` segment; "w1/p2" is the shape in use). A marker on
# the root says nothing about the components below it. Any of them, the last
# included, could be a SYMLINK, and `mkdir -p` walks a symlinked component
# without a word: the metadata writes would then truncate a file outside the
# namespace whose entire purpose is to contain them. That is the unnamespaced
# write defect again, one directory deeper.
#
# So the chain from the marked root down to ${META_DIR} is built one component
# at a time, with plain `mkdir` and never `mkdir -p`:
#
#   * `mkdir` creates the FINAL component itself and does not resolve a
#     symlink sitting at that name; on any existing name it fails with EEXIST.
#     A success is therefore PROOF, not a check, that a real directory now
#     exists at exactly that path because this adapter just created it.
#   * An EEXIST is classified, never repaired. A symlink, or anything that is
#     not a directory, is refused loudly with nothing removed or replaced.
#     Only a real directory is accepted and walked through, which is the
#     re-run case: inside a namespace the marker proves this adapter owns.
#
# TOCTOU. Accepting an existing directory is a check, and a check has a window
# after it. Two things narrow that window, and neither of them shuts it:
#
#   * The completed chain is re-resolved and the PHYSICAL path of ${META_DIR}
#     must equal the physical path of the marked root plus the partition
#     components. A component swapped for a link DURING the walk shows up
#     here, before the first write. A component swapped AFTER this resolve
#     does not.
#   * `.capture-env` is created with O_CREAT|O_EXCL (`set -o noclobber`,
#     below), which refuses ANY existing name including a symlink, dangling or
#     not, so a link planted at THAT NAME after the resolve makes the write
#     fail loudly instead of receiving it. O_EXCL applies to the final
#     component only; it does not stop the kernel resolving a symlinked parent
#     on the way to it.
#
# What remains open after both, including the exporter's state file, which
# this adapter never opens, is spelled out where ${META_DIR} is handed to the
# writes below. It is a known limitation, not something these checks cover.
__build_owned_metadata_path() {
    local -a __comps=()
    local __comp __path="${__META_ROOT}" __expected __root_real __dir_real

    # `read -a`, not word splitting on a reset IFS: splitting would also glob,
    # and a partition containing `*` is a legal relative path.
    IFS='/' read -r -a __comps <<< "${PARTITION}"

    for __comp in "${__comps[@]}"; do
        # A repeated or trailing slash yields an empty component. It is not a
        # name, so there is nothing to create or classify.
        [ -n "${__comp}" ] || continue
        case "${__comp}" in
            . | ..)
                echo "[session-store] refusing to build ${META_DIR}: the partition" \
                     "component '${__comp}' would leave the reserved namespace." \
                     "Nothing was modified." >&2
                return 1
                ;;
        esac
        __path="${__path}/${__comp}"

        if mkdir "${__path}" 2>/dev/null; then
            continue
        fi
        if [ -L "${__path}" ]; then
            echo "[session-store] ${__path} is a symlink, so adapter metadata" \
                 "written under it would land outside ${__META_ROOT}, the only" \
                 "directory this adapter has proven it owns. Refusing: the link" \
                 "is still there and its target was not read, written or" \
                 "removed. Remove the link, or point" \
                 "AGENTIC_SESSION_STORE_PARTITION at another path." >&2
            return 1
        fi
        if [ -d "${__path}" ]; then
            continue
        fi
        if [ -e "${__path}" ]; then
            echo "[session-store] ${__path} exists and is not a directory;" \
                 "refusing to replace it to make room for adapter metadata." \
                 "Nothing was modified." >&2
            return 1
        fi
        echo "[session-store] cannot create ${__path}; adapter metadata has" \
             "nowhere to go. Check that ${__META_ROOT} is writable by uid" \
             "$(id -u). Nothing was modified." >&2
        return 1
    done

    # Containment, on the physical paths. Both sides are resolved, so a spool
    # reached through a link or a bind mount under another name is fine; what
    # this rejects is ${META_DIR} resolving anywhere other than the partition
    # components under the marked root.
    __root_real="$(readlink -f "${__META_ROOT}" 2>/dev/null || true)"
    __dir_real="$(readlink -f "${META_DIR}" 2>/dev/null || true)"
    __expected="${__root_real}"
    for __comp in "${__comps[@]}"; do
        [ -n "${__comp}" ] || continue
        __expected="${__expected}/${__comp}"
    done
    if [ -z "${__root_real}" ] || [ -z "${__dir_real}" ] ||
       [ "${__dir_real}" != "${__expected}" ]; then
        echo "[session-store] ${META_DIR} resolves to ${__dir_real:-nothing}," \
             "not to ${__expected}, so a component of it is not the directory" \
             "this adapter just proved. Refusing to write adapter metadata." \
             "Nothing was modified." >&2
        return 1
    fi
    return 0
}

if ! __claim_metadata_namespace || ! __build_owned_metadata_path; then
    # Return before ANY of the layout work below. No symlink is created, so
    # 5.7's symlinks_correct check fails and the operator gets the specific
    # error above plus a named path, rather than a workspace that quietly
    # captured nothing.
    unset -f __claim_metadata_namespace __build_owned_metadata_path
    echo "[session-store] adapter metadata namespace unavailable; see the doctor output below" >&2
    return 1
fi
unset -f __claim_metadata_namespace __build_owned_metadata_path

# WHAT IS NOW PROVEN ABOUT ${META_DIR}, EXACTLY, because the writes below rest
# on it and nothing more: ${__META_ROOT} is a real directory carrying this
# adapter's ownership marker; every component from it down to ${META_DIR} was
# either created by a plain `mkdir` that cannot follow a symlink, or found to
# be a real directory and refused otherwise; and ${META_DIR}'s resolved
# physical path, AT THE MOMENT IT WAS RESOLVED, was that marked root plus the
# partition components, so no part of it led out of the namespace then.
#
# WHAT IS NOT PROVEN, written down because the last three versions of this
# comment claimed a guarantee the code does not provide. All of the above is a
# check, and a check has a window after it. Two of those windows are open:
#
#   * O_EXCL, added by the `.capture-env` write below, covers THE FINAL
#     COMPONENT ONLY. It refuses to open a name that already exists, so a
#     symlink planted at `.capture-env` itself after the classification makes
#     the write fail instead of following it. It says nothing about the
#     directories above that name: `open` resolves those normally, so a PARENT
#     swapped for a symlink after the walk finished is still followed, and the
#     write lands wherever it points.
#   * The exporter's state file, ${META_DIR}/state.json, gets no O_EXCL at
#     all. This adapter only classifies the NAME (below) and then exports the
#     path in EXPORTER_STATE_FILE; the file is opened later, by the
#     exporter, in a different process, after the agent has run. Every window
#     between here and there is unobserved by anything.
#
# Both are races that a writer with access to ${SPOOL} could win, and NEITHER
# IS CLOSED HERE. Closing them needs per-component openat with O_NOFOLLOW from
# a directory fd, which this shell cannot express, so it is recorded as a known
# limitation of the adapter rather than half-fixed with more checks. Do not
# reword any of the above into a claim that the writes cannot escape.
#
# The `rm -f` names exactly one file inside that namespace, and runs only
# after that name has been classified and refused if it was anything other
# than a regular file (with the same window caveat as everything else here);
# it is not a prune, no transcript directory is on that path, and it exists
# because a reused partition must never serve a previous run's tags.
#
# EVERY STEP BELOW IS CHECKED, and a failure ends the adapter with `return 1`.
# This is the write whose silent failure costs the most: the session still
# uploads, but with the wrong tags or none, and nothing says so. The operator
# is building a corpus to run learning loops over, so a misattributed row is
# expensive and unfindable after the fact. Failing the init instead costs a
# workspace start, which is recoverable.
__CAPTURE_ENV="${META_DIR}/.capture-env"

# The record's own NAME is classified before either branch below touches it,
# for the same reason every component of the path was. A symlink here is not a
# file this adapter wrote: `>` would truncate whatever it points at, and
# `rm -f` would drop the link while reporting the stale record gone. Both
# branches would then have done something other than what they say. So this is
# a refusal, and nothing is removed on the way out. The exporter's state file
# is checked with it: the exporter opens that path itself, so a link left at
# the name would send its writes out of the namespace, and this adapter is the
# only thing that looks at the path before it is used. For the state file this
# check is ALL there is, and it is a check made now about an open that happens
# in another process after the agent has run, so it rules out a link that is
# already there and nothing that appears afterwards.
__STATE_FILE="${META_DIR}/state.json"
# The init-completion marker (written at the very end of this file) is
# classified with them, for the same reason and with the same window caveat.
# Its name is restated in agentic_session_store.contract as INIT_MARKER_NAME,
# because the doctor has to find the same file; the two spellings must agree.
__INIT_MARKER="${META_DIR}/.init-complete"
for __meta_file in "${__CAPTURE_ENV}" "${__STATE_FILE}" "${__INIT_MARKER}"; do
    if [ -L "${__meta_file}" ]; then
        echo "[session-store] ${__meta_file} is a symlink, so it is not a file" \
             "this adapter wrote; refusing to write through it or to remove it." \
             "Nothing was modified." >&2
        unset __meta_file
        return 1
    fi
    if [ -e "${__meta_file}" ] && [ ! -f "${__meta_file}" ]; then
        echo "[session-store] ${__meta_file} exists and is not a regular file;" \
             "refusing to replace it. Nothing was modified." >&2
        unset __meta_file
        return 1
    fi
done
unset __meta_file

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
    #
    # `set -o noclobber` makes `>` open with O_CREAT|O_EXCL, and O_EXCL refuses
    # to open ANY name that already exists, a symlink included, dangling or
    # not (verified in this image: `set -o noclobber; printf x > link` fails
    # for a link to an existing file AND for a dangling one, and the target is
    # neither truncated nor created). What that buys, exactly: the
    # classification above has a window after it, and a link planted AT THIS
    # NAME in that window fails this open instead of being followed. It buys
    # nothing above the name, because O_EXCL constrains the final component
    # only and the kernel still resolves the parent directories normally, so
    # this is not a write that cannot escape the namespace. See the
    # "WHAT IS NOT PROVEN" block above for the two windows that stay open.
    # The stale record is removed first because O_EXCL will not
    # truncate one, and by here the name has already been proven to be a
    # regular file or absent.
    #
    # The option is set INSIDE this subshell only. The file is sourced, so
    # setting it in the parent would persist into the entrypoint and every
    # later command it runs; the same reason pipefail is not used above.
    if ! (
        umask 077
        set -o noclobber
        rm -f "${__CAPTURE_ENV}" &&
            printf 'SESSION_STORE_TAGS_B64=%s\n' "${__tags_b64}" > "${__CAPTURE_ENV}"
    ); then
        unset __tags_b64
        echo "[session-store] could not write ${__CAPTURE_ENV}; this run's" \
             "sessions would be uploaded with the wrong tags or none, and" \
             "nothing later would report it. Check that the directory is" \
             "writable by uid $(id -u), and that nothing else is creating that" \
             "name underneath this adapter." >&2
        return 1
    fi
    unset __tags_b64
else
    # A reused partition must never serve a PREVIOUS run's tags, so a stale
    # record that survives is misattribution just as surely as a failed write.
    # `rm -f` is silent on an absent file, so the check is on the outcome
    # rather than on the exit status. The name has already been refused above
    # if it is anything but a regular file or absent, so this removes a record
    # this adapter wrote and nothing else.
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
# AN EXISTING SYMLINK IS NOT AUTOMATICALLY OURS, AND "UNDER THE SPOOL" IS NOT
# A PROOF THAT IT IS. `ln -sfn` replaces a link silently, which is right for a
# re-run of this adapter and wrong for anybody else's link: retargeting it
# deletes no transcript, but it does stop capture happening where the operator
# said to capture it, from that moment on, and nothing in the doctor output
# would say so.
#
# This used to accept any link whose target was anywhere beneath ${SPOOL}.
# That test proves neither of the two things it was standing in for. It does
# not prove this adapter created the link: the spool is a directory the
# operator owns and may point anything into. And it does not prove the link
# points at THIS run's partition: a link into a DIFFERENT partition under the
# same spool passed it and was silently repointed, so the transcripts still
# being written to the old destination stopped being captured, and the path
# that had been the capture destination was lost from the log.
#
# THE OWNERSHIP TEST IS THE TARGET ITSELF. The only value this adapter ever
# writes at this name is ${dst}, the harness directory of the partition this
# run captures into, so a link that already holds that value is provably one
# of ours (or already correct, which is the same outcome) and a link holding
# anything else is provably not. That is the same shape as the metadata
# namespace's ownership marker: a positive mark this adapter put there, rather
# than an inference from where the thing happens to live.
#
# Both spellings count as a match, because they are the same link written two
# ways: the raw target text equal to ${dst}, or the resolved physical path
# equal to the resolved ${dst}. The second is what keeps a spool reached
# through a symlink, or a bind mount presented under another name, from making
# this adapter refuse its own link on the second run. ${dst} exists by the
# time this runs (the caller `mkdir -p`s it), so it always resolves.
#
# ANYTHING ELSE IS REFUSED LOUDLY AND LEFT EXACTLY AS IT IS, including a
# DANGLING link, which the previous version replaced on the grounds that
# nothing can be orphaned. Nothing is orphaned, but the operator's stated
# destination is still discarded, and a dangling link is a normal state for a
# tree in the middle of being set up or repaired. It also cannot be one of
# ours: ${dst} exists, so a link this adapter wrote does not dangle. Refusing
# costs a workspace start with a named path in the error, which is
# recoverable.
__link_transcript_root() {
    local src="$1" dst="$2" label="$3"
    local entry base mv_failed=0 target_raw target dst_real

    if [ -L "${src}" ]; then
        target_raw="$(readlink "${src}" 2>/dev/null || true)"
        target="$(readlink -f "${src}" 2>/dev/null || true)"
        dst_real="$(readlink -f "${dst}" 2>/dev/null || true)"
        if [ "${target_raw}" = "${dst}" ] ||
           { [ -n "${target}" ] && [ -n "${dst_real}" ] && [ "${target}" = "${dst_real}" ]; }; then
            # Already this run's capture destination. Rewriting it is a no-op
            # in effect and keeps the re-run path a single code path.
            ln -sfn "${dst}" "${src}" || return 1
            return 0
        fi
        echo "[session-store] ${label}: ${src} is a symlink to" \
             "${target_raw:-an unreadable target}, not to ${dst}; refusing to" \
             "retarget a link this adapter did not create. Being under the" \
             "spool would not make it this adapter's, and repointing it would" \
             "silently move capture away from where it currently goes. The" \
             "link is untouched and its target was not read, written or" \
             "removed. Remove the link, or point" \
             "AGENTIC_SESSION_STORE_PARTITION at the partition it already" \
             "names." >&2
        return 1
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
# both directories from this one variable (see its header). The name was
# classified with .capture-env above, so what is handed over is a path inside
# the proven namespace holding either a regular file or nothing.
export EXPORTER_STATE_FILE="${__STATE_FILE}"

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

# --- Record that this init completed ------------------------------------------
# LAST, and reached only when every step above returned success, because the
# doctor's init_complete check reads this file as a statement that all of them
# did. Anything added to this adapter belongs ABOVE this write: a marker
# written before the work it vouches for is worse than no marker, since it
# converts a detectable failure into a pass.
#
# Same write discipline as `.capture-env`: umask so the file is never briefly
# world-readable, `set -o noclobber` (O_CREAT|O_EXCL) inside a subshell so a
# name planted here after the classification above fails the open instead of
# being followed, the stale record removed first because O_EXCL will not
# truncate one, and the subshell's status checked explicitly because errexit
# is inert in this file. Both options are set inside the subshell only: this
# file is sourced, so setting either in the parent would persist into the
# entrypoint and every later command it runs.
#
# What O_EXCL buys is the final component and nothing above it; the two open
# windows recorded in the "WHAT IS NOT PROVEN" block above apply here too.
if ! (
    umask 077
    set -o noclobber
    rm -f "${__INIT_MARKER}" &&
        printf '%s\n' "${AGENTIC_SESSION_STORE_INIT_TOKEN}" > "${__INIT_MARKER}"
); then
    echo "[session-store] could not write ${__INIT_MARKER}, so nothing can" \
         "distinguish this run's initialization from a previous one's. Check" \
         "that the directory is writable by uid $(id -u). Failing the init" \
         "rather than starting a workspace whose doctor would have no way to" \
         "tell that it had." >&2
    return 1
fi
return 0
