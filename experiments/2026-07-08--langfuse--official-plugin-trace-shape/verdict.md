# Verdict

**go**: pivot to official LangFuse marketplace plugins as the canonical rich
trace integrations for Claude Code and Codex.

The current Rust OTLP exporter should remain in the architecture, but as an
explicit fallback/collector/Syntropic137 bridge. It should not be the default
rich LangFuse path for Claude or Codex while official plugins exist.

This was not a total implementation validation: the official Codex plugin test
suite did not run in this `/tmp` shell because of local Node/pnpm/native binding
setup. The source-level contract is still strong enough to make the architecture
decision, and the next experiment should validate both official plugins
end-to-end against the local LangFuse stack.

## Hypothesis Scorecard

| Prediction | Observed | Score | Notes |
| --- | --- | --- | --- |
| Official plugins emit semantic root/generation/tool observations. | Claude source + tests pass; Codex source passes, tests inconclusive due local Node/pnpm/native binding setup. | Partial | Prediction direction holds. Runtime validation for Codex remains a follow-up. |
| Current Rust OTLP is useful but noisier in LangFuse. | Confirmed by source: generic event spans, missing root IO, separate 1 ms tool start/end spans, token usage as generic event. | Correct | Matches the observed weak LangFuse UI. |
| Official plugins should be canonical, JSONL always-on, Rust OTLP fallback/collector bridge. | Supported by evidence and written in `runs/pivot-decision.md`. | Correct | This resolves the duplicate/noise concern without removing Syntropic137 support. |
| A single-active-rich-exporter rule controls noise. | Supported as the explicit default policy in `runs/pivot-decision.md`. | Correct | JSONL may run in parallel; Rust OTLP requires explicit opt-in for Claude/Codex. |
