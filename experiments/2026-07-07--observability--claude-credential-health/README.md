# Experiment: Claude Credential Health

## Question

Is the Claude 401 seen in the observability hook/file-fanout probes caused by
bad host credentials, broken credential staging, or a recipe-driven `itmux run`
path issue?

## Hypothesis

1. Host `claude -p` succeeds with the same account, proving the host credential
   material is currently valid.
2. `itmux start --agents claude` stages both `.credentials.json` and
   `.claude.json` into the container with the expected redacted key shape.
3. Recipe-driven `itmux run` still fails with Claude `API Error: 401`, which
   would point to a run-path credential/launch difference rather than invalid
   host credentials.

## Setup

- Branch: `feat/observability-exporter-primitive`
- Bead: `okrs-51p.6`
- Host credential paths: `$HOME/.claude/.credentials.json` and
  `$HOME/.claude.json`
- No raw secrets may be stored in evidence.

## Conditions

- Probe A: host `claude -p` minimal prompt.
- Probe B: `itmux start` Claude-only workspace, then inspect only redacted
  credential key shapes inside the container.
- Probe C: recipe-driven `itmux run` Claude minimal prompt with file exporter.

## Expected Signals

- `runs/host-claude-stdout.txt`
- `runs/host-claude-stderr.txt`
- `runs/start-report.json`
- `runs/container-credential-shape.json`
- `runs/itmux-run-stdout.jsonl`
- `runs/itmux-run-events.jsonl`
- `runs/itmux-run-result.json`
- `runs/summary.json`

## Out of Scope

- Storing tokens or full credential JSON.
- Fixing Claude auth before evidence is captured.
- Claude hook event ingestion.
