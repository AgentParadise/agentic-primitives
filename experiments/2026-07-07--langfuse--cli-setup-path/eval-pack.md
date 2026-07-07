# Eval Pack

## Probe A: CLI Exporter Unit Tests

Run:

```bash
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  cli_exporters
```

Pass requires the shared CLI exporter builder to emit file and LangFuse
exporters with the expected env-var refs and optional project-id behavior.

## Probe B: Help Surface

Run:

```bash
cargo run --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml -- run --help
cargo run --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml -- codex-exec --help
```

Pass requires both help surfaces to list `--observability-langfuse`,
`--langfuse-base-url`, `--langfuse-project-id`, and `--langfuse-label`.

## Probe C: Regression Hygiene

Run:

```bash
cargo fmt --check --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo clippy --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  --all-targets -- -D warnings
```

Pass requires all commands to exit 0.
