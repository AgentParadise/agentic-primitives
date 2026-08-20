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
# store.
#
# ONE SWEEP'S COUNTERS CANNOT ANSWER THAT ON THEIR OWN, and this header used
# to say they could. A transcript the store REJECTED is marked done in the
# exporter's state file, so every later sweep counts it as skipped_unchanged
# and every blocking counter reads zero. The counters of the later sweep are
# therefore consistent with a transcript that was refused and is not in the
# store, which is why this file also keeps a persisted record of a rejection
# and consults it before it reports a completed upload. See the
# "A REJECTION IS REMEMBERED" block below.
#
# THIS HOOK WRITES ONE FILE, and until that block was added it wrote none at
# all. The file is `.sweep-rejected`, created only inside the reserved
# ${SPOOL}/.agentic-session-store/${PARTITION} metadata namespace init.sh
# claims and marks, never in the transcript partition, which the operator may
# own. It is created and never removed: this hook still deletes nothing.

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
# Both come from EXPORTER_STATE_FILE, which init.sh exports.
#
# THIS HOOK IS NOT A STANDALONE RECOVERY TOOL, and this header used to say it
# was. The claim was never implemented and could not be satisfied by anything
# in this file: run without the adapter's environment, it has no store URL, no
# credential, no spool, no partition and no transcript roots, so the guard at
# the top of the file returns 0 immediately and an operator following the
# documented procedure got silence and a success status. A hook that must
# always exit 0 is the worst possible place to put a procedure that can fail
# invisibly.
#
# What a recovery sweep of a partition left by a SIGKILLed container actually
# is: START A WORKSPACE with the same AGENTIC_SESSION_STORE_SPOOL and
# AGENTIC_SESSION_STORE_PARTITION and let this hook run under the adapter's
# environment, exactly as it does on any other run. The spool is append-only
# and the store dedups on content_hash, so re-sweeping a partition that was
# already partly uploaded costs nothing. The .capture-env recovery below is
# what makes that sweep attributable, because the tag string died with the
# killed process and the new run may not carry it.
#
# EXPORTER_STATE_FILE IS STILL GUARDED, for a case that is real. The
# entrypoint runs finalizers even when an adapter's init FAILED (5.6 warns
# and continues), so this file can genuinely execute with a store URL in the
# environment and no state file. A bare `${EXPORTER_STATE_FILE%/*}` trips
# `set -u` there and aborts the script, breaking the one contract this hook
# cannot break. That case is now also REPORTED rather than absorbed: see the
# warning below.
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
    # A WARNING, NOT A SKIP, and not silence either. This hook must always
    # exit 0, so "fail loudly" here can only mean saying something an operator
    # can act on. Skipping the sweep would be worse than sweeping blind: the
    # exporter can still find transcripts through its own defaults, and
    # refusing to run would strand them for a reason nobody asked for.
    #
    # Everything that is degraded is named, because each one changes what the
    # report below means: the spool cannot be named in any later line, this
    # partition's .capture-env cannot be found so a killed run's tags cannot
    # be recovered, and the exporter falls back to whatever state file its own
    # defaults pick, which is not this partition's and so re-offers work a
    # previous sweep already did.
    __meta_dir="(unknown: EXPORTER_STATE_FILE is unset)"
    echo "[finalize] WARNING: EXPORTER_STATE_FILE is unset, so this hook is" \
         "running without the session-store adapter's environment. Either" \
         "init.sh did not complete (the doctor output above says why) or this" \
         "hook was invoked by hand, which is not supported: it is not a" \
         "standalone recovery tool. The sweep still runs so nothing is" \
         "stranded, but it cannot name the spool it swept, it cannot recover" \
         "this partition's tags from .capture-env, so the upload may be" \
         "unattributable, and the exporter will use a default state file" \
         "rather than this partition's. To sweep a partition left behind by a" \
         "killed container, start a workspace with the same" \
         "AGENTIC_SESSION_STORE_SPOOL and AGENTIC_SESSION_STORE_PARTITION and" \
         "let this hook run normally." >&2
