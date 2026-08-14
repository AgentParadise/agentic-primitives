#!/usr/bin/env bash
# SeshMagic session-store finalize hook (ADR-040).
#
# Sweeps the partition and uploads to the remote store. ALWAYS exits 0:
# a failed upload after an hour of successful agent work must never make
# the phase report as failed.
#
# THIS HOOK NEVER DELETES ANYTHING. The spool is an append-only local cache
# and the store is the durable copy. It used to prune the partition after a
# sweep it judged clean; that capability was removed, because every data-loss
# path found on this branch reached destruction through that one `rm -rf`, and
# each fix for one of them introduced the next. Unbounded spool growth is the
# accepted tradeoff, and reclaiming space is an operator decision made with a
# view of the store that this hook does not have.
#
# The spool is therefore retained on every path, clean or not. Re-sweeping a
# retained partition is safe: the store dedups on content_hash, so a repeat
# sweep is a no-op rather than a corruption risk. What the reporting below
# still does is tell an operator whether everything actually reached the
# store, which is the question the counters answer.

set -u

if [ -z "${SESSION_STORE_URL:-}" ]; then
    exit 0
fi

# TWO DIRECTORIES, derived from one variable.
#
#   __meta_dir  -- where this adapter's own metadata lives (.capture-env and
#                  the exporter state file), inside the reserved
#                  ${SPOOL}/.agentic-session-store/${PARTITION} namespace
#                  init.sh claims and marks.
#   __part_dir  -- where the TRANSCRIPTS live, ${SPOOL}/${PARTITION}. This is
#                  what the reports below mean by "the spool", and it is a
#                  directory the operator may own, so nothing here writes to
#                  it at all.
#
# Both come from EXPORTER_STATE_FILE, which is normally exported by init.sh.
# This hook is also meant to run standalone -- a recovery sweep of a partition
# left behind by a SIGKILLed container (see below) -- where it is unset. A
# bare `${EXPORTER_STATE_FILE%/*}` in that case trips `set -u` and aborts the
# script, breaking the "always exit 0" contract on exactly the failure path
# this recovery mechanism exists to handle.
#
# LEGACY LAYOUT. A spool volume outlives the image, so a partition written by
# an older init.sh has its state file (and .capture-env) directly in the
# transcript partition, with no reserved segment in the path. That shape is
# recognised by the absence of the segment, and the two directories are then
# the same one, which is exactly what was true when those files were written.
readonly __RESERVED_SEGMENT=".agentic-session-store"
if [ -n "${EXPORTER_STATE_FILE:-}" ]; then
    __meta_dir="${EXPORTER_STATE_FILE%/*}"
else
    __meta_dir="<unset>"
fi
case "${__meta_dir}" in
    */"${__RESERVED_SEGMENT}"/*)
        __part_dir="${__meta_dir%%/"${__RESERVED_SEGMENT}"/*}/${__meta_dir#*/"${__RESERVED_SEGMENT}"/}"
        ;;
    *)
        __part_dir="${__meta_dir}"
        ;;
esac

