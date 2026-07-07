# Verdict

**Go on local LangFuse backend export, queryability, and trace-link resolution.**

The current `itmux` exporter path was run against a real local LangFuse Docker
Compose backend on this MacBook. LangFuse accepted the OTLP HTTP/protobuf
export, the trace became discoverable through the self-host-compatible legacy
trace API, and the emitted UI trace link resolved with HTTP 200.

`run-smoke.sh` is now the repeatable close-gate runner for the current exporter
path. `scripts/langfuse-local.sh smoke` seeds local LangFuse env from the
ignored `.agentic/langfuse/langfuse/.env`, exports the current `itmux`
observability path, polls for backend queryability, and records trace-link
evidence under `runs/real-backend-smoke/`.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Synthetic root span and three child spans export through OTLP HTTP/protobuf | Current `itmux` smoke exported root + six event spans | correct | `runs/real-backend-smoke/result.json`; `events_exported=6`. |
| Trace appears in LangFuse within 60 seconds and is findable by run id | Legacy trace query succeeded after 2 attempts | correct | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`; `observation_count=7`. |
| Required attributes survive for filtering/identification | Tool, usage, session, resource, and environment attributes are present in backend response | correct | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`. |
| Current `itmux` exporter reports `langfuse_otlp` success against the backend | Observed `status=ok`, `events_exported=6`, one trace link | correct | `runs/real-backend-smoke/summary.txt`. |
| Repeatable runner captures the current setup state without leaking secrets | Redacted env/keychain evidence captured; local ignored env is not committed | correct | `run-smoke.sh`; `scripts/langfuse-local.sh`; `.agentic/` ignored. |

## Design Impact

- `.9` now has real local-backend evidence for export acceptance,
  backend queryability, and trace-link resolution.
- LangFuse v3 Docker Compose returns 404 for Observations API v2 because that
  path requires v4 write mode. The `itmux langfuse-trace --api legacy-trace`
  compatibility path is required for this v3 self-host stack.
- The real backend revealed and validated a root-span timestamp fix: root spans
  must inherit the first run event timestamp instead of defaulting to Unix
  epoch.
- Mac Mini/VPS setup should use the same official Compose stack plus the
  agentic local override pattern: expose LangFuse web, keep backing stores
  internal unless explicitly needed.
