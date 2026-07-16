# Eval Pack

## Probe A: Temporary Image Build

Build:

```bash
docker build -t itmux-obs-runtime-test:20260707 -f runs/Dockerfile.obs-runtime .
```

Pass requires:

- build exits 0
- no secret material is copied

## Probe B: Direct Hook Handler Runtime

Run:

```bash
printf '{"hook_event_name":"SessionStart","session_id":"exp-manual","matcher":"startup","cwd":"/workspace"}' |
docker run --rm -i itmux-obs-runtime-test:20260707 \
  python3 /opt/agentic/plugins/observability/hooks/handlers/observe.py \
  > runs/manual-hook-stdout.txt \
  2> runs/manual-hook-stderr.jsonl
```

Pass requires:

- command exits 0
- stderr has at least one valid JSONL line with `event_type`
- stdout is empty

## Probe C: Claude Plugin Runtime Through `itmux run`

Run:

```bash
providers/workspaces/interactive-tmux/driver-rs/target/debug/itmux run \
  --recipe runs/claude-plugin-recipe \
  --task "Reply exactly: BAKED_HOOK_RUNTIME_OK" \
  --image itmux-obs-runtime-test:20260707 \
  --json true \
  --observability-file runs/events.jsonl \
  --result-file runs/result.json
```

Pass for auth/driver fanout requires:

- command exits 0
- result success is true
- session contains `BAKED_HOOK_RUNTIME_OK`
- session launch contains `claude --plugin-dir /opt/agentic/plugins/observability`
- stdout event count equals exporter event count
- exporter status is `ok`

Hook capture classification:

- If `event_type` appears in stdout/exporter, the current contract is polluted
  or already receiving raw hook JSONL.
- If `event_type` appears only in session/stderr, hook output is visible but
  not normalized.
- If `event_type` appears nowhere, the driver still needs a dedicated hook
  capture path even after the plugin runtime is present.
