# Results

## Headline

| Probe | Evidence | Result |
|---|---|---|
| Baseline current behavior | `runs/baseline-code-inspection.md` | Confirmed no pre-existing guard: `langfuse_otlp` was configured whenever `langfuse.enabled` was true. |
| CLI exporter tests | `runs/cli-exporters-test.txt`, `runs/cli-exporters-test-exit.txt` | Passed: four focused `cli_exporters` tests passed. |
| Help flag visibility | `runs/help-flags.txt`, `runs/help-flags-exit.txt` | Passed: `--observability-langfuse-force` appears on `run`, `codex-exec`, and `claude-transcript`. |
| Formatting | `runs/fmt-check.txt`, `runs/fmt-check-exit.txt` | Passed after applying `cargo fmt`. |
| Diff hygiene | `runs/diff-check.txt`, `runs/diff-check-exit.txt` | Passed. |

## Baseline

The baseline confirmed the first prediction. The previous
`build_observability_exporters` implementation added
`ObservabilityExporter::LangFuseOtlp` whenever `langfuse.enabled` was true. It
did not inspect `TRACE_TO_LANGFUSE` or any official-plugin tracing signal.

## Treatment

Implemented a CLI-level guard:

- `LangFuseCliOptions` now carries `official_plugin_tracing_active`.
- The CLI sets that field from truthy `TRACE_TO_LANGFUSE`.
- `--observability-langfuse` no longer adds Rust `langfuse_otlp` when official
  plugin tracing is active.
- `--observability-file` still adds file JSONL fanout in that suppressed case.
- `--observability-langfuse-force` restores the Rust OTLP exporter for
  deliberate fallback/collector/Syntropic137 use.

The lower-level typed contract remains unchanged. Programmatic spec consumers
can still configure `ObservabilityExporter::LangFuseOtlp` directly.

## Test Evidence

`runs/cli-exporters-test.txt` shows:

- `cli_exporters_suppress_langfuse_when_official_plugin_tracing_is_active ... ok`
- `cli_exporters_can_force_langfuse_when_official_plugin_tracing_is_active ... ok`
- existing file+LangFuse and missing-project-id tests still pass.

Exit files:

- `runs/cli-exporters-test-exit.txt`: `0`
- `runs/fmt-check-exit.txt`: `0`
- `runs/diff-check-exit.txt`: `0`
- `runs/help-flags-exit.txt`: `0`

## Notes

An initial `cargo fmt --check` run failed only on formatting of the new
`truthy_env` helper. After `cargo fmt`, the frozen hygiene commands passed and
the evidence files were replaced with the passing rerun output.
