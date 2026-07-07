# Results

| Probe | Evidence | Result |
|---|---|---|
| Mock transport | `runs/mock-transport.txt`, `runs/mock-transport-exit.txt` | Passed: `langfuse_otlp_exporter_posts_protobuf_to_mock_receiver` exited 0. |
| LangFuse exporter test set | `runs/langfuse-tests.txt`, `runs/langfuse-tests-exit.txt` | Passed: all four `langfuse_otlp` tests exited 0. |
| Regression hygiene | `runs/fmt.txt`, `runs/fmt-exit.txt`, `runs/full-test.txt`, `runs/full-test-exit.txt`, `runs/clippy.txt`, `runs/clippy-exit.txt` | Passed: fmt, full driver tests, and clippy exited 0. |

## Key Data

| Field | Value |
|---|---|
| Mock transport test exit | 0 |
| LangFuse test set exit | 0 |
| Full driver test exit | 0 |
| Fmt exit | 0 |
| Clippy exit | 0 |
| Mock test observed | POST `/api/public/otel/v1/traces`, `application/x-protobuf`, Basic auth, `x-langfuse-ingestion-version: 4`, non-empty body, root span name |
| Exporter report on mock 2xx | `status = ok`, `events_exported = 1`, `error = none` |

## Classification

The actual Rust `langfuse_otlp` exporter path now performs OTLP HTTP/protobuf
transport against a mock receiver. This proves transport shape and reporting,
but still does not prove LangFuse accepts the payload or makes traces
discoverable/queryable.
