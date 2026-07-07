# Results

| Probe | Evidence | Result |
|---|---|---|
| Existing environment | `runs/existing-env.redacted.txt` | Real LangFuse export cannot run in this shell: all required LangFuse/OTEL env vars are missing. |
| Mock OTLP receiver | `runs/mock-request.json`, `runs/mock-response.txt`, `runs/preflight-summary.json` | Passed: local receiver saw one `POST` to `/api/public/otel/v1/traces`, `Content-Type: application/x-protobuf`, valid Basic auth, and non-empty body. |
| Attribute contract | `runs/attribute-contract.json`, `runs/field-preservation-table.md` | Passed: all required local attributes were present. |

## Key Data

| Field | Value |
|---|---|
| Mock response status | 200 |
| Method | `POST` |
| Path | `/api/public/otel/v1/traces` |
| Content type | `application/x-protobuf` |
| Auth scheme | `Basic` |
| Auth matched expected synthetic credentials | true |
| Body non-empty | true |
| Evidence redaction | true |
| Missing real env | `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_TRACING_ENVIRONMENT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` |

## Required Attributes

- `service.name`
- `deployment.environment.name`
- `langfuse.environment`
- `session.id`
- `langfuse.session.id`
- `langfuse.trace.name`
- `langfuse.trace.metadata.run_id`

## Classification

Local OTLP preflight validates endpoint/auth/header/attribute construction for
the `.9` exporter. Real LangFuse ingestion and trace discoverability remain
unproven until a reachable LangFuse deployment and credentials are available.