# Recovery path (EXP-08 arm A5): when invoked without the adapter's env - a
# sweep of a partition left behind by a SIGKILLed container - recover the tags
# the partition was created with. Without this the session uploads untagged
# and is unattributable.
if [ -z "${SESSION_STORE_TAGS:-}" ] && [ -n "${EXPORTER_STATE_FILE:-}" ]; then
    # Current layout first, then the legacy one. On a legacy partition the two
    # paths are identical, so the fallback only ever reaches a DIFFERENT file
    # when a spool holds a partition written before the metadata namespace
    # existed -- the same crash-recovery case the legacy tag record serves.
    __capture_env="${__meta_dir}/.capture-env"
    if [ ! -r "${__capture_env}" ] && [ -r "${__part_dir}/.capture-env" ]; then
        __capture_env="${__part_dir}/.capture-env"
    fi
    if [ -r "${__capture_env}" ]; then
        # PARSE, never source. Tags are opaque orchestrator input; sourcing
        # them is arbitrary code execution at sweep time, with the store
        # write token in scope. Verified during Tasks 5+6 review: a tag of
        # `workflow:$(touch /tmp/PWNED)` executed on source, and any tag
        # containing a space silently truncated the value to empty --
        # destroying the very attribution this file exists to preserve.
        #
        # The current record is SESSION_STORE_TAGS_B64=<base64>. base64 is
        # what lets an opaque tag containing a NEWLINE survive a
        # line-oriented file; before it, a multi-line tag was truncated at
        # the first line. Decoding cannot reintroduce shell interpretation:
        # the decoded bytes are only ever assigned to a variable, never
        # evaluated.
        #
        # RESOLVE FIRST, ANNOUNCE SECOND. A record being ABSENT is its own
        # case, never the legacy case.
        #
        # This used to branch the fallback on "no _B64 record" rather than
        # on "a legacy record actually matched". A .capture-env that is
        # readable but holds neither record - truncated, empty, or foreign,
        # which is exactly what a spool volume outliving the image produces,
        # the precise case this branch exists to serve - then took the
        # legacy path and printed BOTH the legacy notice and "recovered
        # tags" while recovering nothing. Two false signals on one path: a
        # recovery that did not happen, and a claim that pre-_B64 partitions
        # are still in circulation when they may not be. The notice exists
        # to make a real condition visible, so it must never manufacture one.
        #
        # A record present with an EMPTY value counts as no usable record.
        # init.sh writes this file only when the tag string is non-empty, so
        # that shape is already corrupt, and "recovered an empty tag" is the
        # same false signal in a different costume. A _B64 record that fails
        # to decode is treated the same way, for the same reason.
        __tags_value=""
        __tags_source="none"

        __tags_b64="$(sed -n 's/^SESSION_STORE_TAGS_B64=//p' "${__capture_env}" | head -1)"
        if [ -n "${__tags_b64}" ]; then
            # `read -r -d ''` rather than `$(base64 -d)`: command
            # substitution strips ALL trailing newlines, so a tag that
            # legitimately ends in one would not round-trip byte-exact.
            # Reading to a NUL delimiter (which a value out of the
            # environment can never contain) keeps every byte. read returns
            # non-zero at EOF without finding the delimiter and still
            # assigns, which is why the `|| true` is correct and not a
            # swallowed error. The later plain assignment out of
            # __tags_value keeps those trailing bytes too, where a command
            # substitution there would have thrown them away again.
            IFS= read -r -d '' __tags_value \
                < <(printf '%s' "${__tags_b64}" | base64 -d 2>/dev/null) || true
            if [ -n "${__tags_value}" ]; then
                __tags_source="b64"
            fi
        else
            # LEGACY record, written by an init.sh from before the base64
            # change. The spool volume outlives the image: a partition left
            # by a SIGKILLed container running the older adapter can be swept
            # by this finalize, and that crash-recovery case is the entire
            # reason this file exists. Dropping the fallback would silently
            # upload those sessions unattributed. Same parse as before, still
            # data, still never sourced; it just cannot carry a newline.
            #
            # THIS IS A MIGRATION AFFORDANCE, NOT A SUPPORTED FORMAT. Nothing
            # writes this record any more. It exists only to drain partitions
            # that predate the _B64 change, and it may be deleted once a scan
            # of every spool volume still in use finds no such record (the
            # capability README gives the exact command). The notice below is
            # how an operator learns a legacy partition is still out there: a
            # silent fallback means nobody ever finds out it is safe to
            # remove, and a notice that fires on the no-record case would
            # mean they could never trust it either.
            __tags_value="$(sed -n 's/^SESSION_STORE_TAGS=//p' "${__capture_env}" | head -1)"
            if [ -n "${__tags_value}" ]; then
                __tags_source="legacy"
            fi
        fi

        case "${__tags_source}" in
            b64)
                SESSION_STORE_TAGS="${__tags_value}"
                export SESSION_STORE_TAGS
                echo "[finalize] recovered tags from ${__capture_env}" >&2
                ;;
            legacy)
                SESSION_STORE_TAGS="${__tags_value}"
                export SESSION_STORE_TAGS
                echo "[finalize] NOTE: ${__capture_env} uses the legacy pre-base64" \
                     "SESSION_STORE_TAGS record; this partition predates the current" \
                     "adapter. Tags were recovered, but a tag containing a newline" \
                     "would have been truncated when it was written" >&2
                echo "[finalize] recovered tags from ${__capture_env}" >&2
                ;;
            *)
                # No recovery happened, so nothing claims one. Leave
                # SESSION_STORE_TAGS unset: the upload goes ahead untagged,
                # which is the same outcome as a missing .capture-env and is
                # reported the same way.
                echo "[finalize] WARNING: ${__capture_env} is readable but holds no" \
                     "usable tag record (expected SESSION_STORE_TAGS_B64=<base64>);" \
                     "no tags were recovered and this upload will be unattributable" >&2
                ;;
        esac
        unset __tags_b64 __tags_value __tags_source
    else
        echo "[finalize] WARNING: no tags in env and no ${__capture_env}; " \
             "this upload will be unattributable" >&2
    fi
