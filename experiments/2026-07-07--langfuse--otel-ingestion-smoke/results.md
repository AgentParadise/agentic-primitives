# Results

| Probe | Evidence | Result |
|---|---|---|
| Local synthetic trace | `runs/synthetic-trace-source.json`, `runs/local-trace-summary.json` | Generated one root span plus three child spans with required local attributes. |
| LangFuse OTLP export | `runs/otel-exporter-env.redacted.txt`, `runs/keychain-check.redacted.txt`, `runs/langfuse-ingest-response.txt`, `runs/field-preservation-table.md` | Not attempted: required LangFuse base URL and credentials were absent. |
| Current `itmux` exporter path | `experiments/2026-07-07--langfuse--cli-runtime-failfast`, `experiments/2026-07-07--observability--langfuse-otel-export/runs/current/result.json` | Current exporter path exists and fails safely when `LANGFUSE_*` is absent; real backend success remains unproven. |
| Repeatable real-backend runner | `run-smoke.sh`, `runs/real-backend-smoke/summary.txt`, `runs/real-backend-smoke/otel-exporter-env.redacted.txt`, `runs/real-backend-smoke/keychain-check.redacted.txt` | Added and run without credentials: exited 78 before export, preserving redacted evidence of missing setup. |

## Local Synthetic Trace

- Run id: see `runs/local-trace-summary.json`
- Span count: 4
- Root span: `agentic_primitives.synthetic_run`
- Child spans: `session_started`, `tool_execution_started`,
  `tool_execution_completed`
- Required local attributes present: `session.id`, `service.name`,
  `langfuse.environment`

## Export Preflight

All required LangFuse env vars were missing in this shell:

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_TRACING_ENVIRONMENT`

The matching macOS Keychain service names were also absent in this environment:

- `agentic-primitives/langfuse/base-url`
- `agentic-primitives/langfuse/public-key`
- `agentic-primitives/langfuse/secret-key`
- `agentic-primitives/langfuse/tracing-environment`

See `runs/keychain-check.redacted.txt`.