fi
#
# The same classification decides WHERE, and whether, a rejection can be
# recorded. `__rejection_record` is a path only on the current layout, where
# the reserved segment proves the metadata directory is the namespace init.sh
# claimed and marked. On the legacy layout the metadata directory IS the
# transcript partition, which the operator may own and into which this adapter
# writes no file of its own, ever; on the unset-EXPORTER_STATE_FILE path there
# is no directory at all, only a placeholder string. Both leave it empty, and
# an empty value means "a rejection cannot be remembered here", which is
# reported rather than worked around. Refusing to write is the only option
# that does not put this hook's file into somebody else's directory.
case "${__meta_dir}" in
    */"${__RESERVED_SEGMENT}"/*)
        __part_dir="${__meta_dir%%/"${__RESERVED_SEGMENT}"/*}/${__meta_dir#*/"${__RESERVED_SEGMENT}"/}"
        __rejection_record="${__meta_dir}/.sweep-rejected"
        ;;
    *)
        __part_dir="${__meta_dir}"
        __rejection_record=""
        ;;
esac

# Recovery path (EXP-08 arm A5): a sweep that reaches a partition an earlier,
# killed run left behind has no SESSION_STORE_TAGS, because that value died
# with that process, so recover the tags the partition was created with.
# Without this the session uploads untagged and is unattributable.
#
# This runs on any normal workspace start whose spool and partition were used
# before and whose own environment carries no tags; it needs no special
# invocation, which is exactly why none is offered.
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
        # to decode is its own case, reported as such: see decode_failed
        # below.
        __tags_value=""
        __tags_source="none"

        __tags_b64="$(sed -n 's/^SESSION_STORE_TAGS_B64=//p' "${__capture_env}" | head -1)"
        if [ -n "${__tags_b64}" ]; then
            # THE DECODE STATUS IS CHECKED IN A STEP OF ITS OWN, because the
            # read below cannot report it. A process substitution's exit
            # status is not the status of the command it feeds, and nothing
            # else looks at it either, so a corrupt or truncated payload used
            # to leave __tags_value empty or partial with no error anywhere:
            # the sweep then uploaded the session untagged while the file's
            # only complaint was the generic "no usable record". Silent
            # misattribution is the failure this whole recovery path exists
            # to prevent.
            #
            # Here `base64` is the LAST command of the pipeline, so the
            # pipeline's status IS base64's status without needing pipefail,
            # and the decoded bytes are thrown away: this run answers only
            # "does the payload decode", and the read below is what keeps the
            # bytes.
            #
            # THIS GUARD DEPENDS ON A STRICT DECODER, AND IS INERT UNDER BSD
            # `base64`. That is fine here, because this file only ever runs in
            # the Linux container, but it will mislead you if you test it on a
            # Mac. Same four payloads, measured on both:
            #
            #   payload        macOS (BSD)   container (GNU/busybox)
            #   YT0x           accepted      accepted     (valid)
            #   !!!!bad!!!!    rejected      rejected     (invalid chars)
            #   aGVsbG8        ACCEPTED      rejected     (unpadded)
            #   YT0            ACCEPTED      rejected     (truncated)
            #
            # So on a Mac a truncated record decodes cleanly, `__tags_source`
            # becomes b64, and this guard appears not to work. It is the
            # decoder that is lenient, not the check that is broken. Verify
            # this inside the image, not on the host.
            if ! printf '%s' "${__tags_b64}" | base64 -d > /dev/null 2>&1; then
                __tags_source="decode_failed"
            else
                # `read -r -d ''` rather than `$(base64 -d)`: command
                # substitution strips ALL trailing newlines, so a tag that
                # legitimately ends in one would not round-trip byte-exact.
                # Reading to a NUL delimiter (which a value out of the
                # environment can never contain) keeps every byte. read
                # returns non-zero at EOF without finding the delimiter and
                # still assigns, which is why the `|| true` is correct and
                # not a swallowed error; the decode's own status was taken
                # above, where it is observable. The later plain assignment
                # out of __tags_value keeps those trailing bytes too, where a
                # command substitution there would have thrown them away
                # again.
                IFS= read -r -d '' __tags_value \
                    < <(printf '%s' "${__tags_b64}" | base64 -d 2>/dev/null) || true
                if [ -n "${__tags_value}" ]; then
                    __tags_source="b64"
                fi
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
            decode_failed)
                # A WARNING, NOT A HARD FAILURE, and deliberately so. This
                # hook must always exit 0 and must never alter the run's exit
                # code, so "fatal" could only mean skipping the sweep, which
                # would trade an unattributable upload for a transcript that
                # never reaches the store at all, on the strength of a
                # decision nobody outside stderr would see. Untagged is
                # recoverable: the store holds the transcript, the spool is
                # retained, and the record below is still on disk to be
                # decoded by hand and the session re-attributed. What must
                # never happen is this passing as successful attribution, so
                # SESSION_STORE_TAGS is left unset (an empty export would
                # look like a real value) and the failure is named.
                echo "[finalize] WARNING: the SESSION_STORE_TAGS_B64 record in" \
                     "${__capture_env} does not decode as base64 (corrupt or" \
                     "truncated); no tags were recovered and this upload will be" \
                     "unattributable. The record is left in place: recover it with" \
                     "\`sed -n 's/^SESSION_STORE_TAGS_B64=//p' ${__capture_env} |" \
                     "head -1 | base64 -di\` and re-attribute the session in the" \
                     "store" >&2
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
# only runs on the signal path, which it identifies as "a signal reached the
# wrapper AND the wait returned above 128 because of it" rather than as a
# status above 128 on its own; an agent that exits 200 is an ordinary exit and
# gets the generous budget. On an ordinary agent exit there is no
# `docker stop -t 5` ticking and nothing to stay
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
# The default below is the generous one, because an unset budget means nothing
# in the environment named a deadline, so there is no grace to stay inside and
# the only thing left to bound is a wedged exporter. A non-numeric value is
# ignored rather than trusted.
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

