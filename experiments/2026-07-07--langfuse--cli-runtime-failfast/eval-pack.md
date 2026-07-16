# Eval Pack

## Probe A: Runtime Fail-Fast

Run:

```bash
cargo run --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml -- \
  codex-exec \
  --codex-bin experiments/2026-07-07--langfuse--cli-runtime-failfast/fixtures/fake-codex-success.sh \
  --prompt "synthetic LangFuse failfast" \
  --observability-langfuse \
  --result-file experiments/2026-07-07--langfuse--cli-runtime-failfast/runs/result.json \
  > experiments/2026-07-07--langfuse--cli-runtime-failfast/runs/stdout.jsonl \
  2> experiments/2026-07-07--langfuse--cli-runtime-failfast/runs/stderr.txt
```

Pass requires exit 0, a successful run result, and a failed `langfuse_otlp`
exporter report naming a missing env var.

## Probe B: Artifact Inspection

Inspect:

- `runs/result.json`
- `runs/stdout.jsonl`

Pass requires every stdout line to parse as `AgentRunEvent` and the result file
to contain the failed exporter report.

## Probe C: Regression Hygiene

Run:

```bash
cargo fmt --check --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo clippy --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  --all-targets -- -D warnings
```

Pass requires all commands to exit 0.
