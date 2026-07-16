# Single Rich Exporter Guard

## Question

Can `itmux` mechanically enforce the single-active-rich-exporter rule so an
official LangFuse Claude/Codex plugin and the Rust `langfuse_otlp` fallback do
not both write rich LangFuse traces for the same run by default?

## Hypothesis

1. The current CLI exporter builder will configure `langfuse_otlp` whenever
   `--observability-langfuse` is supplied, even if `TRACE_TO_LANGFUSE=true`
   indicates an official LangFuse plugin is active.
2. Adding a guard in the CLI exporter builder can suppress only the Rust
   `langfuse_otlp` exporter when official plugin tracing is active, while still
   preserving `--observability-file` JSONL fanout.
3. The fallback Rust OTLP path can remain available through an explicit
   override for collector/smoke/Syntropic137 use.

## Setup

- Worktree:
  `/Users/neural/Code/Syntropic137/agentic-primitives_worktrees/20260707_itmux-run`
- Branch: `feat/observability-exporter-primitive`
- Primary code under test:
  `providers/workspaces/interactive-tmux/driver-rs/src/main.rs`
- Verification target: Rust driver unit tests around CLI exporter construction.

## Conditions

### Baseline

Inspect and test the current `build_observability_exporters` behavior with:

- `observability_file = Some(...)`
- `langfuse.enabled = true`
- `TRACE_TO_LANGFUSE=true`

Expected baseline: both file and `langfuse_otlp` exporters are configured.

### Treatment

Add a single-active-rich-exporter guard:

- if official plugin tracing is detected, suppress Rust `langfuse_otlp`;
- keep file JSONL configured;
- allow explicit fallback override to retain Rust `langfuse_otlp` for smoke,
  collector, unsupported harness, or Syntropic137 use.

Expected treatment: default official-plugin sessions configure file JSONL only,
and override sessions configure file JSONL plus `langfuse_otlp`.

## Expected Signals

- A unit test proves default suppression when `TRACE_TO_LANGFUSE=true`.
- A unit test proves JSONL fanout is preserved during suppression.
- A unit test proves explicit override restores `langfuse_otlp`.
- CLI help/docs describe the suppression and override without changing the
  official plugin canonical path.