# THE EXPORTER'S OUTPUT IS CAPTURED AND NEVER REPLAYED. Two independent
# reasons, and each one alone is sufficient:
#
#   * STDOUT CLEANLINESS. Under the old `exec "$@"`, container stdout was
#     exclusively the agent's; now that finalize runs after the agent exits,
#     letting exporter chatter reach stdout would corrupt anything parsing it
#     (e.g. an agent CMD invoked with a structured --output-format). Capturing
#     both streams (`2>&1` inside the command substitution) keeps stdout clean
#     whatever the exporter writes to.
#
#   * THE EXPORTER IS NOT PART OF THIS IMAGE. It is a binary the operator
#     mounts or bakes in at deploy time (see the capability README's
#     "Exporter provisioning contract"), so nothing here can know what any
#     given build of it prints. This block used to replay the captured bytes
#     to fd2 verbatim, which meant a build that dumped its environment,
#     echoed an `Authorization: Bearer ...` diagnostic, or logged a request
#     body put the store's write credential straight into durable container
#     logs, on every single run, with no way for an operator to opt out. That
#     replay is gone.
#
# So the only exporter-derived bytes this file emits are the counters parsed
# out of the summary line below, each of them matched as `[0-9][0-9]*` and
# therefore incapable of carrying anything but digits, printed next to counter
# names this file spells out itself. The report is RECONSTRUCTED, never echoed.
# Resolve the exporter the same way the doctor does: explicit override, then the
# vendor-neutral standard name, then the legacy vendor-branded name. The doctor
# has already established that ONE of these exists (exporter_present), so this
# cannot be the first place a missing binary is discovered.
if [ -n "${AGENTIC_SESSION_STORE_EXPORTER_BIN:-}" ]; then
    __exporter_bin="${AGENTIC_SESSION_STORE_EXPORTER_BIN}"
elif command -v apss-session-exporter >/dev/null 2>&1; then
    __exporter_bin="apss-session-exporter"
else
    __exporter_bin="SeshMagicSessionExporter"
fi

__exporter_out="$(timeout -k "${__UPLOAD_KILL_AFTER_S}" "${__UPLOAD_TIMEOUT_S}" \
    "${__exporter_bin}" 2>&1)"
__exporter_rc=$?

