# Results

## Summary

| Probe | Evidence | Result |
| --- | --- | --- |
| LangFuse trace link unit set | `runs/langfuse-tests.txt`, `runs/langfuse-tests-exit.txt` | Passed: all four `langfuse_otlp` tests plus the contract filter exited 0. |
| Contract round trip | `runs/contract-roundtrip.txt`, `runs/contract-roundtrip-exit.txt` | Passed: `observability_langfuse_otlp_exporter_round_trips_with_env_refs` exited 0 with default `project_id = None` and `project_id_env = LANGFUSE_PROJECT_ID`. |
| Format check | `runs/fmt-check.txt`, `runs/fmt-check-exit.txt` | Passed: exited 0. |
| Full driver tests | `runs/full-test.txt`, `runs/full-test-exit.txt` | Passed: exited 0. |
| Clippy | `runs/clippy.txt`, `runs/clippy-exit.txt` | Passed after replacing the long resolver argument list with `LangFuseOtlpConfigInput`. |

## Exit Codes

| Command | Exit |
| --- | ---: |
| LangFuse test set | 0 |
| Contract round trip | 0 |
| fmt check | 0 |
| full test | 0 |
| clippy | 0 |

## Observations

- `ObservabilityExporter::LangFuseOtlp` now accepts optional `project_id` and
  `project_id_env`, defaulting the env lookup name to `LANGFUSE_PROJECT_ID`.
- Missing project id does not fail configuration; it only suppresses a UI link.
- The mock transport test asserts that a successful export with
  `LANGFUSE_PROJECT_ID=project-123` reports a link shaped like
  `/project/project-123/traces/<32_hex_trace_id>`.
- `target` remains the OTLP traces endpoint. `links` now represents
  human-facing observability views rather than ingest endpoints.
- Cargo still prints non-fatal APSS template diagnostics about `{{slug}}`
  package names from the git dependency checkout, but all recorded commands
  exited 0 after the clippy refactor.
