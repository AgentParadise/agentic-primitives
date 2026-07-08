# Verdict

**go**: official LangFuse plugins are empirically validated as the rich trace
path for both Claude and Codex against the local self-hosted LangFuse stack.

This closes the concern raised by the weak `agentic_primitives.run` UI trace:
LangFuse is capable of agent-useful traces when the integration emits
LangFuse-native root, generation, and tool observations. The official plugins do
that; the current Rust OTLP exporter should remain fallback/collector/Syntropic137
support rather than default rich Claude/Codex LangFuse tracing.

## Hypothesis Scorecard

| Prediction | Observed | Score | Notes |
| --- | --- | --- | --- |
| Official Claude plugin exports rich local LangFuse trace from fixture. | Trace has root input/output, `SPAN`, `GENERATION`, and `TOOL` observations, including `Tool: Read` with input/output. | Correct | `runs/claude-summary.md` |
| Official Codex plugin exports rich local LangFuse trace from fixture. | Trace has root input/output, `AGENT`, `GENERATION`, and `TOOL` observations, usage details, total cost, and sidecar dedup state. | Correct | `runs/codex-summary.md` |
| Direct hook execution is sufficient without global plugin install. | Both official hook entrypoints exported traces when invoked directly with fixture transcripts and local LangFuse env. | Correct | Global marketplace install remains the production setup path, but was not needed for this validation. |
| Rust OTLP is not required or triggered. | No `itmux ... --observability-langfuse` writer path or direct Rust OTLP exporter was run. | Correct | `runs/noise-control.md` |
