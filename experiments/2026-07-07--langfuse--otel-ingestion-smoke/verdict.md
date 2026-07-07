# Verdict

**No-go on LangFuse export in the current environment; go on local trace shape.**

The synthetic trace shape is ready for an OTLP exporter, but the actual LangFuse
ingestion question remains unanswered until a reachable LangFuse deployment and
credentials are provided.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Synthetic root span and three child spans export through OTLP HTTP/protobuf | Local trace generated, export not attempted | partial | `runs/synthetic-trace-source.json`; missing env blocked export. |
| Trace appears in LangFuse within 60 seconds and is findable by run id | Not observed | wrong | No LangFuse config present; see `runs/langfuse-ingest-response.txt`. |
| Required attributes survive for filtering/identification | Present locally, backend preservation unverified | partial | See `runs/field-preservation-table.md`. |

## Design Impact

- `.9` should not proceed to run-event mapping until this smoke passes against
  either LangFuse Cloud or the planned Mac Mini self-host.
- The exporter should fail fast with a clear config error when required
  LangFuse/OTEL env vars are missing.
