# Noise-Control Check

Commands used in this experiment:

- official Claude hook:
  `uv run --quiet --script /tmp/langfuse-claude-plugin/hooks/langfuse_hook.py`
- official Codex hook:
  `node /tmp/langfuse-codex-plugin/plugins/tracing/dist/index.mjs`
- query:
  `target/debug/itmux langfuse-traces`
  and `target/debug/itmux langfuse-trace`

Commands intentionally not used:

- `itmux run --observability-langfuse`
- `itmux codex-exec --observability-langfuse`
- direct Rust OTLP exporter execution

Result: pass. Official plugin traces were exported without running the
agentic-primitives Rust OTLP exporter, so the official path can be validated
without creating duplicate low-level LangFuse spans.

