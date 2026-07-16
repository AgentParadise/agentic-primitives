# Verdict

**go**: the `itmux` CLI now mechanically enforces the single-active-rich-exporter
rule for human-facing Claude/Codex runs while keeping both required non-rich
paths intact.

When official LangFuse plugin tracing is active via `TRACE_TO_LANGFUSE=true`,
the CLI suppresses the Rust `langfuse_otlp` fallback writer by default and
keeps file JSONL fanout. The explicit `--observability-langfuse-force` flag
restores Rust OTLP for fallback smoke, collector, unsupported harness, or
Syntropic137 routing.

## Hypothesis scorecard

| Prediction | Observed | Score | Notes |
|---|---|---|---|
| Current CLI builder configures `langfuse_otlp` whenever `--observability-langfuse` is supplied. | Confirmed by baseline code inspection. | correct | `runs/baseline-code-inspection.md` |
| A CLI-level guard can suppress only Rust `langfuse_otlp` when official plugin tracing is active while preserving JSONL. | Confirmed by `cli_exporters_suppress_langfuse_when_official_plugin_tracing_is_active`. | correct | `runs/cli-exporters-test.txt` |
| Fallback Rust OTLP can remain available through an explicit override. | Confirmed by `cli_exporters_can_force_langfuse_when_official_plugin_tracing_is_active`. | correct | `runs/cli-exporters-test.txt` |

## Decision Impact

- Official LangFuse Claude/Codex plugins stay canonical for rich traces.
- JSONL fanout remains safe to run alongside those official plugins.
- Rust OTLP is still available, but it is no longer an accidental duplicate
  rich writer when `TRACE_TO_LANGFUSE=true`.
- `.9` still needs real-session official plugin setup and CLI/MCP learning-loop
  validation before closure; this experiment only closes the default noise-risk
  guard in the `itmux` CLI.
