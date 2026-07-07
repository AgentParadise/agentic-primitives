# Eval Pack

## Probe A: Local Synthetic Trace

Generate a synthetic trace with:

- one root span named `agentic_primitives.synthetic_run`
- child span `session_started`
- child span `tool_execution_started`
- child span `tool_execution_completed`
- unique run id present as `session.id` and trace metadata

Capture:

- `runs/synthetic-trace-source.json`
- `runs/local-trace-summary.json`

## Probe B: LangFuse OTLP Export

Export the same synthetic trace to:

```text
$LANGFUSE_BASE_URL/api/public/otel/v1/traces
```

using OTLP HTTP/protobuf and Basic auth.

Capture:

- `runs/otel-exporter-env.redacted.txt`
- `runs/langfuse-ingest-response.log`
- `runs/langfuse-trace-screenshot.png` or `runs/langfuse-trace-api-response.json`
- `runs/field-preservation-table.md`

## Scoring

Pass requires:

- export command exits successfully
- LangFuse contains one trace discoverable by the run id
- root span plus all three child spans appear
- `session.id`, `service.name`, and `langfuse.environment` are visible or
  queryable

Classify failures as:

- auth/config failure
- unsupported protocol or endpoint shape
- successful ingestion but delayed or missing UI/API visibility
- trace exists but required attributes are lost
