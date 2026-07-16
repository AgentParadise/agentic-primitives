# Experiment: LangFuse Trace Query CLI

## Question

Can agents query LangFuse observations for a trace through the same `itmux`
surface that exports traces, without requiring secrets in specs or committed
files?

## Hypothesis

`itmux langfuse-trace` should provide the first agent-facing read path:

1. accept either a 32-hex LangFuse trace id or an `itmux` run id;
2. derive the deterministic trace id used by the exporter when given a run id;
3. query LangFuse's bounded Observations API v2 endpoint;
4. support the legacy trace endpoint for self-hosted deployments that do not
   expose Observations API v2;
5. fail before network access with redacted missing-config JSON when
   `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, or `LANGFUSE_SECRET_KEY` is
   absent.

## Environment

- Branch: `feat/observability-exporter-primitive`
- Backend: no real LangFuse credentials in this shell
- API shape: bounded `GET /api/public/v2/observations?traceId=...`, with
  `GET /api/public/traces/{traceId}` as the explicit legacy fallback mode

## Non-Goals

- Proving real LangFuse backend queryability.
- Reconstructing a full trace tree from observation rows.
- Replacing the real backend smoke gate.
