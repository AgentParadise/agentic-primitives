# Eval Pack

## Probe A: Claude Plugin Recipe Run

Run:

```bash
providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux run \
  --recipe runs/claude-plugin-recipe \
  --task "Reply exactly: CLAUDE_HOOK_AUTH_OK" \
  --json true \
  --observability-file runs/events.jsonl \
  --result-file runs/result.json
```

Capture:

- `runs/stdout.jsonl`
- `runs/stderr.txt`
- `runs/exit.txt`
- `runs/events.jsonl`
- `runs/result.json`
- `runs/summary.json`

## Scoring

Pass for auth/file fanout requires:

- command exits 0
- result success is true
- session contains `CLAUDE_HOOK_AUTH_OK`
- session launch contains `claude --plugin-dir /workspace/plugins/observability`
- stdout event count equals exporter event count
- exporter status is `ok`

Hook visibility classification:

- `event_type` appears in stdout/exporter: current fanout is contaminated or
  already captures raw hook JSONL.
- `event_type` appears only in session/stderr: hook stream is visible but not
  normalized.
- no `event_type` appears: plugin may not emit, handler dependency may be
  missing, or Claude does not surface hook stderr in the interactive transcript.
