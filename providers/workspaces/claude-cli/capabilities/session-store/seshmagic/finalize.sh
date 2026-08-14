#!/usr/bin/env bash
# SeshMagic session-store finalize hook (ADR-040).
#
# Sweeps the partition and uploads to the remote store. ALWAYS exits 0:
# a failed upload after an hour of successful agent work must never make
# the phase report as failed. On failure the spool is left intact so a
# later recovery sweep can retry; the store dedups on content_hash, so
# re-sweeping is a no-op rather than a corruption risk. The partition is
# pruned only after a CLEAN sweep, which is a stronger condition than a clean
# exit code (see the summary-line gate below).

set -u

if [ -z "${SESSION_STORE_URL:-}" ]; then
    exit 0
fi

# Partition directory, computed once up front and reused everywhere below
# via this one :-guarded variable. EXPORTER_STATE_FILE is normally exported
# by init.sh, but this hook is also meant to run standalone -- a recovery
# sweep of a partition left behind by a SIGKILLed container (see below) --
# where it is unset. A bare `${EXPORTER_STATE_FILE%/*}` in that case trips
# `set -u` and aborts the script, breaking the "always exit 0" contract on
# exactly the failure path this recovery mechanism exists to handle.
if [ -n "${EXPORTER_STATE_FILE:-}" ]; then
    __part_dir="${EXPORTER_STATE_FILE%/*}"
else
    __part_dir="<unset>"
fi

# Recovery path (EXP-08 arm A5): when invoked without the adapter's env - a
# sweep of a partition left behind by a SIGKILLed container - recover the tags
# the partition was created with. Without this the session uploads untagged
# and is unattributable.
if [ -z "${SESSION_STORE_TAGS:-}" ] && [ -n "${EXPORTER_STATE_FILE:-}" ]; then
    __capture_env="${__part_dir}/.capture-env"
    if [ -r "${__capture_env}" ]; then
        # PARSE, never source. Tags are opaque orchestrator input; sourcing
        # them is arbitrary code execution at sweep time, with the store
        # write token in scope. Verified during Tasks 5+6 review: a tag of
        # `workflow:$(touch /tmp/PWNED)` executed on source, and any tag
        # containing a space silently truncated the value to empty --
        # destroying the very attribution this file exists to preserve.
        SESSION_STORE_TAGS="$(sed -n 's/^SESSION_STORE_TAGS=//p' "${__capture_env}" | head -1)"
        export SESSION_STORE_TAGS
        echo "[finalize] recovered tags from ${__capture_env}" >&2
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
# The arithmetic. Two constants bound the window:
#   * entrypoint.sh's __TERM_GRACE_TICKS   -- 15 x 0.1s = 1.5s before the
#     wrapper escalates a stubborn agent to SIGKILL.
#   * docker.py's `docker stop -t`         -- 5s
#     (lib/python/agentic_isolation/agentic_isolation/providers/docker.py).
# Measured through the real entrypoint on 2026-08-14: escalation completes at
# ~1.66s for a stubborn agent (`trap "" TERM`), leaving ~3.3s of the 5s before
# docker's own SIGKILL. 2s finishes at ~3.66s, a 1.3s margin. 3s would finish
# at ~4.66s, a 0.34s margin, which is too thin to be reliable.
#
# A timeout is an upload FAILURE: keep the spool, never prune, exit 0.
readonly __UPLOAD_TIMEOUT_S=2

# Both the exporter's stdout and stderr go to OUR stderr, never our stdout.
# Under the old `exec "$@"`, container stdout was exclusively the agent's;
# now that finalize runs after the agent exits, letting exporter chatter
# reach stdout would corrupt anything parsing it (e.g. an agent CMD invoked
# with a structured --output-format). We capture both streams into a variable
# (`2>&1` inside the command substitution) and replay them to fd2, which keeps
# that stdout-cleanliness property while making the exporter's machine-readable
# summary line available to the prune gate below.
__exporter_out="$(timeout "${__UPLOAD_TIMEOUT_S}" SeshMagicSessionExporter 2>&1)"
__exporter_rc=$?
if [ -n "${__exporter_out}" ]; then
    printf '%s\n' "${__exporter_out}" >&2
fi

if [ "${__exporter_rc}" -ne 0 ]; then
    if [ "${__exporter_rc}" -eq 124 ]; then
        echo "[finalize] session-store upload TIMED OUT after ${__UPLOAD_TIMEOUT_S}s;" \
             "spool retained at ${__part_dir}" >&2
    else
        echo "[finalize] session-store upload FAILED (rc=${__exporter_rc});" \
             "spool retained at ${__part_dir}" >&2
    fi
    exit 0
