# Pivot Decision

## Decision

Use the official LangFuse Claude Code and Codex plugins as the canonical rich
LangFuse trace integrations for those harnesses.

The agentic-primitives observability primitive should wrap, configure, validate,
and document those official plugins instead of competing with them for rich
LangFuse trace UX.

## Ownership Boundaries

### Official LangFuse Plugins

Own rich LangFuse traces for supported harnesses:

- Claude Code: transcript-backed turn spans, generation observations, tool
  observations, usage, subagent/task handling, root input/output.
- Codex: rollout-backed `Codex Turn` agent observations, generation
  observations, tool observations, subagent nesting, usage, dedup sidecars.

### JSONL Fanout

Own durable local and portable evidence:

- Always-on local run artifact when requested by the workspace.
- Replay/debug input for MacBook, VPS, Docker, CI, and Syntropic137 consumers.
- Source-of-truth normalized event stream for backends that are not LangFuse or
  for post-run transforms.

### Rust OTLP Exporter

Own fallback/collector support:

- Useful when no official plugin exists.
- Useful for Syntropic137 or generic OTEL collector pipelines.
- Useful for smoke tests and backend reachability.
- Not the default rich LangFuse path for Claude or Codex while official
  plugins exist.

If the Rust exporter is used for LangFuse directly, it must either:

- be explicitly selected by the user/config; or
- be upgraded to emit LangFuse-native root input/output, observation
  input/output, semantic observation types, and paired tool spans.

### Syntropic137

Consumes normalized JSONL or collector events. It should not depend on
LangFuse-specific SDK behavior, and it should not force LangFuse users to ingest
duplicate low-level event spans.

## Noise-Control Rule

Default policy per harness run:

| Destination | Default | Rationale |
| --- | --- | --- |
| JSONL file fanout | on when observability is requested | durable local source of truth; low backend noise |
| Official LangFuse Claude plugin | on for Claude rich LangFuse tracing | canonical supported integration |
| Official LangFuse Codex plugin | on for Codex rich LangFuse tracing | canonical supported integration |
| Rust OTLP to LangFuse | off by default for Claude/Codex | would duplicate/noisify official traces |
| Rust OTLP to collector/Syntropic137 | explicit opt-in | useful backend bridge without polluting LangFuse |
| Rust OTLP to LangFuse for unsupported harnesses | explicit opt-in or fallback | acceptable when no official plugin exists |

Single-active-rich-exporter invariant:

For a given run, at most one backend path should create rich LangFuse trace
observations by default. JSONL can run in parallel. Collector/fallback OTLP must
be separately named and explicitly configured.

## Next Experiment Before Closing `.9`

Run an end-to-end official-plugin validation against local self-hosted LangFuse:

1. Install/configure official Claude plugin against the local LangFuse project.
2. Install/configure official Codex plugin against the same local project.
3. Run one minimal Claude Code tool turn and one minimal Codex tool turn.
4. Capture LangFuse UI/API evidence showing root input/output, generation
   observations, tool observations, usage/cost, environment, session grouping,
   and agent-query/MCP retrieval.
5. Verify the current agentic-primitives Rust OTLP exporter is not also sending
   duplicate rich traces by default.

