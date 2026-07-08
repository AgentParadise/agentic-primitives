# Verdict

**go with one setup caveat**: official marketplace plugins are now proven
against real Claude and Codex sessions on the local LangFuse backend, without
using the Rust fallback OTLP exporter for those traces.

This closes the biggest uncertainty behind the pivot: the official plugins are
not merely better in theory or direct-hook fixtures; they work from marketplace
installation through real harness sessions into queryable local LangFuse traces.

## Hypothesis scorecard

| Prediction | Observed | Score | Evidence |
|---|---|---|---|
| MacBook has runtime prerequisites. | Correct: local LangFuse, Claude, Codex, Node 22, `uv`, and Python are present. | correct | `runs/preflight.md` |
| Claude marketplace plugin can be installed/configured and produce a real trace. | Partially correct: marketplace/local install and real trace worked, but install-time `--config` reported values still unset; env fallback was used. | partial | `runs/claude-session/install.md`, `runs/claude-session/trace-compact.json` |
| Codex marketplace plugin can be added/enabled and produce a real trace. | Correct: marketplace/plugin install succeeded and `codex exec` emitted queryable trace `b3d2561d7c0557c12fd427c02a16e2f3`. | correct | `runs/codex-session/install.md`, `runs/codex-session/trace-compact.json` |
| Official-plugin traces have richer UX than fallback OTLP. | Correct: both traces have root IO, semantic generation observations, tool observations, usage/cost, and environment metadata. | correct | `runs/claude-session/trace-observation-sample.json`, `runs/codex-session/trace-observation-sample.json` |
| JSONL/Syntropic fanout remains separate; Rust OTLP is not required. | Correct: no official-plugin trace evidence used `itmux --observability-langfuse`; CLI suppression tests still pass. | correct | `runs/noise-audit.txt`, `runs/cli-exporters-test.txt` |

## Decision

- Continue treating official LangFuse Claude/Codex plugins as canonical for
  rich traces.
- Keep `--observability-file` and `--observability-syntropic-file` as local and
  Syntropic137 fanout, not as competing rich LangFuse writers.
- Keep Rust `langfuse_otlp` as fallback/collector/smoke support and require
  explicit force when official plugin tracing is active.
- Update the .9 close gate from "prove real local backend" to "make setup
  durable and repeatable across MacBook, VPS, and Docker workspace surfaces,
  including the Claude stored-config caveat and official-tool rollups in
  agent-facing summaries."
