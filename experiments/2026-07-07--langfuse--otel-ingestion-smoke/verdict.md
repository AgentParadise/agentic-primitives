# Verdict

**Go on local LangFuse backend export, queryability, trace-link resolution,
live Codex usage/cost/model telemetry through both direct exec and
recipe-driven `itmux run --codex-mode exec`, Claude transcript/workspace
telemetry, and agent-facing feedback write-back.**

The current `itmux` exporter path was run against a real local LangFuse Docker
Compose backend on this MacBook. LangFuse accepted the OTLP HTTP/protobuf
export, the trace became discoverable through the self-host-compatible legacy
trace API, the emitted UI trace link resolved with HTTP 200, and the latest
run populated native LangFuse generation usage/cost/model fields. A live Codex
CLI run now also populates native LangFuse model, token, and cost fields
through the same exporter/query path. A separate Claude transcript run also
populated native LangFuse generation fields and tool spans through the same
exporter fanout.

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
| Live Codex runs can export useful LangFuse traces | Real `codex exec --json` via `itmux codex-exec` exported six events; LangFuse returned seven observations with harness `codex`, provider `openai`, model `gpt-5.5`, 15932 total tokens, calculated cost `0.07996`, OpenAI cache tokens preserved as metadata but not double-counted, event/tool sequences ordered by `agentic.event.seq`, and `agent_tool` vs `harness_tool` grouping | correct for live Codex exec | `runs/codex-live-real-langfuse-token-total-fixed/events.jsonl`; `runs/codex-live-real-langfuse-token-total-fixed/langfuse-trace-query-legacy.json`; `runs/codex-live-real-langfuse-token-total-fixed/summary.txt`. |
| Recipe-driven Codex runs can choose the rich observer path | Standard `itmux run --codex-mode exec` loaded a Codex recipe, invoked `codex exec --json`, fanned six normalized events to file and LangFuse exporters, and queried back one generation with harness `codex`, provider `openai`, model `gpt-5.5`, 15943 total tokens, 4992 cached input tokens, calculated cost `0.080015`, `agent_tools.codex_exec.item.agent_message`, and `harness_tools.codex_exec.thread`/`codex_exec.turn` | correct for recipe-driven Codex exec mode | `runs/codex-itmux-run-exec-mode/events.jsonl`; `runs/codex-itmux-run-exec-mode/result.json`; `runs/codex-itmux-run-exec-mode/langfuse-trace-summary.json`; `runs/codex-itmux-run-exec-mode/summary.txt`. |
| Claude transcript usage maps into the same backend contract | Observed two Claude `token_usage` generations, five tool-start spans, five tool-end spans, harness `claude`, provider `anthropic`, both Claude model names, 122272 total tokens, and calculated cost `0.09459785`; transcript-derived tool values are redacted in the committed evidence | correct for transcript export | `runs/claude-transcript-langfuse/langfuse-trace-query-legacy.json`; `runs/claude-transcript-langfuse/summary.txt`. |
| Completed Claude workspace runs can export useful LangFuse traces | Live `itmux run` exported 15 events; LangFuse returned 16 observations with hook spans, tool spans, one `token_usage` generation, harness `claude`, provider `anthropic`, model `claude-sonnet-4-6`, 15737 total tokens, and calculated cost `0.000234` | correct for terminalization-time collection | `runs/claude-live-itmux-run/langfuse-trace-query-legacy.json`; `runs/claude-live-itmux-run/summary.txt`. |
| Claude workspace runs can stream observed events before await ends | Live `itmux run` exported hook events and one transcript-derived `token_usage` event before the `await` phase ended; LangFuse returned 16 observations, native `GENERATION` usage, model `claude-sonnet-4-6`, 15735 total tokens, and calculated cost `0.000219` | correct for poll-time hook/transcript delta collection | `runs/claude-live-streaming-dedupe-itmux-run/event-order.json`; `runs/claude-live-streaming-dedupe-itmux-run/langfuse-trace-query-legacy.json`; `runs/claude-live-streaming-dedupe-itmux-run/summary.txt`. |
| Live Claude tool use appears as queryable agent tools | Real Claude `itmux run` used Bash; LangFuse returned 21 observations with `agent_tools.Bash`, hook tool execution events, two `token_usage` generations, model `claude-sonnet-4-6`, 31789 total tokens, calculated cost `0.001767`, and success after normal `agent_stopped` ended await | correct for live Claude tool use | `runs/claude-live-agent-tool-itmux-run/events.jsonl`; `runs/claude-live-agent-tool-itmux-run/event-order.json`; `runs/claude-live-agent-tool-itmux-run/langfuse-trace-query-legacy.json`; `runs/claude-live-agent-tool-itmux-run/summary.txt`. |
| Agents can query useful learning-loop summaries | `itmux langfuse-trace --api legacy-trace --run-id ...` reports harness, provider, model, token totals, cost, tool counts by name, tool success/failure counts, a compact redacted tool sequence, a compact full event sequence ordered by `agentic.event.seq`, and separate `operations`, `agent_tools`, and `harness_tools` groups | correct for local self-host | `/tmp/langfuse-playwright/trace-rich-summary.json`; `runs/claude-transcript-langfuse/langfuse-trace-query-learning-loop.json`; `runs/claude-transcript-langfuse/learning-loop-summary.txt`; `runs/claude-live-streaming-dedupe-itmux-run/langfuse-trace-query-legacy.json`; `runs/codex-live-real-langfuse-token-total-fixed/langfuse-trace-query-legacy.json`. |
| Agents can query trace summaries through MCP tools | The observability plugin MCP server handled a framed `tools/call` for `agentic_langfuse_trace_summary`, delegated to `itmux langfuse-trace --output summary`, and returned `isError=false` plus the compact summary for Codex run `run-88868068` with harness/provider/model, tokens, and cost | correct for local self-host | `plugins/observability/mcp/langfuse_server.py`; `runs/langfuse-mcp-trace-query/response.json`; `runs/langfuse-mcp-trace-query/summary.json`; `runs/langfuse-mcp-trace-query/summary.txt`. |
| Agents can request aggregate MCP retrospectives across recent runs | `agentic_langfuse_learning_loop_report` discovered and drilled into two Codex traces and two Claude traces, returning aggregate harness/provider/model, generation counts, token totals, calculated costs, agent-tool outcomes, and score counts. A real backend run exposed overbroad score rows; the CLI and MCP report now filter score rows client-side by trace id before presenting feedback to agents. | correct for local self-host | `runs/langfuse-mcp-learning-loop-report/summary.json`; `runs/langfuse-mcp-learning-loop-report/codex-summary.json`; `runs/langfuse-mcp-learning-loop-report/claude-summary.json`; `runs/langfuse-mcp-learning-loop-report/summary.txt`. |
| Agents can request actionable MCP learning-loop recommendations | `agentic_langfuse_learning_loop_report` with `include_insights=true` queried recent Codex and Claude traces through the MCP server and returned cost/token hotspots plus missing-feedback recommendations. Codex returned 2 traces, 31875 tokens, `$0.159975`, model `gpt-5.5`, one unscored trace, and no failed agent tools. Claude returned 2 traces, 47526 tokens, `$0.0020009999999999997`, model `claude-sonnet-4-6`, two unscored traces, and no failed agent tools. | correct for local self-host | `runs/langfuse-mcp-learning-loop-insights/summary.json`; `runs/langfuse-mcp-learning-loop-insights/codex-summary.json`; `runs/langfuse-mcp-learning-loop-insights/claude-summary.json`; `runs/langfuse-mcp-learning-loop-insights/summary.txt`. |
| Agents can request compact query output | `itmux langfuse-trace --api legacy-trace --output summary --run-id ...` queried both live Codex and Claude traces without explicit time-window arguments and returned only `{ok, request, summary}`; no raw backend `response` key was present | correct for local self-host | `runs/langfuse-trace-compact-summary/codex-summary.json`; `runs/langfuse-trace-compact-summary/claude-summary.json`; `runs/langfuse-trace-compact-summary/summary.txt`. |
| Agents can discover recent traces | `itmux langfuse-traces` listed recent traces with run ids, harness/provider/model, costs, observation counts, environment, pagination metadata, and no raw backend `response`; `--harness codex` and `--harness claude` produced filtered discovery views | correct for local self-host | `runs/langfuse-traces-discovery/recent-summary.json`; `runs/langfuse-traces-discovery/codex-summary.json`; `runs/langfuse-traces-discovery/claude-summary.json`; `runs/langfuse-traces-discovery/summary.txt`. |
| Agents can write and read feedback scores | `itmux langfuse-score` created a boolean `agentic.learning_loop_probe` score on live Codex run `run-f7ae62c8`; `itmux langfuse-scores` read the same score back by run id, score id, name, and data type, including trace tags and environment | correct for local self-host | `runs/langfuse-score-feedback/create-score.json`; `runs/langfuse-score-feedback/itmux-langfuse-scores-summary.json`. |
| Agents can inspect trace telemetry and feedback together | `itmux langfuse-trace --include-scores --output summary --run-id run-f7ae62c8` returned the Codex trace summary and its attached `agentic.learning_loop_probe` score in one compact payload with no raw backend `response` | correct for local self-host | `runs/langfuse-trace-with-scores/codex-trace-with-scores-summary.json`; `runs/langfuse-trace-with-scores/summary.txt`. |
| Agents can attribute cost at the generation level | `itmux langfuse-trace --output summary` returned `generations.by_model` and ordered `generations.sequence` entries with split input/output costs, total costs, cached input tokens, pricing tier, model id, harness, and provider for both live Codex and Claude traces | correct for local self-host | `runs/langfuse-generation-breakdown/codex-generation-summary.json`; `runs/langfuse-generation-breakdown/claude-generation-summary.json`; `runs/langfuse-generation-breakdown/summary.txt`. |
| Live Claude message usage is not double-counted with terminal result rollups | A fresh Claude `itmux run` after the review fix exported 15 events and queried back as exactly one `claude-sonnet-4-6` generation with 15737 total tokens and total cost `0.000234` | correct for local self-host | `runs/claude-live-generation-dedupe-fixed/events.jsonl`; `runs/claude-live-generation-dedupe-fixed/langfuse-trace-summary.json`; `runs/claude-live-generation-dedupe-fixed/summary.txt`. |
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
  evidence against the same LangFuse backend. For Codex, `itmux codex-exec`
  and `itmux run --codex-mode exec` both use the `codex exec --json` observer;
  the recipe-driven mode strips an `openai/` recipe prefix before passing the
  model to Codex. Direct `itmux codex-exec` annotates token usage with an
  explicit `--model` when supplied, else `CODEX_MODEL`, else top-level Codex
  config `model`, which makes LangFuse cost/model fields queryable for
  default-account runs without changing the Codex execution model. The OTLP
  exporter now computes provider-aware total
  tokens: OpenAI/Codex cached and reasoning fields are emitted as metadata but
  not added to the native total, while Anthropic/Claude cache fields remain
  additive. `itmux run` now drains Claude hook/transcript deltas
  during the await poll loop when the hook stream reports a `transcript_path`,
  with terminalization as a final safety drain. A normal Claude `agent_stopped`
  hook now ends the await loop after delta drain, which prevents tool-using
  sessions from waiting on a stale TUI readiness heuristic after the agent has
  already stopped. That path is now proven with live Claude workspace runs
  against LangFuse, including one live Bash tool invocation. Broader
  long-running stress coverage is still needed before treating all possible
  live Claude transcript shapes as exhausted.
