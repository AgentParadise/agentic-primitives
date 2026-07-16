# Verdict

**Go for explicit Claude hook sink capture.**

The implementation converted the previous no-go into a pass: Claude hook JSONL
is captured from an explicit in-container sink, normalized as `hook_event`, and
sent through the same stdout/file exporter path as driver events. Stdout remains
pure `AgentRunEvent` JSONL; raw hook JSON is nested under the `event` field.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Direct handler writes both stderr and sink file | Both contained `session_started`; handler stdout was empty | correct | `runs/direct-hook-stderr.jsonl`, `runs/direct-hook-sink.jsonl` |
| `itmux run` launches and succeeds | Exit 0, result success true, session contained `CLAUDE_HOOK_SINK_OK` | correct | `runs/result.json` |
| `itmux run` emits normalized `hook_event` records | 3 hook events in stdout and 3 in exporter | correct | `runs/summary.json` |
| `session_end` remains last and stdout is not raw hook JSONL | Last type was `session_end`; 0 standalone raw hook lines | correct | `runs/stdout.jsonl` |

## Design Impact

- `.6` now has a proven Claude hook capture mechanism.
- The final `.6` packaging task is provider integration: bake or stage
  `plugins/observability` and `agentic_events` into interactive-tmux.
- `.9` can depend on the normalized event fanout, but should still wait until
  the packaging path is committed and validated in the stock provider image.
