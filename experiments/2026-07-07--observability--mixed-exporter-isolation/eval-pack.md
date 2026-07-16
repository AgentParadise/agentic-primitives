# Eval Pack

## Probe A: Mixed Exporter Runtime

Run:

```bash
cargo run --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml -- \
  codex-exec \
  --codex-bin experiments/2026-07-07--langfuse--cli-runtime-failfast/fixtures/fake-codex-success.sh \
  --prompt "synthetic mixed exporter isolation" \
  --observability-file experiments/2026-07-07--observability--mixed-exporter-isolation/runs/events.jsonl \
  --observability-langfuse \
  --result-file experiments/2026-07-07--observability--mixed-exporter-isolation/runs/result.json \
  > experiments/2026-07-07--observability--mixed-exporter-isolation/runs/stdout.jsonl \
  2> experiments/2026-07-07--observability--mixed-exporter-isolation/runs/stderr.txt
```

Pass requires exit 0 and two exporter reports: file `ok`, LangFuse `failed`.

## Probe B: Artifact Inspection

Inspect:

- `runs/result.json`
- `runs/stdout.jsonl`
- `runs/events.jsonl`

Pass requires stdout and file events to match by type and seq.

## Probe C: Regression Hygiene

Run:

```bash
cargo fmt --check --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo clippy --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  --all-targets -- -D warnings
```

Pass requires all commands to exit 0.
