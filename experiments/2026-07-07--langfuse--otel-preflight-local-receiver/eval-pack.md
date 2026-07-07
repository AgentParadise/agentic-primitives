# Eval Pack

## Probe A: Existing Environment

Inspect the current shell for LangFuse/OTEL variables:

- `LANGFUSE_BASE_URL`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_TRACING_ENVIRONMENT`
- `OTEL_EXPORTER_OTLP_PROTOCOL`
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`

Capture a redacted summary in `runs/existing-env.redacted.txt`.

## Probe B: Local OTLP Receiver

Start a localhost HTTP server that records a single request and validates:

- method is `POST`
- path is `/api/public/otel/v1/traces`
- `Content-Type` includes `application/x-protobuf`
- `Authorization` is Basic auth for the configured public/secret key pair
- body is non-empty

Capture:

- `runs/local-receiver-request.json`
- `runs/local-receiver-response.txt`
- `runs/preflight-summary.json`

## Probe C: Attribute Contract

Generate a local trace config summary containing:

- `service.name`
- `deployment.environment.name`
- `langfuse.environment`
- `session.id`
- `langfuse.session.id`
- `langfuse.trace.name`
- `langfuse.trace.metadata.run_id`

Capture:

- `runs/attribute-contract.json`
- `runs/field-preservation-table.md`

## Scoring

Pass requires:

- existing env capture redacts secrets
- local receiver observes one valid OTLP-shaped request
- auth is correct without writing secret values to artifacts
- all required attributes are present in the local contract

Classify remaining failures separately:

- missing real LangFuse backend
- endpoint/auth construction failure
- attribute contract gap
- evidence redaction failure