fi

# A CLEAN EXIT IS NOT A CLEAN SWEEP. The exporter says so in its own source
# (crates/seshmagic-session-store-exporter/src/bin/exporter.rs):
#
#   // A completed sweep exits 0 even with per-item skips/failures; only a
#   // hard RunError (store unreachable, source scan failure) is non-zero.
#
# So rc=0 is consistent with `failed=3 skipped_oversize=2`, i.e. five
# transcripts that never reached the store. Pruning on rc=0 alone deletes them.
#
# That is the defect, and it does not depend on anything about persisted homes:
# these are sessions the agent wrote DURING THIS RUN, which existed, never
# reached the store, and get deleted anyway on the strength of an exit code
# that is 0 even when failed=3. The spool is their only remaining copy.
#
# The adapter also migrates a pre-existing ~/.claude/projects into the
# partition rather than deleting it, so the partition can hold more than the
# current run's output. That widens the blast radius but is not what makes this
# a data-loss path; the run's own transcripts already do.
#
# The gate is the summary line the exporter already prints:
#
#   run: discovered=N skipped_unchanged=N uploaded=N accepted=N duplicate=N \
#        rejected=N skipped_oversize=N failed=N
#
# Prune only on failed=0 AND skipped_oversize=0 AND rejected=0. Those three are
# the counters that mean "this transcript is not in the store".
#
# duplicate and skipped_unchanged are NOT failures and must never block the
# prune: duplicate means the store already holds that content (it dedups on
# content_hash) and skipped_unchanged means a prior sweep already uploaded the
# file. Both are confirmations, not losses.
#
# No parseable summary means no evidence of success, so it is treated as
# not-clean. That is also what covers the timeout path above reaching this far
# by any future edit: a killed exporter prints no summary.
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

__blocked=""
[ "${__failed}" -ne 0 ] && __blocked="${__blocked} failed=${__failed}"
[ "${__oversize}" -ne 0 ] && __blocked="${__blocked} skipped_oversize=${__oversize}"
[ "${__rejected}" -ne 0 ] && __blocked="${__blocked} rejected=${__rejected}"

if [ -n "${__blocked}" ]; then
    echo "[finalize] session-store sweep INCOMPLETE (${__blocked# }): at least one transcript" \
         "did not reach the store; spool retained at ${__part_dir}" >&2
    exit 0
fi

echo "[finalize] session-store upload complete (${__summary#run: })" >&2

# Prune the partition on success only. The spool volume outlives any single
# container (that persistence is exactly what makes the .capture-env
# recovery path above meaningful for a SIGKILLed run) and would otherwise
# accumulate one partition directory per container run forever. Never prune
# on a failed sweep -- that spool is the only remaining copy of a session
# that has not been confirmed uploaded.
#
# CONTAINMENT. Remove only a directory this capability created, evidenced by
# the .agentic-partition marker init.sh writes at creation time.
#
# The previous guard tested path SHAPE (`case "${__part_dir}" in /*/*`) and
# claimed to prevent `rm -rf /` and `rm -rf /spool`. It did prevent those two,
# and nothing else: shape says nothing about ownership. With SPOOL=/workspace
# and PARTITION=repos the state file is /workspace/repos/state.json, whose
# dirname matches /*/*, and a successful sweep ran `rm -rf /workspace/repos`
# on an operator's bind mount. Reproduced during review, with data lost.
#
# What the marker proves, exactly: at init time no directory existed at this
# path, so this capability created it and everything inside it arrived through
# this capability. init.sh deliberately does NOT write the marker over a
# pre-existing directory, which is what makes the /workspace/repos case
# refuse. Also note the marker is not a claim about uploads - the clean
# summary line above is that claim, and both must hold to reach this line.
#
# The marker cannot be produced by a misconfigured path: /, /spool, and any
# unrelated mount all lack it, so the old shape guard's two cases stay covered
# without a separate check.
if [ -n "${EXPORTER_STATE_FILE:-}" ]; then
    if [ -f "${__part_dir}/.agentic-partition" ]; then
        rm -rf "${__part_dir}"
        echo "[finalize] pruned partition ${__part_dir}" >&2
    else
        echo "[finalize] WARNING: refusing to prune '${__part_dir}': no .agentic-partition marker," \
             "so this capability did not create it; leaving it untouched" >&2
    fi
fi

exit 0
