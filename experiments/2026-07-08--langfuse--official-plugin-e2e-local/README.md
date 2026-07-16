# Experiment: Official LangFuse Plugin E2E Local

## Question

Can the official LangFuse Claude Code and Codex plugins export rich traces into
the local self-hosted LangFuse stack without enabling the agentic-primitives
Rust OTLP exporter?

## Hypothesis

1. The official Claude plugin can export a fixture Claude transcript into local
   LangFuse with root input/output, at least one generation observation, and at
   least one tool observation.
2. The official Codex plugin can export a fixture Codex rollout into local
   LangFuse with a `Codex Turn` agent observation, generation observations,
   tool observations, usage details, and sidecar dedup state.
3. Direct official hook execution with isolated state is sufficient for this
   validation; global Claude/Codex plugin installation is not required for the
   experiment.
4. No agentic-primitives Rust OTLP exporter run is required or triggered during
   this experiment, proving the official-plugin path can be validated without
   duplicate low-level traces.

## Setup

- Branch: `feat/observability-exporter-primitive`.
- Local LangFuse stack: `http://localhost:3000`, managed by
  `scripts/langfuse-local.sh`.
- Local project credentials: ignored `.agentic/langfuse/langfuse/.env`.
- Official plugin source clones:
  - `/tmp/langfuse-claude-plugin`
  - `/tmp/langfuse-codex-plugin`
- Run state must be isolated under this experiment's `runs/` directory.
- Do not print or commit LangFuse secret values.

## Conditions

- **Claude condition:** invoke the official Claude hook script through `uv run
  --script` with a fixture transcript and isolated `HOME`.
- **Codex condition:** invoke the official Codex bundled hook with explicit
  Node 22/PATH and a fixture rollout transcript.
- **Query condition:** query local LangFuse after each export and capture
  redacted summaries showing trace/observation shape.

## Expected Signals

- Hook command exit status.
- LangFuse query evidence showing official-plugin traces exist.
- Root observation input/output presence.
- Generation observation presence with model/usage where fixture data provides
  usage.
- Tool observation presence with semantic tool names and input/output.
- Codex sidecar file existence after export.
- No `itmux ... --observability-langfuse` or Rust OTLP exporter invocation in
  the run log.

## Out of Scope

- Global marketplace installation.
- Live paid model/API calls.
- Mac Mini durable deployment.
- Full UI screenshot verification.
