# Experiment: LangFuse Trace Link Reporting

## Question

Can the Rust `langfuse_otlp` exporter report a human-usable LangFuse trace URL
after a successful export without requiring the project id for ingestion?

## Hypothesis

1. `langfuse_otlp` config accepts an optional `project_id` or
   `LANGFUSE_PROJECT_ID` reference.
2. Missing project id does not fail exporter configuration or OTLP transport.
3. When project id is present and the local receiver export succeeds, the final
   `ObservabilityExportReport.links` contains a LangFuse UI URL shaped as
   `/project/<project_id>/traces/<32_hex_trace_id>`.
4. The report `target` remains the OTLP traces endpoint, while `links` are
   reserved for user-facing observability views.

## Setup

- Branch: `feat/observability-exporter-primitive`.
- Builds on `experiments/2026-07-07--langfuse--otlp-transport-local-receiver`.
- Backend: local receiver HTTP server in Rust tests; no real LangFuse credentials.

## Expected Signals

- `langfuse_otlp` tests pass.
- Contract round-trip tests pass with the added optional project-id fields.
- Full driver tests, fmt, and clippy pass.
- No real LangFuse credentials are required.

## Out of Scope

- Proving the URL resolves in a real LangFuse deployment.
- Querying LangFuse by trace id.
- Self-hosted Mac Mini setup automation.
