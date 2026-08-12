#!/usr/bin/env bash
# SeshMagic session-store finalize hook (ADR-038).
#
# Sweeps the partition and uploads to the remote store. ALWAYS exits 0:
# a failed upload after an hour of successful agent work must never make
# the phase report as failed. On failure the spool is left intact so a
# later recovery sweep can retry; the store dedups on content_hash, so
# re-sweeping is a no-op rather than a corruption risk. On success the
# partition is pruned (see the block below for why).

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

# Both the exporter's stdout and stderr go to OUR stderr, never our stdout.
# Under the old `exec "$@"`, container stdout was exclusively the agent's;
# now that finalize runs after the agent exits, letting exporter chatter
# reach stdout would corrupt anything parsing it (e.g. an agent CMD invoked
# with a structured --output-format). `>&2 2>&1` (in that order) sends both
# streams to whatever fd2 already points at, not the other way around.
if ! SeshMagicSessionExporter >&2 2>&1; then
    echo "[finalize] session-store upload FAILED; spool retained at ${__part_dir}" >&2
    exit 0
fi

echo "[finalize] session-store upload complete" >&2

# Prune the partition on success only. The spool volume outlives any single
# container (that persistence is exactly what makes the .capture-env
# recovery path above meaningful for a SIGKILLed run) and would otherwise
# accumulate one partition directory per container run forever. Never prune
# on a failed sweep -- that spool is the only remaining copy of a session
# that has not been confirmed uploaded.
#
# Guard requires at least two path segments under root (e.g. /spool/<part>)
# so a misconfigured EXPORTER_STATE_FILE (e.g. "/state.json", dirname "/")
# can't turn this into `rm -rf /` or `rm -rf /spool`.
if [ -n "${EXPORTER_STATE_FILE:-}" ]; then
    case "${__part_dir}" in
        /*/*)
            rm -rf "${__part_dir}"
            echo "[finalize] pruned partition ${__part_dir}" >&2
            ;;
        *)
            echo "[finalize] WARNING: refusing to prune suspicious partition path '${__part_dir}'" >&2
            ;;
    esac
fi

exit 0
