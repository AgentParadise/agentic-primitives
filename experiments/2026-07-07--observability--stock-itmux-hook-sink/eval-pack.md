# Eval Pack

## Probe A: Stock Image Runtime Check

```bash
docker run --rm agentic-workspace-interactive-tmux:latest \
  sh -lc 'test -x /opt/agentic/plugins/observability/hooks/handlers/observe.py && python3 -c "import agentic_events; print(agentic_events.__version__)"'
```

Pass requires exit 0 and an `agentic_events` version on stdout.

## Probe B: Stock Image Hook Capture

```bash
providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux run \
  --recipe runs/claude-plugin-recipe \
  --task "Reply exactly: STOCK_HOOK_SINK_OK" \
  --image agentic-workspace-interactive-tmux:latest \
  --json true \
  --observability-file runs/events.jsonl \
  --result-file runs/result.json
```

Pass requires:

- command exits 0
- result success is true
- session contains `STOCK_HOOK_SINK_OK`
- stdout has at least one `type = "hook_event"`
- exporter has the same total line count as stdout
- exporter has the same hook-event count as stdout
- final stdout event is `session_end`
- no standalone raw hook JSONL line appears in stdout
