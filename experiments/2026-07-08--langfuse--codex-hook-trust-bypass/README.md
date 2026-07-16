# Codex Hook Trust Bypass

## Question

Does `codex exec --dangerously-bypass-hook-trust` allow the installed official
LangFuse Codex plugin Stop hook to run automatically and upload a fresh rich
trace?

## Hypothesis

1. The previous no-go was caused by non-interactive Codex hook trust, not by
   LangFuse credentials or plugin export logic.
2. Running a fresh `codex exec --json --sandbox read-only
   --dangerously-bypass-hook-trust` turn with `TRACE_TO_LANGFUSE=true`,
   `LANGFUSE_CODEX_DEBUG=true`, and `LANGFUSE_CODEX_FAIL_ON_ERROR=true` will
   automatically create a `.langfuse` sidecar next to the fresh rollout.
3. The fresh trace will be discoverable through `itmux langfuse-traces
   --harness codex --environment local-macbook`.
4. The trace summary will show official-plugin rich data: `Codex Turn`,
   `GENERATION`, `TOOL`, model `gpt-5.5`, non-zero usage/cost, and
   `exec_command`.
5. No Rust OTLP fallback exporter flags or raw LangFuse keys will appear in
   artifacts.

## Setup

- Repository: `agentic-primitives`
- Prior no-go:
  `experiments/2026-07-08--langfuse--codex-official-hooks-fresh-run-corrected`
- Official plugin:
  `tracing@codex-observability-plugin`, installed and enabled in user config
- Codex config includes `plugin_hooks = true`

## Conditions

1. Baseline: record latest Codex trace and doctor readiness.
2. Treatment: run one fresh Codex exec turn with hook trust bypass and debug
   fail-on-error enabled.
3. Verification: check the fresh rollout sidecar and query the resulting trace.
4. Hygiene: scan for raw keys and fallback exporter flags.
