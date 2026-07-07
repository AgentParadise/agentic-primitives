# Verdict

**No-go on LangFuse export in the current environment; go on local trace shape.**

The synthetic trace shape is ready for an OTLP exporter, but the actual LangFuse
ingestion question remains unanswered until a reachable LangFuse deployment and
credentials are provided. The current `itmux` exporter path is implemented and
mock-proven elsewhere; this experiment is now the real-backend close gate for
`.9`, not a prerequisite for local exporter implementation.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Synthetic root span and three child spans export through OTLP HTTP/protobuf | Local trace generated, export not attempted | partial | `runs/synthetic-trace-source.json`; missing env blocked export. |
| Trace appears in LangFuse within 60 seconds and is findable by run id | Not observed | wrong | No LangFuse config present; see `runs/langfuse-ingest-response.txt`. |
| Required attributes survive for filtering/identification | Present locally, backend preservation unverified | partial | See `runs/field-preservation-table.md`. |
| Current `itmux` exporter reports `langfuse_otlp` success against the backend | Not observed | wrong | No LangFuse config/keychain entries present in this environment. |

## Design Impact

- `.9` should not close and should not claim production LangFuse readiness until
  this smoke passes against either LangFuse Cloud or the planned Mac Mini
  self-host.
- The reusable exporter architecture remains valid for local/file export and
  mock-proven LangFuse transport, but backend-dependent trace discoverability is
  still unverified.
- The exporter should continue to fail fast with a clear config error when
  required LangFuse env vars are missing.
