# Experiment: LangFuse Exporter Config Fail-Fast

## Question

Can the Rust observability fanout accept a typed `langfuse_otlp` exporter config
and report missing LangFuse configuration as an explicit exporter failure
without leaking credentials or corrupting stdout JSONL?

## Hypothesis

1. `ObservabilityExporter` can round-trip a `kind = "langfuse_otlp"` config
   with only environment-variable references for credentials.
2. The generated `AgentRunSpec` JSON schema includes the `langfuse_otlp`
   exporter variant.
3. Missing LangFuse env produces an `ObservabilityExportReport` with
   `status = failed`, `kind = langfuse_otlp`, and a redacted error.
4. Endpoint and Basic auth derivation remain unit-testable without a real
   LangFuse deployment.

## Setup

- Branch: `feat/observability-exporter-primitive`.
- Prerequisite evidence:
  `experiments/2026-07-07--langfuse--otel-preflight-local-receiver`.
- This experiment does not enable real OTLP transport; it validates the config
  and fail-fast slice before the real ingestion smoke.

## Expected Signals

- targeted Cargo tests pass
- schema contains `langfuse_otlp`
- clippy/fmt stay green
- no secret values appear in failure text

## Out of Scope

- Sending OTLP payloads to LangFuse.
- Generating semantic OTLP protobuf spans.
- Trace link creation.
