# Experiment: Claude Hook Sink Capture

## Question

After adding an explicit `AGENTIC_EVENTS_JSONL` hook sink and driver drain path,
does recipe-driven `itmux run` emit normalized Claude hook events without
polluting stdout with raw hook JSONL?

## Hypothesis

1. The updated `observe.py` still emits to stderr and also appends to the sink
   file when `AGENTIC_EVENTS_JSONL` is set.
2. A derived image containing the updated observability plugin and
   `agentic_events` launches through `itmux run` and completes the prompt.
3. `itmux run` stdout and file exporter contain at least one normalized
   `type = "hook_event"` line, with raw hook JSON nested under `event`.
4. The terminal `session_end` remains the last lifecycle event and raw
   `event_type` hook lines do not appear as standalone stdout records.

## Setup

- Branch: `feat/observability-exporter-primitive`
- Bead: `okrs-51p.6`
- Implementation under test: `feat: collect claude hook events through sink`
- Base image: `agentic-workspace-interactive-tmux:latest`
- Temporary image tag: `itmux-obs-runtime-test:20260707`
- No raw secrets may be stored in evidence.

## Conditions

- Probe A: rebuild the temporary derived image with the updated plugin handler.
- Probe B: direct handler run with `AGENTIC_EVENTS_JSONL` set.
- Probe C: recipe-driven `itmux run` against the derived image with file
  exporter enabled.

## Expected Signals

- `runs/direct-hook-stderr.jsonl`
- `runs/direct-hook-sink.jsonl`
- `runs/stdout.jsonl`
- `runs/events.jsonl`
- `runs/result.json`
- `runs/summary.json`

## Out of Scope

- Permanently changing the provider image.
- LangFuse export.
- Rich semantic mapping from every hook event into domain-specific payloads.
