# Verdict

**Go for `.9` exporter config/preflight implementation; no-go for claiming
LangFuse ingestion.**

The local mock receiver proves the exporter can deterministically construct the
LangFuse OTLP traces request shape and preserve the required local attributes
without leaking credentials. It does not prove LangFuse accepts the protobuf
payload or that traces are visible/queryable in LangFuse.

## Hypothesis Scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Endpoint derivation is deterministic | Mock receiver saw `/api/public/otel/v1/traces` | correct | `runs/mock-request.json` |
| Request shape matches OTLP HTTP/protobuf expectations | POST, `application/x-protobuf`, Basic auth, non-empty body | correct | `runs/preflight-summary.json` |
| Required attributes are present locally | All seven required attributes emitted | correct | `runs/attribute-contract.json` |
| Evidence is redacted | Authorization value and synthetic keys are not written to request summary | correct | `runs/mock-request.json` |

## Design Impact

- `.9` can implement fail-fast config validation and OTLP HTTP/protobuf request
  construction before a durable Mac Mini LangFuse deployment exists.
- `.9` still must run `experiments/2026-07-07--langfuse--otel-ingestion-smoke`
  against real LangFuse before run-event span mapping is considered complete.
- The first LangFuse exporter should report missing env as an exporter config
  failure in `ObservabilityBundle`, not as a silent no-op and not by corrupting
  stdout JSONL.
