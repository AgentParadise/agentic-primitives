# Verdict

**Go for stock interactive-tmux Claude hook observability.**

The stock provider image now satisfies the packaging requirement and the live
run preserved the stdout/exporter contract while emitting normalized hook
events.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Stock image contains plugin/runtime | Image check exited 0 and imported `agentic_events` 0.1.0 | correct | `runs/image-check.txt` |
| `itmux run` succeeds with stock image | Exit 0, result success true, expected text present | correct | `runs/result.json` |
| Stock image run emits normalized hook events | 3 hook events in stdout and exporter | correct | `runs/summary.json` |
| `session_end` remains last and stdout is pure contract JSONL | Last type was `session_end`; 0 standalone raw hook lines | correct | `runs/stdout.jsonl` |

## Design Impact

- `.6` now has a stock-provider Claude hook implementation, not just a derived
  image prototype.
- LangFuse `.9` can build on the normalized event fanout; remaining `.9`
  blocker is backend/exporter configuration, not basic hook capture.
