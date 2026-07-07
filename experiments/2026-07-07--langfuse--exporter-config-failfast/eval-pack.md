# Eval Pack

## Probe A: Contract Round-Trip

Run:

```bash
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  observability_langfuse_otlp_exporter_round_trips_with_env_refs
```

Pass requires the typed exporter to round-trip and deserialize defaults from
`{"kind":"langfuse_otlp"}`.

## Probe B: Fanout Config Validation

Run:

```bash
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  langfuse_otlp
```

Pass requires endpoint derivation, Basic auth derivation, and missing-env
reporting tests to pass.

## Probe C: Schema and Hygiene

Run:

```bash
cargo run --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  --example emit_contract_schema
cargo fmt --check --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo clippy --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  --all-targets -- -D warnings
rg -n '"langfuse_otlp"' providers/workspaces/interactive-tmux/driver-rs/docs/contract/agent-run-spec.schema.json
```

Pass requires the schema to include `langfuse_otlp` and hygiene checks to pass.
