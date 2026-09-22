#!/usr/bin/env bash
# Best-effort final sweep. Persistent native roots remain recoverable on failure.
set -u
if [ -z "${EXPORTER_SPOOL_DIR:-}" ]; then
    echo "[local-capture] envelope directory unset; capture requires recovery" >&2
    exit 0
fi
exporter="${AGENTIC_SESSION_STORE_EXPORTER_BIN:-apss-session-exporter}"
budget="${AGENTIC_FINALIZE_BUDGET_S:-30}"
if timeout --signal=TERM --kill-after=1 "${budget}" "${exporter}" --spool-only; then
    echo "[local-capture] sweep persisted; workflow coverage remains independently determined" >&2
else
    rc=$?
    echo "[local-capture] sweep failed (exit ${rc}); retained native transcripts require recovery" >&2
fi
exit 0
