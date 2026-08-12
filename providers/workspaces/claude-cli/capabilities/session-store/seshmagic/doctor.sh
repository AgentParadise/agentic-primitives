#!/usr/bin/env bash
# SeshMagic provider-specific health check (ADR-038).
#
# NOT wired into the automatic preflight. Unlike the memory capability's
# ProviderSpecificCheck, agentic_session_store.doctor's check list (Task 3)
# has no provider-specific hook, and this script is not invoked by
# /opt/agentic/capabilities/session-store/doctor. It is a manual diagnostic
# only — run it by hand (see the capability README's "Running the doctor
# by hand" section) after sourcing the adapter's exported env. Reports
# JSON to stdout; exit 0 = pass, exit 1 = fail.

set -e

STATE_FILE="${EXPORTER_STATE_FILE:-}"
if [ -z "${STATE_FILE}" ]; then
    printf '{"seshmagic_provider_check":"fail","details":{"error":"EXPORTER_STATE_FILE unset"}}\n'
    exit 1
fi

STATE_DIR="$(dirname "${STATE_FILE}")"
if [ ! -w "${STATE_DIR}" ]; then
    printf '{"seshmagic_provider_check":"fail","details":{"error":"state dir not writable","dir":"%s"}}\n' "${STATE_DIR}"
    exit 1
fi

if [ -f "${STATE_FILE}" ] && ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "${STATE_FILE}" 2>/dev/null; then
    printf '{"seshmagic_provider_check":"fail","details":{"error":"state file is not valid JSON","path":"%s"}}\n' "${STATE_FILE}"
    exit 1
fi

state_status="fresh"
[ -f "${STATE_FILE}" ] && state_status="resuming"
printf '{"seshmagic_provider_check":"ok","details":{"state":"%s","path":"%s"}}\n' "${state_status}" "${STATE_FILE}"
exit 0
