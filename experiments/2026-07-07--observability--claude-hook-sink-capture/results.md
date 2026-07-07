# Results

| Probe | Evidence | Result |
|---|---|---|
| Temporary image build | `runs/docker-build-exit.txt`, `runs/docker-build-stderr.txt` | Passed: build exited 0 and produced the updated `itmux-obs-runtime-test:20260707` image. |
| Direct hook sink | `runs/direct-hook-stdout.txt`, `runs/direct-hook-stderr.jsonl`, `runs/direct-hook-sink.jsonl` | Passed: handler stdout was empty, stderr contained `session_started`, and the sink file contained the same `session_started` event. |
| `itmux run` hook sink capture | `runs/stdout.jsonl`, `runs/events.jsonl`, `runs/result.json`, `runs/summary.json` | Passed: exit 0, result success true, session contained `CLAUDE_HOOK_SINK_OK`, stdout/exporter had 14 events each, and both contained 3 `hook_event` records. |

## Key Data

| Field | Value |
|---|---|
| Direct stderr event type | `session_started` |
| Direct sink event type | `session_started` |
| `itmux run` exit | 0 |
| Result success | true |
| Stdout event lines | 14 |
| Exporter event lines | 14 |
| Stdout hook events | 3 |
| Exporter hook events | 3 |
| Hook event types | `session_started`, `user_prompt_submitted`, `agent_stopped` |
| Last stdout event type | `session_end` |
| Standalone raw hook JSONL lines on stdout | 0 |

## Classification

The explicit hook sink design works. `observe.py` can tee hook JSONL into
`AGENTIC_EVENTS_JSONL`, and the Rust driver drains that file before teardown and
emits normalized `type = "hook_event"` records through the existing stdout and
file exporter fanout.

This proves the reusable `.6` architecture for Claude hook capture. Remaining
packaging work is to make the observability plugin and `agentic_events`
available in the stock interactive-tmux provider image instead of relying on a
temporary derived image.
