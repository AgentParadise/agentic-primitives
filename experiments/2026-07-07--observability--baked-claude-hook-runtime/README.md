# Experiment: Baked Claude Hook Runtime

## Question

If the interactive-tmux image actually contains `plugins/observability` and
`agentic_events`, do Claude hook events become observable through `itmux run`,
or is a separate hook capture mechanism still required?

## Hypothesis

1. A temporary derived image that copies `plugins/observability` and
   `lib/python/agentic_events` can run `observe.py` directly and emit at least
   one `event_type` JSONL line. This proves the plugin dependency/runtime
   packaging is viable.
2. A recipe using `skills: [/opt/agentic/plugins/observability]` launches
   Claude with that plugin path and completes a prompt successfully.
3. Even with the plugin and dependency present, `itmux run` will still export
   only normalized driver events. No raw hook `event_type` JSONL will appear in
   stdout or the file exporter, because the current driver has no Claude hook
   observer/capture path.

## Setup

- Branch: `feat/observability-exporter-primitive`
- Bead: `okrs-51p.6`
- Base image: `agentic-workspace-interactive-tmux:latest`
- Temporary image tag: `itmux-obs-runtime-test:20260707`
- No raw secrets may be stored in evidence.

## Conditions

- Probe A: build a temporary derived image with the observability plugin and
  local `agentic_events` package.
- Probe B: run `observe.py` directly inside the image with a synthetic
  `SessionStart` payload and capture stderr/stdout.
- Probe C: run recipe-driven `itmux run` against the derived image with the
  plugin path and file exporter enabled.

## Expected Signals

- `runs/docker-build-exit.txt`
- `runs/manual-hook-stdout.txt`
- `runs/manual-hook-stderr.jsonl`
- `runs/stdout.jsonl`
- `runs/events.jsonl`
- `runs/result.json`
- `runs/summary.json`

## Out of Scope

- Permanently changing the provider image.
- Implementing the `claude_hooks` observer.
- LangFuse export.