fi

# Bound the sweep. An unbounded exporter (stuck DNS lookup, hung connection,
# wedged filesystem) turns a completed agent run into a hang, and during
# `docker stop` it burns the remaining grace until SIGKILL, so the run reports
# 137 instead of the agent's real exit code.
#
# THE BUDGET IS ASYMMETRIC, because the deadline only exists on one path.
# entrypoint.sh calls __run_finalizers on BOTH exits, but its escalation window
# only runs when the agent's status is >128, i.e. the signal path. On an
# ordinary agent exit there is no `docker stop -t 5` ticking and nothing to stay
# inside. A single tight bound applied to both would kill a legitimate 4s sweep
# on every normal run, so for a heavy user no sweep would ever complete and
# their transcripts would never reach the store. So entrypoint.sh picks the
# budget and passes it in:
#
#   * SIGNAL path -- tight. Two constants bound the window: entrypoint.sh's
#     __TERM_GRACE_TICKS (15 x 0.1s = 1.5s before a stubborn agent is escalated
#     to SIGKILL) and docker.py's `docker stop -t` of 5s
#     (lib/python/agentic_isolation/agentic_isolation/providers/docker.py).
#     Measured through the real entrypoint on 2026-08-14, escalation completes
#     at ~1.66s for a stubborn agent (`trap "" TERM`), leaving ~3.3s of the 5s.
#     2s finishes at ~3.66s, a 1.3s margin. 3s would finish at ~4.66s, a 0.34s
#     margin, too thin to be reliable.
#   * CLEAN exit -- generous. Nothing is waiting on us, so the bound exists only
#     to stop a wedged exporter hanging forever, not to hit a deadline.
#
# The default below is the generous one, because an unset budget means this hook
# was invoked standalone (a recovery sweep of a partition left by a SIGKILLed
# container, see the EXPORTER_STATE_FILE note above), and that too has no grace
# ticking. A non-numeric value is ignored rather than trusted.
#
# A timeout is an upload FAILURE: report it and exit 0. The spool is kept, as
# it is on every other path.
readonly __UPLOAD_TIMEOUT_DEFAULT_S=120
case "${AGENTIC_FINALIZE_BUDGET_S:-}" in
    "" | *[!0-9]* | 0) __UPLOAD_TIMEOUT_S="${__UPLOAD_TIMEOUT_DEFAULT_S}" ;;
    *) __UPLOAD_TIMEOUT_S="${AGENTIC_FINALIZE_BUDGET_S}" ;;
esac
readonly __UPLOAD_TIMEOUT_S

# `-k 1`: GNU timeout sends only SIGTERM at the deadline and then WAITS. A child
# blocked in uninterruptible I/O or ignoring TERM leaves timeout waiting too, so
# the bound silently becomes unbounded -- precisely the "wedged filesystem" case
# named above, which is the one least likely to die on TERM. -k follows with
# SIGKILL 1s later, which is what makes this an actual bound.
readonly __UPLOAD_KILL_AFTER_S=1

# Both the exporter's stdout and stderr go to OUR stderr, never our stdout.
# Under the old `exec "$@"`, container stdout was exclusively the agent's;
# now that finalize runs after the agent exits, letting exporter chatter
# reach stdout would corrupt anything parsing it (e.g. an agent CMD invoked
# with a structured --output-format). We capture both streams into a variable
# (`2>&1` inside the command substitution) and replay them to fd2, which keeps
# that stdout-cleanliness property while making the exporter's machine-readable
# summary line available to the reporting below.
__exporter_out="$(timeout -k "${__UPLOAD_KILL_AFTER_S}" "${__UPLOAD_TIMEOUT_S}" \
    SeshMagicSessionExporter 2>&1)"
