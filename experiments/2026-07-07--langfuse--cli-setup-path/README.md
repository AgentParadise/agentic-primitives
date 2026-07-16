# Experiment: LangFuse CLI Setup Path

## Question

Can a new machine enable LangFuse export for `itmux run` and
`itmux codex-exec` through simple CLI flags plus `LANGFUSE_*` environment
variables, without writing a JSON spec by hand?

## Hypothesis

1. `itmux run` exposes `--observability-langfuse`,
   `--langfuse-base-url`, `--langfuse-project-id`, and `--langfuse-label`.
2. `itmux codex-exec` exposes the same flags.
3. The CLI maps those flags into the typed `ObservabilityExporter::LangFuseOtlp`
   config while keeping public/secret keys referenced by environment variable
   names.
4. Project id remains optional; missing project id must not block export.

## Setup

- Branch: `feat/observability-exporter-primitive`.
- Builds on `experiments/2026-07-07--langfuse--trace-link-reporting`.
- No real LangFuse credentials are required for this local setup-path probe.

## Expected Signals

- CLI exporter unit tests pass.
- `itmux run --help` shows the LangFuse setup flags.
- `itmux codex-exec --help` shows the same LangFuse setup flags.
- Full driver tests, fmt, and clippy pass.

## Out of Scope

- Real LangFuse backend ingestion.
- Secret storage or keychain injection.
- Installing/running a Mac Mini LangFuse deployment.
