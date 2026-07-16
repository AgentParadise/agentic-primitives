# Official Plugin Real Session

## Question

Can marketplace-installed official LangFuse plugins trace real Claude Code and
Codex sessions into the local LangFuse backend while the agentic-primitives
fallback Rust OTLP exporter stays out of the rich-trace path by default?

## Hypothesis

1. This MacBook has the runtime prerequisites for the official plugin path:
   Claude Code, Codex, Node.js 22+, `uv`, Python, and a running local LangFuse
   stack with project credentials.
2. The official Claude marketplace plugin can be installed/configured in a
   project or local scope and will produce a LangFuse trace from a real Claude
   Code session without invoking `itmux --observability-langfuse`.
3. The official Codex marketplace plugin can be added/enabled for this project
   and will produce a LangFuse trace from a real Codex session with
   `TRACE_TO_LANGFUSE=true`.
4. The resulting official-plugin traces will have richer UX than the fallback
   OTLP trace: root input/output, generation observations, semantic tool
   observations, usage/cost where the harness exposes it, and environment or
   session metadata usable for filtering.
5. Agentic-primitives JSONL/Syntropic137 fanout remains separate from this
   real-session proof; no Rust OTLP export should be required for these two
   official-plugin traces.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Local LangFuse: `scripts/langfuse-local.sh status`
- Official plugins:
  - Claude: `langfuse/Claude-Observability-Plugin`
  - Codex: `langfuse/codex-observability-plugin`

## Conditions

1. Preflight: record installed tool versions, local LangFuse status, current
   plugin state, and redacted local LangFuse project config.
2. Claude treatment: install/configure the official Claude plugin through the
   marketplace path and run one real Claude Code prompt.
3. Codex treatment: add/enable the official Codex plugin through the Codex
   marketplace path and run one real Codex prompt.
4. Query: use LangFuse API or existing `itmux langfuse-*` commands to discover
   and summarize traces produced by the two sessions.
5. Noise audit: confirm the evidence path did not require fallback
   `--observability-langfuse` for these official-plugin traces.

## Expected Signals

- `runs/preflight.md` shows all hard prerequisites are present.
- `runs/claude-session/` contains install/config/run/query evidence or a
  precise blocker.
- `runs/codex-session/` contains install/config/run/query evidence or a
  precise blocker.
- `results.md` names trace IDs only after they are queryable in LangFuse.
- `verdict.md` does not close .9 unless both real-session traces are proven and
  queryable.