__exporter_rc=$?
if [ -n "${__exporter_out}" ]; then
    printf '%s\n' "${__exporter_out}" >&2
fi

# 124 is timeout's own "deadline reached"; 137 is what surfaces when -k had to
# follow through with SIGKILL. Both mean the same thing here.
if [ "${__exporter_rc}" -ne 0 ]; then
    if [ "${__exporter_rc}" -eq 124 ] || [ "${__exporter_rc}" -eq 137 ]; then
        echo "[finalize] session-store upload TIMED OUT after ${__UPLOAD_TIMEOUT_S}s;" \
             "spool retained at ${__part_dir}" >&2
    else
        echo "[finalize] session-store upload FAILED (rc=${__exporter_rc});" \
             "spool retained at ${__part_dir}" >&2
    fi
    exit 0
fi

# A CLEAN EXIT IS NOT A CLEAN SWEEP, so the exit code alone is not a report.
# The exporter says so in its own source
# (crates/seshmagic-session-store-exporter/src/bin/exporter.rs):
#
#   // A completed sweep exits 0 even with per-item skips/failures; only a
#   // hard RunError (store unreachable, source scan failure) is non-zero.
#
# So rc=0 is consistent with `failed=3 skipped_oversize=2`, i.e. five
# transcripts that never reached the store. Nothing is deleted on any path any
# more, so this is no longer a data-loss question, but an operator still has to
# be told: those five exist only in the spool, and only the store copy is
# durable.
#
# The report reads the summary line the exporter already prints:
#
#   run: discovered=N skipped_unchanged=N uploaded=N accepted=N duplicate=N \
#        rejected=N skipped_oversize=N failed=N
#
# failed, skipped_oversize and rejected are the three counters that mean "this
# transcript is not in the store". A nonzero one is reported as INCOMPLETE and
# named, so the operator knows what to chase.
#
# Note that a rejected item is reported only by the sweep that hit it. The
# exporter marks state for every item the store returned a result for, rejected
# included (lib.rs:202-204), so the NEXT sweep counts it as skipped_unchanged
# and reads clean. failed and skipped_oversize are left unmarked and so recur
# until they resolve.
#
# duplicate and skipped_unchanged are NOT failures and must never be reported as
# such: duplicate means the store already holds that content (it dedups on
# content_hash) and skipped_unchanged means a prior sweep already uploaded the
# file. Both are confirmations, not losses.
#
# No parseable summary means no evidence of success, so it is reported as
# unknown rather than as complete. That is also what covers the timeout path
# above reaching this far by any future edit: a killed exporter prints no
# summary.
__summary="$(printf '%s\n' "${__exporter_out}" | grep -E '^run: .*[[:space:]]failed=[0-9]+' | tail -1)"

__counter() {
    # $1 = counter name, read out of ${__summary}. Prints nothing if absent.
    printf '%s' "${__summary}" | sed -n "s/.*[[:space:]]$1=\([0-9][0-9]*\).*/\1/p"
}

__failed="$(__counter failed)"
__oversize="$(__counter skipped_oversize)"
__rejected="$(__counter rejected)"

if [ -z "${__summary}" ] || [ -z "${__failed}" ] || [ -z "${__oversize}" ] || [ -z "${__rejected}" ]; then
    echo "[finalize] session-store sweep produced no parseable summary line;" \
         "treating as INCOMPLETE, spool retained at ${__part_dir}" >&2
    exit 0
fi

__incomplete=""
[ "${__failed}" -ne 0 ] && __incomplete="${__incomplete} failed=${__failed}"
[ "${__oversize}" -ne 0 ] && __incomplete="${__incomplete} skipped_oversize=${__oversize}"
[ "${__rejected}" -ne 0 ] && __incomplete="${__incomplete} rejected=${__rejected}"

if [ -n "${__incomplete}" ]; then
    echo "[finalize] session-store sweep INCOMPLETE (${__incomplete# }): at least one transcript" \
         "did not reach the store; spool retained at ${__part_dir}" >&2
    exit 0
fi

# A clean sweep is reported and nothing else happens: the partition and every
# transcript in it stay exactly where they are. That is the whole contract now,
# so say so, because this line used to be followed by a delete.
echo "[finalize] session-store upload complete (${__summary#run: });" \
     "spool retained at ${__part_dir}" >&2

exit 0
