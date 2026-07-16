# Experiment: Stock Itmux Hook Sink

## Question

After baking the observability runtime into the stock interactive-tmux provider
image, does `itmux run` capture Claude hook events without using a temporary
derived image?

## Hypothesis

1. `agentic-workspace-interactive-tmux:latest` contains
   `/opt/agentic/plugins/observability` and an importable `agentic_events`
   package.
2. A recipe using `skills: [/opt/agentic/plugins/observability]` succeeds
   through `itmux run`.
3. Stdout and file exporter contain at least one normalized `hook_event`, with
   matching total event counts and matching hook-event counts.
4. `session_end` remains the last stdout event and there are no standalone raw
   hook JSONL records.

## Setup

- Branch: `feat/observability-exporter-primitive`
- Bead: `okrs-51p.6`
- Implementation under test: `feat: bake observability runtime into itmux image`
- Image: `agentic-workspace-interactive-tmux:latest`
- No raw secrets may be stored in evidence.

## Conditions

- Probe A: inspect the stock image for plugin/runtime availability.
- Probe B: run recipe-driven `itmux run` against the stock image with file
  exporter enabled.

## Expected Signals

- `runs/image-check.txt`
- `runs/stdout.jsonl`
- `runs/events.jsonl`
- `runs/result.json`
- `runs/summary.json`

## Out of Scope

- LangFuse export.
- Rich semantic remapping of hook events beyond normalized `hook_event`.
