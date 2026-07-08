# Verdict

**Go on local LangFuse backend export, queryability, trace-link resolution,
native Codex usage/cost/model telemetry, and Claude transcript telemetry.**

The current `itmux` exporter path was run against a real local LangFuse Docker
Compose backend on this MacBook. LangFuse accepted the OTLP HTTP/protobuf
export, the trace became discoverable through the self-host-compatible legacy
trace API, the emitted UI trace link resolved with HTTP 200, and the latest
run populated native LangFuse generation usage/cost/model fields. A separate
Claude transcript run also populated native LangFuse generation fields and tool
spans through the same exporter fanout.

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
| Token usage becomes native LangFuse usage/cost/model data, not only metadata | Observed `token_usage` as `GENERATION`, model `gpt-4o-mini`, 13 tokens, calculated total cost `0.000003299999` | correct for Codex | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`; `/tmp/langfuse-playwright/dashboard-rich.har`. |
| Claude transcript usage maps into the same backend contract | Observed two Claude `token_usage` generations, five tool-start spans, five tool-end spans, harness `claude`, provider `anthropic`, both Claude model names, 122272 total tokens, and calculated cost `0.09459785`; transcript-derived tool values are redacted in the committed evidence | correct for transcript export | `runs/claude-transcript-langfuse/langfuse-trace-query-legacy.json`; `runs/claude-transcript-langfuse/summary.txt`. |
| Completed Claude workspace runs can export useful LangFuse traces | Live `itmux run` exported 15 events; LangFuse returned 16 observations with hook spans, tool spans, one `token_usage` generation, harness `claude`, provider `anthropic`, model `claude-sonnet-4-6`, 15737 total tokens, and calculated cost `0.000234` | correct for terminalization-time collection | `runs/claude-live-itmux-run/langfuse-trace-query-legacy.json`; `runs/claude-live-itmux-run/summary.txt`. |
| Claude workspace runs can stream observed events before await ends | Live `itmux run` exported hook events and one transcript-derived `token_usage` event before the `await` phase ended; LangFuse returned 16 observations, native `GENERATION` usage, model `claude-sonnet-4-6`, 15735 total tokens, and calculated cost `0.000219` | correct for poll-time hook/transcript delta collection | `runs/claude-live-streaming-dedupe-itmux-run/event-order.json`; `runs/claude-live-streaming-dedupe-itmux-run/langfuse-trace-query-legacy.json`; `runs/claude-live-streaming-dedupe-itmux-run/summary.txt`. |
| Agents can query useful learning-loop summaries | `itmux langfuse-trace --api legacy-trace --run-id ...` reports harness, provider, model, token totals, cost, tool counts by name, tool success/failure counts, and a compact redacted tool sequence | correct for local self-host | `/tmp/langfuse-playwright/trace-rich-summary.json`; `runs/claude-transcript-langfuse/langfuse-trace-query-learning-loop.json`; `runs/claude-transcript-langfuse/learning-loop-summary.txt`. |
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
- The real backend also validated the OTEL mapping needed for useful cost
  dashboards: `token_usage` must carry GenAI usage/model attributes so LangFuse
  stores it as a `GENERATION` with native token and cost fields.
- The normalized `token_usage` event contract now has optional
  `harness`/`provider`/`model` metadata and now has both Codex and Claude
  transcript evidence against the same LangFuse backend. `itmux run` now drains
  Claude hook/transcript deltas during the await poll loop when the hook stream
  reports a `transcript_path`, with terminalization as a final safety drain.
  That path is now proven with a live Claude workspace run against LangFuse.
  Broader long-running stress coverage is still needed before treating all
  possible live Claude transcript shapes as exhausted.
- External OTLP tool spans intentionally carry redacted tool-input summaries
  instead of raw JSON. The Claude transcript path also redacts transcript-derived
  tool input/output values and omits raw transcript content from `session_log`.
  Hook event previews are also removed before fanout and OTLP hook spans carry
  selected scalar metadata instead of raw hook event JSON.
- `itmux langfuse-trace` now turns those redacted tool-span attributes into a
  machine-readable `tools` summary for learning loops: counts by tool name,
  success/failure totals, and a compact sequence sorted by observation
  timestamp/id.
- Mac Mini/VPS setup should use the same official Compose stack plus the
  agentic local override pattern: expose LangFuse web, keep backing stores
  internal unless explicitly needed.
