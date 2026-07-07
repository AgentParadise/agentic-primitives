# Results

| Probe | Evidence | Result |
|---|---|---|
| Successful Codex exec observer run | `runs/stdout.jsonl`, `runs/events.jsonl`, `runs/result.json`, `runs/summary.json` | Pass: command exited 0, emitted normalized lifecycle and token usage events, file fanout matched stdout, and result exporter report was `ok`. |

## Counts

| Metric | Value |
|---|---:|
| Exit code | 0 |
| Stdout events | 6 |
| Exported events | 6 |
| Exporter report count | 6 |
| Result success | true |

## Event Types

Observed event types:

- `tool_start`
- `tool_end`
- `token_usage`
- `session_end`

Sequence numbers were contiguous from 0 through 5.

## Token Usage

`runs/summary.json` captured:

- `input_tokens=15919`
- `cached_input_tokens=9600`
- `output_tokens=11`
- `reasoning_output_tokens=0`

## Notes

Codex still printed `Reading additional input from stdin...` on stderr even
though the wrapper sets stdin to null. It did not affect normalized stdout,
exporter fanout, or result success.
