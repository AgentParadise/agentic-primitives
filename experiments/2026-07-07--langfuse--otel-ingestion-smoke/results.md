# Results

| Probe | Evidence | Result |
|---|---|---|
| Local synthetic trace | `runs/synthetic-trace-source.json`, `runs/local-trace-summary.json` | Generated one root span plus three child spans with required local attributes. |
| LangFuse OTLP export | `runs/otel-exporter-env.redacted.txt`, `runs/langfuse-ingest-response.txt`, `runs/field-preservation-table.md` | Not attempted: required LangFuse base URL, credentials, and OTEL exporter env were absent. |

## Local Synthetic Trace

- Run id: see `runs/local-trace-summary.json`
- Span count: 4
- Root span: `agentic_primitives.synthetic_run`
- Child spans: `session_started`, `tool_execution_started`,
  `tool_execution_completed`
- Required local attributes present: `session.id`, `service.name`,
  `langfuse.environment`

## Export Preflight

All required LangFuse/OTEL env vars were missing in this shell:

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_TRACING_ENVIRONMENT`
- `OTEL_EXPORTER_OTLP_PROTOCOL`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
- `OTEL_SERVICE_NAME`
- `OTEL_RESOURCE_ATTRIBUTES`
