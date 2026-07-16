# Eval Pack

## Probe A: Temporary Image Build

```bash
docker build -t itmux-obs-runtime-test:20260707 -f runs/Dockerfile.obs-runtime .
```

Pass requires exit 0.

## Probe B: Direct Hook Sink

```bash
printf '{"hook_event_name":"SessionStart","session_id":"exp-sink","matcher":"startup","cwd":"/workspace"}' |
docker run --rm -i \
  -e AGENTIC_EVENTS_JSONL=/tmp/agentic-observability/direct-hooks.jsonl \
  itmux-obs-runtime-test:20260707 \
  sh -lc 'python3 /opt/agentic/plugins/observability/hooks/handlers/observe.py 2>/tmp/direct-stderr.jsonl; cat /tmp/direct-stderr.jsonl; echo __SINK__; cat /tmp/agentic-observability/direct-hooks.jsonl'
```

Pass requires:

- handler exits 0
- stderr side contains `event_type`
- sink side contains the same `event_type`

## Probe C: `itmux run` Hook Sink Capture

```bash
providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux run \
  --recipe runs/claude-plugin-recipe \
  --task "Reply exactly: CLAUDE_HOOK_SINK_OK" \
  --image itmux-obs-runtime-test:20260707 \
  --json true \
  --observability-file runs/events.jsonl \
  --result-file runs/result.json
```

Pass requires:

- command exits 0
- result success is true
- session contains `CLAUDE_HOOK_SINK_OK`
- stdout has at least one `type = "hook_event"`
- exporter has the same number of `hook_event` records as stdout
- final stdout event is `session_end`
- no standalone raw hook JSONL line appears in stdout; hook raw JSON is nested
  under the `event` field of `hook_event`.
