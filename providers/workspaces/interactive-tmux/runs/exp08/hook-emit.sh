#!/usr/bin/env bash
# EXP-08 hook prototype: read Claude Code hook JSON on stdin and append it as
# a single JSONL line to /host-events/claude.jsonl. Wraps the event in a
# minimal Lane-2 envelope (hook_event_name, ts_ms, container, payload).
TS_MS=$(( $(date +%s%N) / 1000000 ))
PAYLOAD=$(cat)
HOST=$(hostname)
ENV_NAME=${1:-unknown_event}
EVENT="{\"ts_ms\":$TS_MS,\"container\":\"$HOST\",\"event\":\"$ENV_NAME\",\"payload\":$PAYLOAD}"
echo "$EVENT" >> /host-events/claude.jsonl