# 124 is timeout's own "deadline reached"; 137 is what surfaces when -k had to
# follow through with SIGKILL. Both mean the same thing here.
#
# WHAT A FAILED SWEEP REPORTS, decided deliberately. The operator still has to
# be able to diagnose it, and the exporter's own diagnostic is the only thing
# that says why it failed -- but that diagnostic is exactly the untrusted
# stream above, so it cannot be copied into a durable log to make the failure
# legible. What this path gives instead is everything this file knows for
# certain (which of the two failure classes it was, the exporter's status, the
# bound it was given, the spool that was kept) plus the procedure that
# recovers the missing half. Re-running the exporter is safe and is not a
# workaround for a lost message: the spool is retained on every path and the
# store dedups on content_hash, so a repeat sweep re-uploads nothing.
# EXIT 3 IS NOT A FAILED SWEEP. agentic-session-exporter reserves it for "the
# sweep RAN but did not capture everything it found": something was rejected,
# oversize, unconfirmed or failed. The summary line is present and accurate, and
# the counter reporting below is exactly what an operator needs to see for it.
#
# Treating it like rc=1 would be a regression twice over: a partial capture
# would be reported as a total upload failure, and this function would exit
# before the rejection record below, which is the only thing that stops a LATER
# sweep printing a false completion claim. Older exporters documented only 0
# and 1, so this is inert against them.
#
# The status is BYPASSED here, not rewritten to 0. An earlier version set it to
# zero, which erased the one fact the exporter had just gone to the trouble of
# telling us: completeness is decided further down from three counters, and a
# sweep whose only loss is `unconfirmed` leaves all three at zero. That sweep
# would have printed "upload complete" while its own exit status said the
# opposite. rc is therefore preserved and consulted again below.
if [ "${__exporter_rc}" -ne 0 ] && [ "${__exporter_rc}" -ne 3 ]; then
    if [ "${__exporter_rc}" -eq 124 ] || [ "${__exporter_rc}" -eq 137 ]; then
        echo "[finalize] session-store upload TIMED OUT after ${__UPLOAD_TIMEOUT_S}s;" \
             "spool retained at ${__part_dir}" >&2
    else
        echo "[finalize] session-store upload FAILED (rc=${__exporter_rc});" \
             "spool retained at ${__part_dir}" >&2
    fi
    echo "[finalize] the exporter's own output is deliberately NOT reproduced" \
         "here: it is an operator-supplied binary, this stream is durable, and" \
         "a build that prints its environment or an auth header would leak the" \
         "store write credential into the logs. To see it, re-run" \
         "${__exporter_bin} by hand with the same environment; the spool" \
         "is retained and the store dedups on content_hash, so a repeat sweep" \
         "uploads nothing twice." >&2
    exit 0
fi

# A CLEAN EXIT IS NOT A CLEAN SWEEP, so the exit code alone is not a report.
#
# This was once absolute: the exporter exited 0 for any completed sweep,
# "even with per-item skips/failures", so rc=0 was consistent with
# `failed=3 skipped_oversize=2`, i.e. five transcripts that never reached the
# store.
#
# agentic-session-exporter now distinguishes them: 3 means the sweep ran and
# did not capture everything, 1 means it could not run. rc=0 from such a build
# genuinely does mean a clean sweep. But this hook still cannot ASSUME it is
# talking to such a build, because the exporter binary is operator-supplied,
# so the counters remain the primary report and rc=3 is treated as additional
# evidence rather than the only evidence. Nothing is deleted on any path any
# more, so this is no longer a data-loss question, but an operator still has to
# be told: those five exist only in the spool, and only the store copy is
# durable.
#
# The report is built from the summary line the exporter prints:
#
#   run: discovered=N skipped_unchanged=N uploaded=N accepted=N duplicate=N \
#        rejected=N skipped_oversize=N failed=N
#
# BUILT FROM, not quoted from. Every value below comes through __counter,
# whose sed expression matches `[0-9][0-9]*` and prints the captured digits
# and nothing else, and every counter NAME is a literal in this file. So the
# reconstructed line cannot carry a byte the exporter chose, which is the
# whole point: see the capture block above for why none of its output is
# trusted enough to appear in this log.
#
# failed, skipped_oversize and rejected are the three counters that mean "this
# transcript is not in the store". A nonzero one is reported as INCOMPLETE and
# named, so the operator knows what to chase.
#
# Note that a rejected item is counted only by the sweep that hit it. The
# exporter marks state for every item the store returned a result for, rejected
# included (lib.rs:202-204), so the NEXT sweep counts it as skipped_unchanged
# and its counters read clean. failed and skipped_oversize are left unmarked
# and so recur until they resolve. That asymmetry is why a rejection, and only
# a rejection, is written down: see the block below the counters.
#
# duplicate and skipped_unchanged are NOT failures and must never be reported as
# such, but they carry different weights and only one of them is evidence.
# duplicate means the store already holds that content, which it knows because
# it dedups on content_hash, so it is a positive statement about the store.
# skipped_unchanged is a statement about the EXPORTER'S STATE FILE and nothing
# else: it means the file has not changed since the exporter last marked it,
# and the exporter marks rejected items too. So skipped_unchanged is consistent
# with "already uploaded" AND with "the store refused it and never will hold
# it", and it cannot tell those apart. Neither is a loss to report per sweep;
# neither is proof of an upload either.
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
# The exporter's own verdict, trusted over this file's arithmetic.
#
# These three counters are the ones this hook knows how to parse, and they are
# not the only way a sweep can come up short. agentic-session-exporter also
# counts `unconfirmed`: envelopes it SENT for which the store returned no
# matching outcome, which are neither accepted nor rejected. A sweep whose only
# loss is unconfirmed has failed=0 oversize=0 rejected=0 and still exits 3.
#
# Deciding completeness from counters this file happens to know about, while
# ignoring a status that says "not everything got there", is how a false
# completion claim gets made by a hook written to prevent them. If the exporter
# says the sweep was incomplete, it was incomplete.
[ "${__exporter_rc}" -eq 3 ] && [ -z "${__incomplete}" ] && \
    __incomplete="${__incomplete} exporter reported an incomplete sweep (rc=3)"

