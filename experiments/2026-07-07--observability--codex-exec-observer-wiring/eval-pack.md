# Eval Pack

## Probe A: Successful Codex Exec Observer Run

Run:

```bash
itmux codex-exec \
  --prompt "Reply exactly: CODEX_EXEC_WIRING_OK" \
  --observability-file runs/events.jsonl \
  --result-file runs/result.json
```

Capture:

- `runs/stdout.jsonl`
- `runs/events.jsonl`
- `runs/result.json`
- `runs/exit.txt`
- `runs/summary.json`

## Scoring

Pass requires:

- command exits 0
- result success is true
- stdout contains `tool_start`, `tool_end`, `token_usage`, and `session_end`
- exporter file line count equals stdout event line count
- result exporter report status is `ok`
- result exporter event count equals exporter file line count
- token usage has nonzero `input_tokens` and `output_tokens`

Failure modes to classify:

- Codex auth/model failure
- observer parse failure
- fanout count mismatch
- missing token usage
