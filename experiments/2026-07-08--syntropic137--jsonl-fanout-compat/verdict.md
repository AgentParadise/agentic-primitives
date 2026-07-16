# Verdict

**go with a scoped limitation**: agentic-primitives now has a dedicated
Syntropic137 JSONL projection path for session/tool observability, while the
canonical `AgentRunEvent` file and LangFuse ownership rules remain intact.

The experiment proved that the current `--observability-file` output is not
directly consumable by Syntropic137's existing HookWatcher. Instead of changing
that canonical artifact, `syntropic_jsonl` provides the top-level
`event_type`/`session_id`/`timestamp` shape that Syntropic137 already parses.

## Hypothesis scorecard

| Prediction | Observed | Score | Notes |
|---|---|---|---|
| Syntropic137 HookWatcher expects top-level hook-style fields. | Confirmed by parser surface and control parse. | correct | `runs/syntropic-parser-surface.md`, `runs/control-parse.json` |
| Current `AgentRunEvent` JSONL is skipped by HookWatcher. | Baseline parsed count was `0`. | correct | `runs/baseline-parse.json` |
| A dedicated Syntropic137 exporter can preserve local fanout without LangFuse noise. | `syntropic_jsonl` exporter and CLI flag implemented; tests pass. | correct | `runs/treatment-test.txt` |

## Decision Impact

- Do not repurpose `--observability-file`; it remains the full normalized
  `AgentRunEvent` artifact.
- Use `--observability-syntropic-file` when Syntropic137 needs hook-style
  session/tool ingestion.
- Do not use fallback LangFuse OTLP as the Syntropic137 integration path for
  Claude/Codex official-plugin runs.
- Track Syntropic137 token/cost parity separately: current HookWatcher skips
  `token_usage` rows, so Syntropic137 must either extend its hook map or keep
  using transcript/OTLP lanes for token metrics.
