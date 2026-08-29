#!/usr/bin/env bash
# Finalize hook for the probe test capability. Reports which withheld values
# reached it, by name, and exits 0 like every finalize hook must.
set -u
echo "PROBE_FINALIZE PROBE_SECRET=${PROBE_SECRET:-<unset>}" >&2
echo "PROBE_FINALIZE SESSIONS_WRITE_TOKEN=${SESSIONS_WRITE_TOKEN:-<unset>}" >&2
echo "PROBE_FINALIZE AGENTIC_SESSION_STORE_AUTH=${AGENTIC_SESSION_STORE_AUTH:-<unset>}" >&2
exit 0
