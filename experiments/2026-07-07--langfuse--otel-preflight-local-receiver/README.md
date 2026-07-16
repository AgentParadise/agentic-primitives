# Experiment: LangFuse OTLP Preflight Local Receiver

## Question

Before a reachable LangFuse deployment is available, can we validate the
LangFuse exporter configuration contract locally: endpoint derivation, Basic
auth construction, redaction, content type, and required trace/resource
attributes?

## Hypothesis

1. Given `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`,
   `LANGFUSE_SECRET_KEY`, and `LANGFUSE_TRACING_ENVIRONMENT`, the exporter
   preflight can derive the OTLP traces endpoint:
   `$LANGFUSE_BASE_URL/api/public/otel/v1/traces`.
2. The request uses OTLP HTTP/protobuf shape: `POST`,
   `Content-Type: application/x-protobuf`, and Basic auth derived from
   `LANGFUSE_PUBLIC_KEY:LANGFUSE_SECRET_KEY`.
3. Required attributes for the future run-event mapping are present locally:
   `service.name`, `deployment.environment.name`, `langfuse.environment`,
   `session.id`, `langfuse.session.id`, `langfuse.trace.name`, and
   `langfuse.trace.metadata.run_id`.
4. Redacted evidence can prove the preflight without leaking public/secret key
   values.

## Setup

- Branch: `feat/observability-exporter-primitive`.
- Beads: `.6` fanout substrate is ready; `.9` owns LangFuse backend/exporter
  work.
- Backend: local receiver HTTP server only. This experiment does not prove
  LangFuse ingestion or UI/API trace discoverability.

## Conditions

- **Baseline:** inspect existing LangFuse env and confirm whether real export
  can run.
- **Treatment:** set synthetic LangFuse env against a local local receiver endpoint and
  send one preflight OTLP-shaped trace request.

## Expected Signals

- local receiver request capture with method/path/content-type/auth status
- redacted env/config summary
- required attribute preservation table
- preflight summary classifying what is proven and what still requires real
  LangFuse

## Out of Scope

- Real LangFuse ingestion.
- Protobuf semantic validation by LangFuse.
- Run-event to span/generation mapping.
- Agent trace-query integration.
