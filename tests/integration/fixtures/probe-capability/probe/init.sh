#!/usr/bin/env bash
# Adapter for the probe test capability, SOURCED by entrypoint.sh 5.6.
#
# Declares one secret of its own and withholds it, exactly as a real adapter
# does. Its finalize.sh then reports what it can see, which is how the
# per-capability scoping of AGENTIC_CAPABILITY_WITHHOLD is observed from
# outside the entrypoint.
export PROBE_SECRET="probe-owns-this"
AGENTIC_CAPABILITY_WITHHOLD="${AGENTIC_CAPABILITY_WITHHOLD:-} PROBE_SECRET"
export AGENTIC_CAPABILITY_WITHHOLD
return 0