# --- A REJECTION IS REMEMBERED, because the counters forget it ----------------
#
# A rejection is the one outcome that disappears from the counters after the
# sweep that hit it, so it is the one outcome this file writes down.
#
# The exporter marks state for every item the store returned a result for,
# rejected included (crates/seshmagic-session-store-exporter/src/lib.rs:202-204,
# "the store processed it and a re-send would be wasted"). But rejected means
# the store REFUSED the transcript: processed, not stored. So:
#
#   Sweep 1: T rejected  -> rejected=1, reported INCOMPLETE, and recorded here.
#   Sweep 2: state says T is current -> counted as skipped_unchanged. failed,
#            skipped_oversize and rejected all read 0.
#
# Without a record, sweep 2 prints "session-store upload complete" about a
# partition holding a transcript the store refused and will never hold. That is
# a FALSE COMPLETION CLAIM: an operator, or a later automated check that greps
# this log, is told the corpus is whole when a session is silently absent from
# it, and absent sessions are exactly what nothing downstream can notice.
#
# Sweep 2 is not a recovery scenario. It happens on any later run with a stable
# AGENTIC_SESSION_STORE_PARTITION, since only the ${HOSTNAME} default is
# per-container, which is also why the record has to survive the container: it
# lives in the spool, which outlives every container that mounts it.
#
# THIS IS NOT THE OLD PRUNE SENTINEL COMING BACK, though it carries the same
# name. That file gated an `rm -rf` and was deleted along with the prune, on
# the reasoning that it existed only to gate it. That reasoning was incomplete:
# the health signal needs the same memory, and this is the half that was still
# required. Nothing here deletes, moves or truncates anything; it gates a
# REPORT.
#
# ONLY REJECTED IS RECORDED, deliberately. failed and skipped_oversize are left
# unmarked by the exporter, so they are recounted by every sweep and clear on
# their own when they resolve. A record for those would turn one transient
# network blip into a partition that reads INCOMPLETE forever, and an operator
# who stops believing the signal is back where this started.
#
# WRITE DISCIPLINE, the same as init.sh's `.owner`: `set -o noclobber` makes
# `>` open with O_CREAT|O_EXCL inside a subshell, so a name planted at this
# path fails the open instead of being followed and truncated, and the
# subshell's status is checked explicitly because this file runs without
# errexit. Nothing is removed to make room, on any path. There is no umask
# here, unlike `.capture-env`: the content is a fixed literal this file writes
# and holds nothing secret. O_EXCL covers the final component only; a parent
# swapped for a symlink is still resolved, the same known limitation the
# adapter records for every other write into this namespace.
readonly __REJECTION_RECORD_ID="agentic-session-store-rejection-v1"
if [ "${__rejected}" -ne 0 ]; then
    if [ -z "${__rejection_record}" ]; then
        echo "[finalize] WARNING: the store REFUSED ${__rejected} transcript(s), but this" \
             "partition's metadata is not in the reserved ${__RESERVED_SEGMENT} namespace" \
             "(a legacy partition, or EXPORTER_STATE_FILE is unset), so there is nowhere" \
             "this hook is allowed to record it: the only candidate directory holds" \
             "transcripts and the operator may own it. This run's report is therefore the" \
             "ONLY notice of these rejections. A later sweep will count them as" \
             "skipped_unchanged and report a complete upload." >&2
    elif [ -e "${__rejection_record}" ] || [ -L "${__rejection_record}" ]; then
        # Already recorded by an earlier sweep. Nothing to add, and nothing to
        # remove: one unresolved rejection is what the file already says.
        echo "[finalize] the store REFUSED ${__rejected} transcript(s); ${__rejection_record}" \
             "already records an unresolved rejection for this partition" >&2
    elif (
        set -o noclobber
        printf '%s\n' "${__REJECTION_RECORD_ID}" > "${__rejection_record}"
    ); then
        echo "[finalize] recorded ${__rejection_record}: the store REFUSED ${__rejected}" \
             "transcript(s), which the exporter marks as done, so no later sweep can" \
             "re-detect them from its counters" >&2
    else
        echo "[finalize] WARNING: could not write ${__rejection_record}, so the" \
             "${__rejected} transcript(s) the store REFUSED are recorded nowhere and a" \
             "later sweep will report a complete upload. Check that the directory is" \
             "writable by uid $(id -u), and that nothing else is creating that name" \
             "underneath this adapter. This run's report is the only notice." >&2
    fi
