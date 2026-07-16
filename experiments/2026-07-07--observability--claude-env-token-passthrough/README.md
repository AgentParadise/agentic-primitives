# Experiment: Claude Env Token Passthrough

## Question

Does passing `CLAUDE_CODE_OAUTH_TOKEN` into the Docker workspace by environment
variable name fix the recipe-driven Claude 401 while preserving file exporter
behavior?

## Hypothesis

1. When the host has `CLAUDE_CODE_OAUTH_TOKEN`, `itmux run` starts a Claude
   Docker workspace with `-e CLAUDE_CODE_OAUTH_TOKEN`, not `NAME=value`.
2. The same minimal Claude recipe that failed with `API Error: 401` now
   succeeds and returns the requested exact text.
3. The file exporter writes the same number of events as stdout, and the result
   reports exporter status `ok`.

## Setup

- Branch: `feat/observability-exporter-primitive`
- Bead: `okrs-51p.6`
- Fix under test: `fix: pass claude oauth token into docker workspace`
- No raw secrets may be stored in evidence.

## Conditions

- Probe A: pure/unit validation that Docker argv carries env names only.
- Probe B: live recipe-driven `itmux run` Claude minimal prompt with file
  exporter.
- Probe C: redacted container/env evidence if a workspace is available long
  enough to inspect without storing secret values.

## Expected Signals

- `runs/itmux-run-stdout.jsonl`
- `runs/itmux-run-events.jsonl`
- `runs/itmux-run-result.json`
- `runs/itmux-run-exit.txt`
- `runs/summary.json`

## Out of Scope

- Claude observability hook parsing.
- LangFuse OTLP export.
- Storing token values or full credential JSON.
