# Results

## Summary

| Probe | Evidence | Result |
| --- | --- | --- |
| CLI exporter unit tests | `runs/cli-exporter-tests.txt`, `runs/cli-exporter-tests-exit.txt` | Passed: both `cli_exporters` tests exited 0. |
| `itmux run` help surface | `runs/run-help.txt`, `runs/run-help-exit.txt` | Passed: help lists all LangFuse setup flags. |
| `itmux codex-exec` help surface | `runs/codex-exec-help.txt`, `runs/codex-exec-help-exit.txt` | Passed: help lists all LangFuse setup flags. |
| Format check | `runs/fmt-check.txt`, `runs/fmt-check-exit.txt` | Passed: exited 0. |
| Full driver tests | `runs/full-test.txt`, `runs/full-test-exit.txt` | Passed: exited 0. |
| Clippy | `runs/clippy.txt`, `runs/clippy-exit.txt` | Passed: exited 0. |

## Exit Codes

| Command | Exit |
| --- | ---: |
| CLI exporter tests | 0 |
| `run --help` | 0 |
| `codex-exec --help` | 0 |
| fmt check | 0 |
| full test | 0 |
| clippy | 0 |

## Observations

- `itmux run --help` exposes `--observability-langfuse`,
  `--langfuse-base-url`, `--langfuse-project-id`, and `--langfuse-label`.
- `itmux codex-exec --help` exposes the same flags.
- The shared CLI builder maps those flags into
  `ObservabilityExporter::LangFuseOtlp` with secret env refs fixed to
  `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`.
- `LANGFUSE_PROJECT_ID` remains optional. The default link label is
  `LangFuse trace` when no label is supplied.
- Cargo still prints non-fatal APSS template diagnostics about `{{slug}}`
  package names from the git dependency checkout, but all recorded commands
  exited 0.
