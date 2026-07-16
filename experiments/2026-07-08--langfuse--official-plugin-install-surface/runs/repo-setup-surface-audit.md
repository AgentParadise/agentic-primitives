# Repo Setup Surface Audit

Captured after hypothesis commit `0542332`.

## Files Inspected

- `docs/guides/langfuse-observability-setup.md`
- `plugins/observability/README.md`
- `docs/adrs/038-modular-agent-observability.md`
- `providers/workspaces/interactive-tmux/driver-rs/src/main.rs`
- `runs/itmux-run-help.txt`

## Matches

- Architecture pivot is present: official LangFuse Claude/Codex plugins are
  canonical for rich traces.
- `--observability-file` remains documented as durable local JSONL fanout.
- `--observability-syntropic-file` is separate from both official plugin
  tracing and fallback OTLP.
- `TRACE_TO_LANGFUSE=true` suppresses fallback Rust `langfuse_otlp` by default.
- `--observability-langfuse-force` is present in CLI help for deliberate
  fallback/collector smoke paths.

## Drift Found

- The guide's "Required Runtime Environment" section read as if all LangFuse
  paths required the same env variables. Official Claude plugin configuration
  is plugin-managed and does not require `LANGFUSE_TRACING_ENVIRONMENT`.
- The guide did not mention the official Claude plugin's install-time
  `--config` path or optional `CC_LANGFUSE_*` controls.
- The guide did not mention Codex's Node.js 22+ requirement.
- The guide did not describe Codex JSON config precedence or
  `LANGFUSE_CODEX_*` overrides.
- The observability plugin README named the official repositories but did not
  summarize the distinct Claude-vs-Codex setup mechanisms.

## Treatment

Patched:

- `docs/guides/langfuse-observability-setup.md`
- `plugins/observability/README.md`

No Rust exporter implementation change was needed.

## Remaining Gap

This experiment audits and aligns install/config docs. It does not prove a real
interactive Claude or Codex session installed through the marketplace writes a
new trace to the target LangFuse backend. That remains the next .9 close gate.