fi

if [ -n "${__incomplete}" ]; then
    echo "[finalize] session-store sweep INCOMPLETE (${__incomplete# }): at least one transcript" \
         "did not reach the store; spool retained at ${__part_dir}" >&2
    exit 0
fi

# CLEAN COUNTERS ARE NOT A CLEAN PARTITION while a rejection is unresolved.
# This is the check the counters above cannot make, for the reason spelled out
# in the record block: the item is marked done, so it reads as
# skipped_unchanged forever. The record is consulted on EVERY sweep, including
# ones that discovered nothing at all, because "no work this time" is not
# evidence about work an earlier sweep did.
#
# The record is never removed here. Clearing it is an operator action taken
# after they have looked at the store, which is the same reasoning that
# removed the prune: this hook cannot see the remote side.
if [ -n "${__rejection_record}" ] &&
   { [ -e "${__rejection_record}" ] || [ -L "${__rejection_record}" ]; }; then
    echo "[finalize] session-store sweep INCOMPLETE (unresolved rejection recorded at" \
         "${__rejection_record}): this sweep's counters are clean, but the store REFUSED" \
         "at least one transcript on an earlier sweep and the exporter marks a rejected" \
         "item as done, so it now counts as skipped_unchanged and no sweep can re-detect" \
         "it. That transcript is in the spool at ${__part_dir} and is NOT in the store." \
         "Find out why the store refused it, upload it by hand once that is fixed, then" \
         "remove ${__rejection_record} to acknowledge; this hook never removes it and" \
         "will keep reporting INCOMPLETE until you do." >&2
    exit 0
fi

# A clean sweep is reported and nothing else happens: the partition and every
# transcript in it stay exactly where they are. That is the whole contract now,
# so say so, because this line used to be followed by a delete.
#
# The counters are re-emitted one at a time from __counter rather than by
# quoting the matched summary line, which is what this line used to do. Only
# the three loss counters are REQUIRED (checked above); the rest are reported
# when present and simply omitted when they are not, so a future exporter that
# drops or renames an informational counter narrows this line instead of
# turning a clean sweep into an unparseable one.
__report=""
for __name in discovered skipped_unchanged uploaded accepted duplicate \
              rejected skipped_oversize failed; do
    __value="$(__counter "${__name}")"
    [ -n "${__value}" ] || continue
    __report="${__report} ${__name}=${__value}"
done
unset __name __value

echo "[finalize] session-store upload complete (${__report# });" \
     "spool retained at ${__part_dir}" >&2

exit 0
