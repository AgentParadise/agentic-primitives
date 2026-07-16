# Portable LangFuse Setup Doctor

## Question

Can agentic-primitives provide a secret-safe preflight command that helps a new
MacBook, VPS, or Docker workspace verify the intended observability ownership:
official LangFuse Claude/Codex plugins are canonical for rich traces, JSONL and
Syntropic137 fanout remain available, and Rust OTLP is quiet by default when an
official plugin is active?

## Hypothesis

1. The current repository has strong documentation and backend evidence, but no
   single executable preflight that summarizes official plugin readiness,
   runtime `LANGFUSE_*` readiness, Syntropic137 JSONL support, and the
   single-active-rich-exporter guard without printing secrets.
2. A small shell-based doctor can be portable across MacBook, VPS, and Docker
   because it only needs POSIX shell, optional `claude`, optional `codex`,
   optional `node`, optional `uv`, and repo-local files.
3. The doctor should not install plugins or call LangFuse by default. It should
   classify readiness and tell the operator what is missing, while preserving
   a no-secrets evidence artifact for experiments and board handoffs.
4. The doctor can mechanically verify the noise-control contract by running the
   focused `cli_exporters` Rust tests when `cargo` is present, or by reporting
   that source-level validation was skipped when it is not.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Prior evidence:
  - `experiments/2026-07-08--langfuse--official-plugin-real-session`
  - `experiments/2026-07-08--langfuse--runtime-noise-guard`
  - `experiments/2026-07-08--langfuse--official-plugin-discovery-report`

## Conditions

1. Baseline: inspect current repo for an executable setup doctor.
2. Treatment: add a secret-safe `scripts/langfuse-observability-doctor.sh`.
3. Run the doctor in this worktree against the local MacBook environment.
4. Run focused validation for the doctor and the existing runtime guard.
5. Capture no raw LangFuse keys in committed artifacts.

## Expected Signals

- Baseline shows no existing portable doctor command.
- Treatment doctor emits machine-readable JSON and human-readable text.
- JSON reports:
  - official Claude/Codex plugin prerequisites and configuration hints;
  - `LANGFUSE_*` readiness as set/missing only;
  - `TRACE_TO_LANGFUSE` state;
  - JSONL/Syntropic137 fanout support from repo-local CLI help/source;
  - whether the focused single-rich-exporter guard tests pass.
- Secret scan over artifacts finds no `pk-lf-*` or `sk-lf-*` values.
