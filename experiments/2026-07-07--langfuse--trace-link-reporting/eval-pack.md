# Eval Pack

## Probe A: LangFuse Trace Link Unit Set

Run:

```bash
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  langfuse_otlp
```

Pass requires the mock exporter test to report one link shaped like a LangFuse
trace view when `LANGFUSE_PROJECT_ID` is present.

## Probe B: Contract Round Trip

Run:

```bash
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  observability_langfuse_otlp_exporter_round_trips_with_env_refs
```

Pass requires default deserialization to keep `project_id = null` and
`project_id_env = LANGFUSE_PROJECT_ID`.

## Probe C: Regression Hygiene

Run:

```bash
cargo fmt --check --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo clippy --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  --all-targets -- -D warnings
```

Pass requires all commands to exit 0.
