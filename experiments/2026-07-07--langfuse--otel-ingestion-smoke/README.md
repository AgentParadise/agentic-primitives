# Experiment: LangFuse OTEL Ingestion Smoke

## Question

Can a reachable LangFuse deployment ingest a minimal agentic trace through OTLP
HTTP/protobuf, and can the current `itmux codex-exec --observability-langfuse`
path report a successful LangFuse exporter against that backend?

## Hypothesis

1. A synthetic root span and three child spans can be sent to LangFuse through
   OTLP HTTP/protobuf.
2. The trace appears in LangFuse within 60 seconds and can be found by a unique
   run id.
3. `session.id`, `service.name`, and `langfuse.environment` are preserved well
   enough to filter or identify the run.
4. The current reusable exporter path reports `kind = langfuse_otlp`,
   `status = ok`, and more than zero exported events when the same backend is
   configured through `LANGFUSE_*`.

## Setup

- Branch: `feat/observability-exporter-primitive`.
- Beads: `.6` defines the reusable primitive; `.9` owns LangFuse backend
  integration and is blocked by `.6`.
- LangFuse target: cloud or a reachable self-hosted deployment. The expected
  durable target is a self-hosted Mac Mini deployment.
- Credentials: supplied through env/keychain-backed injection, never committed.

Expected env shape for the current `itmux` exporter:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=agentic-primitives-exp
LANGFUSE_PROJECT_ID=... # optional, enables UI trace links
```

For direct OpenTelemetry CLI probes, the derived OTEL shape is:

```bash
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=$LANGFUSE_BASE_URL/api/public/otel
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=$LANGFUSE_BASE_URL/api/public/otel/v1/traces
OTEL_SERVICE_NAME=agentic-primitives
OTEL_RESOURCE_ATTRIBUTES=langfuse.environment=agentic-primitives-exp,service.name=agentic-primitives
```

The OTLP Authorization header should be Basic auth over
`LANGFUSE_PUBLIC_KEY:LANGFUSE_SECRET_KEY`; capture only redacted evidence.

## Conditions

- **Baseline:** local synthetic trace generation without LangFuse export.
- **Treatment:** same synthetic trace exported to LangFuse over OTLP
  HTTP/protobuf.

## Expected Signals

- redacted OTEL exporter env
- synthetic trace source or fixture
- exporter response/log
- current `itmux codex-exec` result JSON
- LangFuse UI screenshot or API response proving the trace exists
- field preservation notes for the required attributes

## Out of Scope

- Claude or Codex live-session capture.
- LangFuse self-hosting automation.
