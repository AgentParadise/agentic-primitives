#!/usr/bin/env bash
# Adapter for the nofinalize test capability, SOURCED by entrypoint.sh 5.6.
#
# Deliberately ships NO finalize.sh alongside this file. That is the whole
# fixture: a capability that is genuinely active (registered, provider set,
# doctor passing, adapter sourced) and still has no post-agent work, so it
# must not cost the consumer the exec path. memory/hindsight is the real
# instance of this shape, but exercising it needs a live hindsight backend.
export AGENTIC_NOFINALIZE_MARKER=nofinalize-adapter-ran
return 0