- External OTLP tool spans intentionally carry redacted tool-input summaries
  instead of raw JSON. The Claude transcript path also redacts transcript-derived
  tool input/output values and omits raw transcript content from `session_log`.
  Hook event previews are also removed before fanout and OTLP hook spans carry
  selected scalar metadata instead of raw hook event JSON.
- `itmux langfuse-trace` now turns those redacted tool-span attributes into a
  machine-readable `tools` summary for learning loops: counts by tool name,
  success/failure totals, and a compact sequence sorted by `agentic.event.seq`
  when present. It also emits a compact `events.sequence` for the whole run so
  agents can reconstruct chronology across lifecycle, tool, usage, and session
  end observations. The query summary now separates driver lifecycle
  `operations`, harness plumbing under `harness_tools`, and agent-visible work
  under `agent_tools`, while keeping the legacy aggregate `tools` view. Agents
  can now pass `--output summary` to avoid returning the raw LangFuse backend
  payload, and trace queries have default bounded start-time windows so a run-id
  lookup does not require extra time-window arguments. `itmux langfuse-traces`
  now gives agents a discovery step before single-trace drilldown, returning
  recent run ids with harness/provider/model, cost, observation counts, and
  optional harness/provider/model/environment filters. Agents can also write
  trace-scoped learning-loop feedback with `itmux langfuse-score` and retrieve
  it with `itmux langfuse-scores`, allowing post-run evaluators to attach
  durable API scores to the same traces they inspect. `itmux langfuse-trace
  --include-scores` combines the trace summary and trace-scoped feedback scores
  in one compact query payload for retrospectives. Compact trace summaries also
  include a `generations` section with model-grouped and ordered per-call
  usage/cost records, which lets agents distinguish aggregate trace spend from
  per-model/per-call input, output, cached-token, and total costs for both
  Codex and Claude. The MCP server now exposes
  `agentic_langfuse_learning_loop_report` as the higher-level agent entry point
  when the agent does not already know a specific run id: it discovers recent
  traces, drills into the top rows, and returns aggregate cost/token/tool/score
  rollups across Codex or Claude traces. Real backend testing found that score
  query responses can be broader than requested, so both the CLI summary and
  MCP report filter score rows client-side by trace id/name/id/type before
  surfacing feedback to agents. The MCP learning-loop report now also emits
  default `insights` with cost/token hotspots, missing token/cost/model
  coverage, unscored traces, and failed agent-tool recommendations; real local
  backend evidence covers both Codex and Claude harness filters. Reviewer
  follow-up tightened that contract by
  avoiding duplicate Claude live usage when message-level usage and terminal
  cumulative result usage are both present, ignoring non-generation spans that
  merely mirror token totals, and failing `itmux langfuse-trace` on malformed
  backend JSON instead of returning a successful empty trace.
- Mac Mini/VPS setup should use the same official Compose stack plus the
  agentic local override pattern: expose LangFuse web, keep backing stores
  internal unless explicitly needed.
