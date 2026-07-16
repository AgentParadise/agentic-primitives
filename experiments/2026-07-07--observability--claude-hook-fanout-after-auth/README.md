# Experiment: Claude Hook Fanout After Auth

## Question

Now that Docker Claude auth works via `CLAUDE_CODE_OAUTH_TOKEN` passthrough, do
Claude observability plugin hook events appear in `itmux run` evidence and file
fanout?

## Hypothesis

1. The recipe launches Claude with `--plugin-dir /workspace/plugins/observability`
   and the prompt succeeds, proving auth is no longer the blocker.
2. `itmux run` stdout and file exporter remain valid normalized driver event
   JSONL with matching counts.
3. Current code still does not expose Claude hook JSONL as normalized
   `AgentRunEvent`s; if raw hook JSONL appears anywhere, it will be in captured
   session/stderr evidence rather than the file exporter.

## Setup

- Branch: `feat/observability-exporter-primitive`
- Bead: `okrs-51p.6`
- Credential precondition:
  `experiments/2026-07-07--observability--claude-env-token-passthrough` passed.
- Plugin path under test: `/workspace/plugins/observability`
- No raw secrets may be stored in evidence.

## Conditions

- Run one minimal Claude recipe with `skills: [/workspace/plugins/observability]`.
- Capture normalized stdout JSONL, file exporter JSONL, result JSON, stderr, and
  a summary.
- Score whether `event_type` hook JSONL appears in stdout/exporter/session/stderr.

## Expected Signals

- `runs/stdout.jsonl`
- `runs/events.jsonl`
- `runs/result.json`
- `runs/stderr.txt`
- `runs/summary.json`

## Out of Scope

- Implementing the `claude_hooks` observer.
- LangFuse export.
- Storing token values.
