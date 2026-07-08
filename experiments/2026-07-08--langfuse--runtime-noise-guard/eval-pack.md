# Eval Pack

This eval pack is frozen after the hypothesis commit.

## Probe A: Runtime Suppression

Run `itmux claude-transcript` against a local HTTP receiver with:

- `TRACE_TO_LANGFUSE=true`
- `--observability-langfuse`
- `--observability-file runs/suppressed/events.jsonl`
- `--observability-syntropic-file runs/suppressed/syntropic-events.jsonl`
- no `--observability-langfuse-force`

Evidence:

- `runs/suppressed/stdout.jsonl`
- `runs/suppressed/stderr.txt`
- `runs/suppressed/result.json`
- `runs/suppressed/events.jsonl`
- `runs/suppressed/syntropic-events.jsonl`
- `runs/suppressed/receiver.json`

## Probe B: Explicit Force

Run the same command with `--observability-langfuse-force`.

Evidence:

- `runs/forced/stdout.jsonl`
- `runs/forced/stderr.txt`
- `runs/forced/result.json`
- `runs/forced/events.jsonl`
- `runs/forced/syntropic-events.jsonl`
- `runs/forced/receiver.json`

## Probe C: Focused Tests

Run:

```bash
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml cli_exporters -- --nocapture
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml run::observability::tests::syntropic_jsonl_exporter_writes_hook_style_events -- --nocapture
```

Evidence:

- `runs/test-cli-exporters.txt`
- `runs/test-cli-exporters-exit.txt`
- `runs/test-syntropic-exporter.txt`
- `runs/test-syntropic-exporter-exit.txt`

## Probe D: Hygiene

Run:

```bash
git diff --check
rg -P "(sk-lf|pk-lf)-(?!REDACTED)[A-Za-z0-9_-]+" experiments/2026-07-08--langfuse--runtime-noise-guard
```

Evidence:

- `runs/diff-check.txt`
- `runs/diff-check-exit.txt`
- `runs/secret-scan.txt`
- `runs/secret-scan-exit.txt`

## Verdict Rules

Use verdict `go` if the suppressed run sends zero receiver requests, the forced
run sends one receiver request, JSONL fanout works in both conditions, focused
tests pass, and no unredacted key values are present.

Use verdict `no-go` if suppression disables local JSONL or force cannot restore
the fallback OTLP path.

Use verdict `inconclusive` if the command or local receiver cannot be executed
on this machine.
