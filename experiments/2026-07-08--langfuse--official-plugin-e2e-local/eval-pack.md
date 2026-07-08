# Eval Pack

## Probe A: Local LangFuse Readiness

Verify local LangFuse web is reachable and local ignored env contains project
keys without printing secret values.

Capture:

- `runs/readiness.txt`

## Probe B: Official Claude Hook Fixture Export

Run the official Claude hook against:

```text
/tmp/langfuse-claude-plugin/tests/fixtures/transcripts/tool_turn/transcript.jsonl
```

Use isolated state:

```text
runs/claude-home/
```

Capture:

- `runs/claude-hook-stdout.txt`
- `runs/claude-hook-stderr.txt`
- `runs/claude-hook-exit.txt`
- `runs/claude-query.json`
- `runs/claude-summary.md`

Pass criteria:

- hook exits 0
- LangFuse contains a recent Claude plugin trace or observation
- root input/output is present
- at least one generation observation exists
- at least one tool observation exists with a semantic tool name

## Probe C: Official Codex Hook Fixture Export

Run the official Codex hook against:

```text
/tmp/langfuse-codex-plugin/plugins/tracing/test/fixtures/sessions/2026/06/03/rollout-basic-main.jsonl
```

Use explicit Node 22 and isolated config/state as needed.

Capture:

- `runs/codex-hook-stdout.txt`
- `runs/codex-hook-stderr.txt`
- `runs/codex-hook-exit.txt`
- `runs/codex-query.json`
- `runs/codex-summary.md`
- `runs/codex-sidecar.txt`

Pass criteria:

- hook exits 0
- sidecar file exists for completed turn deduplication, or the hook explains
  why the fixture is not marked complete
- LangFuse contains a recent `Codex Turn`
- root input/output is present
- at least one generation observation exists
- at least one tool observation exists with a semantic tool name
- usage details are present when fixture usage exists

## Probe D: Noise-Control Check

Inspect command logs and summaries to confirm no agentic-primitives Rust OTLP
exporter path ran.

Capture:

- `runs/noise-control.md`

Pass criteria:

- no `itmux run --observability-langfuse`
- no `itmux codex-exec --observability-langfuse`
- no direct Rust OTLP exporter invocation

## Scoring

Use verdict `go` if both official plugins export rich traces into local
LangFuse and no Rust OTLP duplicate path runs.

Use verdict `inconclusive` if local fixture export works for one plugin but
the other is blocked by environment/tooling.

Use verdict `no-go` if official plugins cannot export rich traces or require
the Rust OTLP exporter to be useful.
