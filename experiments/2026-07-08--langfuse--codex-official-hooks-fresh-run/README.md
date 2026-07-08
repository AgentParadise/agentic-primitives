# Codex Official Hooks Fresh Run

## Question

After enabling `plugin_hooks = true` in the user Codex config, does a fresh
Codex exec session emit a new rich official LangFuse plugin trace into the
local LangFuse backend without using the Rust OTLP fallback exporter?

## Hypothesis

1. With the existing local LangFuse Docker Compose stack and ignored local
   project keys, a fresh `codex exec --json` run with `TRACE_TO_LANGFUSE=true`
   will create a new LangFuse trace after the current latest Codex trace.
2. The new trace will be discoverable through `itmux langfuse-traces
   --harness codex --environment local-macbook`.
3. `itmux langfuse-trace --api legacy-trace --output summary --trace-id <id>`
   will report a rich official-plugin shape: trace name `Codex Turn`, at least
   one `GENERATION`, at least one `TOOL`, model `gpt-5.5`, non-zero token usage,
   non-zero calculated cost, and tool name `exec_command`.
4. The run will not use `itmux --observability-langfuse` or
   `--observability-langfuse-force`; any trace produced is therefore from the
   official Codex plugin path, not the Rust fallback exporter.
5. The experiment artifacts will not contain raw LangFuse public or secret keys.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Local LangFuse: `.agentic/langfuse/langfuse`
- User Codex config: `~/.codex/config.toml`
- Prior remediation:
  `experiments/2026-07-08--langfuse--codex-plugin-hooks-remediation`

## Conditions

1. Baseline: record doctor output, local LangFuse status, Codex config excerpt,
   and latest recent Codex traces before the fresh run.
2. Treatment: run one fresh Codex exec prompt with local LangFuse env loaded
   from the ignored LangFuse `.env`, `TRACE_TO_LANGFUSE=true`, and no
   `itmux` fallback export flags.
3. Verification: query recent Codex traces, identify a trace containing the
   marker or newer than baseline, and query its compact summary.
4. Hygiene: scan committed run artifacts for raw LangFuse keys and record
   `git diff --check`.

## Expected Signals

- Codex doctor readiness remains true.
- Recent Codex trace count increases or the latest Codex trace id changes.
- The identified trace summary contains a rich official-plugin shape with model,
  generation, token, cost, and `exec_command` tool data.
- No fallback OTLP command appears in the command artifacts.
