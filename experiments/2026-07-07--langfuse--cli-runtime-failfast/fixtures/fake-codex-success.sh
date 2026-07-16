#!/bin/sh
set -eu

if [ "${1:-}" != "exec" ] || [ "${2:-}" != "--json" ]; then
  echo "unexpected fake codex argv: $*" >&2
  exit 2
fi

printf '%s\n' '{"type":"thread.started","thread_id":"synthetic-thread"}'
printf '%s\n' '{"type":"turn.started"}'
printf '%s\n' '{"type":"item.completed","item":{"type":"agent_message","text":"SYNTHETIC_CODEX_OK"}}'
printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":0,"output_tokens":3,"reasoning_output_tokens":0}}'
