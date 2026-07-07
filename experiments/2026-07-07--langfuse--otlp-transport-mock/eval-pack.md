# Eval Pack

## Probe A: Mock Transport

Run:

```bash
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  langfuse_otlp_exporter_posts_protobuf_to_mock_receiver
```

Pass requires a local mock receiver to observe a `POST` to
`/api/public/otel/v1/traces` with protobuf content type, Basic auth,
LangFuse ingestion-version header, and a non-empty body.

## Probe B: LangFuse Exporter Test Set

Run:

```bash
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  langfuse_otlp
```

Pass requires endpoint derivation, auth derivation, missing-env fail-fast, and
mock transport tests to pass.

## Probe C: Regression Hygiene

Run:

```bash
cargo fmt --check --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml
cargo clippy --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml \
  --all-targets -- -D warnings
```

Pass requires all commands to exit 0.
