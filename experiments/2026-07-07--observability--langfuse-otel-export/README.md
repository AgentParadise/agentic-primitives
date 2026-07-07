# Experiment: LangFuse OTEL Export

## Question

Can normalized `itmux run` observability events be exported to a LangFuse
project as a usable trace through an OTEL/LangFuse exporter?

## Hypothesis

1. A configured LangFuse/OTEL exporter can create one trace per `itmux run`.
2. The trace will contain child observations for run phases such as provision,
   launch, submit, await, and capture.
3. The final `AgentRunResult.observability` report will include a LangFuse trace
   link suitable for humans and future agents.

## Setup

- Branch: `feat/observability-exporter-primitive` plus the LangFuse exporter work.
- Beads: `.6` must remain complete enough to provide fanout; `.9` owns the
  LangFuse backend.
- Prerequisite experiment:
  `experiments/2026-07-07--langfuse--otel-ingestion-smoke` must prove OTLP
  HTTP/protobuf ingestion and trace discoverability before this run-event
  mapping experiment executes.
- LangFuse target: any reachable LangFuse base URL during the probe; expected
  production target is a self-hosted Mac Mini deployment.
- Credentials: provided through env/keychain-backed injection, never committed.

Expected env vars:

```bash
LANGFUSE_BASE_URL=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=$LANGFUSE_BASE_URL/api/public/otel
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=$LANGFUSE_BASE_URL/api/public/otel/v1/traces
```

## Conditions

- **Baseline:** file exporter only.
- **Treatment:** file exporter plus LangFuse/OTEL exporter.

## Expected Signals

- local event JSONL artifact
- local result JSON with exporter report
- LangFuse trace URL
- evidence that the trace contains run phase observations

## Out of Scope

- LangFuse self-hosting automation.
- Long-term retention policy.
- Agent trace-query integration beyond validating a linkable trace exists.
