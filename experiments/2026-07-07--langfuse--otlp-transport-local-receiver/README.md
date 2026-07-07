# Experiment: LangFuse OTLP Transport Local Receiver

## Question

Can the actual Rust `langfuse_otlp` exporter path send normalized
`AgentRunEvent` data as an OTLP HTTP/protobuf request to a receiver, using the
same fanout/reporting path that `itmux run` uses?

## Hypothesis

1. A configured `langfuse_otlp` exporter buffers normalized run events and sends
   exactly one `POST` to `/api/public/otel/v1/traces` on `finish()`.
2. The request uses `Content-Type: application/x-protobuf`, Basic auth, and
   `x-langfuse-ingestion-version: 4`.
3. The protobuf body is non-empty and includes the root span name
   `agentic_primitives.run`.
4. A 2xx local receiver response yields an `ObservabilityExportReport` with
   `status = ok`, event count equal to buffered events, and no error.

## Setup

- Branch: `feat/observability-exporter-primitive`.
- Builds on:
  `experiments/2026-07-07--langfuse--otel-preflight-local-receiver` and
  `experiments/2026-07-07--langfuse--exporter-config-failfast`.
- Backend: local receiver HTTP server in a Rust test.

## Expected Signals

- `langfuse_otlp_exporter_posts_protobuf_to_local_receiver` passes
- all `langfuse_otlp` tests pass
- full driver tests, fmt, and clippy pass
- no real LangFuse credentials are required

## Out of Scope

- Real LangFuse ingestion and trace discoverability.
- LangFuse API trace-query integration.
- Span/generation semantic mapping beyond a basic run root span and event spans.
