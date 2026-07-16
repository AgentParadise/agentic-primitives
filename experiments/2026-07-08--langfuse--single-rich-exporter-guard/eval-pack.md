# Eval Pack

This eval pack is frozen after the hypothesis commit.

## Probe A: Baseline Current Behavior

Before implementation, inspect the current CLI exporter construction and record
whether `TRACE_TO_LANGFUSE=true` affects `--observability-langfuse`.

Evidence files:

- `runs/baseline-code-inspection.md`

Pass for the hypothesis requires the baseline to show no existing guard.

## Probe B: Unit Tests

Add or update Rust tests for:

1. `TRACE_TO_LANGFUSE=true` plus `--observability-langfuse` suppresses
   `langfuse_otlp` by default.
2. `--observability-file` is still configured when suppression happens.
3. An explicit override restores `langfuse_otlp`.

Run:

```bash
cargo test cli_exporters -- --nocapture
```

from:

```text
providers/workspaces/interactive-tmux/driver-rs
```

Evidence files:

- `runs/cli-exporters-test.txt`
- `runs/cli-exporters-test-exit.txt`

## Probe C: Hygiene

Run:

```bash
cargo fmt --check
git diff --check
```

Evidence files:

- `runs/fmt-check.txt`
- `runs/fmt-check-exit.txt`
- `runs/diff-check.txt`
- `runs/diff-check-exit.txt`

## Verdict Rules

Use verdict `go` if the guard is implemented, tests prove suppression,
JSONL-preservation, and explicit override, and hygiene passes.

Use verdict `no-go` if the guard cannot be implemented without breaking JSONL
fanout or fallback OTLP.

Use verdict `inconclusive` if the behavior cannot be tested locally.
