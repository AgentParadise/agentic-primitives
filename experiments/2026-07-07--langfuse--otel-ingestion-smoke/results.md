# Results

| Probe | Evidence | Result |
|---|---|---|
| Local synthetic trace | `runs/synthetic-trace-source.json`, `runs/local-trace-summary.json` | Generated one root span plus three child spans with required local attributes. |
| LangFuse OTLP export | `runs/real-backend-smoke/summary.txt`, `runs/real-backend-smoke/result.json`, `runs/real-backend-smoke/events.jsonl` | Passed against local LangFuse Docker Compose: exporter status `ok`, `events_exported=6`, trace link emitted. |
| Trace queryability | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `runs/real-backend-smoke/langfuse-trace-query-v2.json` | Passed through `itmux langfuse-trace --api legacy-trace`: trace returned with 7 observations. Observations v2 returns 404 on LangFuse v3 Docker Compose because it requires v4 write mode. |
| Trace UI link | `runs/real-backend-smoke/trace-ui-response.txt`, `runs/real-backend-smoke/trace-ui.html` | Passed: trace URL returned HTTP 200. |
| Native usage/cost/model fields | `runs/real-backend-smoke/summary.txt`, `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `/tmp/langfuse-playwright/dashboard-rich.har` | Passed: LangFuse classified `token_usage` as a `GENERATION`, set `model=gpt-4o-mini`, recorded 13 tokens, calculated `$0.000003299999`, and dashboard cost/model queries returned non-null values. |
| Live Codex exec export | `runs/codex-live-real-langfuse-token-total-fixed/summary.txt`, `runs/codex-live-real-langfuse-token-total-fixed/events.jsonl`, `runs/codex-live-real-langfuse-token-total-fixed/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose with the real Codex CLI: model `gpt-5.5`, harness `codex`, provider `openai`, 15932 total tokens, calculated cost `0.07996`, OpenAI cache tokens preserved as metadata but not double-counted, event/tool sequences ordered by `agentic.event.seq`, and `agent_tool` vs `harness_tool` grouping. |
| Agent-facing trace summary | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `/tmp/langfuse-playwright/trace-rich-summary.json`, `runs/claude-transcript-langfuse/langfuse-trace-query-learning-loop.json`, `runs/claude-transcript-langfuse/learning-loop-summary.txt`, `runs/codex-live-real-langfuse-token-total-fixed/langfuse-trace-query-legacy.json`, `runs/claude-live-agent-tool-itmux-run/langfuse-trace-query-legacy.json` | Passed: `itmux langfuse-trace --api legacy-trace --run-id ...` reports harness/provider/model/token/cost summary fields, a redacted tool-call summary, a compact full event sequence, and separate `operations`, `agent_tools`, and `harness_tools` groups for learning loops. |
| Compact agent query mode | `runs/langfuse-trace-compact-summary/summary.txt`, `runs/langfuse-trace-compact-summary/codex-summary.json`, `runs/langfuse-trace-compact-summary/claude-summary.json` | Passed against local LangFuse Docker Compose: `itmux langfuse-trace --api legacy-trace --output summary --run-id ...` works without explicit time bounds, omits the raw backend `response`, and returns the learning-loop summary for both Codex and Claude traces. |
| Trace discovery mode | `runs/langfuse-traces-discovery/summary.txt`, `runs/langfuse-traces-discovery/recent-summary.json`, `runs/langfuse-traces-discovery/codex-summary.json`, `runs/langfuse-traces-discovery/claude-summary.json` | Passed against local LangFuse Docker Compose: `itmux langfuse-traces` lists recent traces without raw backend `response`, reports run ids, harness/provider/model, cost, observation counts, and supports harness filtering for Codex vs Claude. |
| Feedback write-back | `runs/langfuse-score-feedback/create-score.json`, `runs/langfuse-score-feedback/itmux-langfuse-scores-summary.json` | Passed against local LangFuse Docker Compose: `itmux langfuse-score` created a boolean score on the live Codex trace, and `itmux langfuse-scores` read it back by run id, score id, name, and data type with trace environment/tags. |
| Claude transcript export | `runs/claude-transcript-langfuse/summary.txt`, `runs/claude-transcript-langfuse/events.jsonl`, `runs/claude-transcript-langfuse/result.json`, `runs/claude-transcript-langfuse/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose: Claude transcript tool use became spans, model usage became `GENERATION` observations, and the agent-facing summary reports harness `claude`, provider `anthropic`, both Claude model names, token totals, and calculated cost. |
| Live Claude `itmux run` export | `runs/claude-live-itmux-run/summary.txt`, `runs/claude-live-itmux-run/events.jsonl`, `runs/claude-live-itmux-run/result.json`, `runs/claude-live-itmux-run/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose: a real Claude workspace run exported hooks, transcript-derived tool spans, transcript-derived token usage, and LangFuse classified usage as `GENERATION` with model `claude-sonnet-4-6`, token totals, and calculated cost. |
| Live Claude poll-time streaming | `runs/claude-live-streaming-dedupe-itmux-run/summary.txt`, `runs/claude-live-streaming-dedupe-itmux-run/event-order.json`, `runs/claude-live-streaming-dedupe-itmux-run/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose: hook and transcript-derived token usage events streamed before `await` ended, message-level usage was deduplicated to one event, and LangFuse classified usage as `GENERATION` with model, token totals, and calculated cost. |
| Live Claude agent tool export | `runs/claude-live-agent-tool-itmux-run/summary.txt`, `runs/claude-live-agent-tool-itmux-run/event-order.json`, `runs/claude-live-agent-tool-itmux-run/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose: a real Claude workspace run used Bash, exported live hook tool execution events plus transcript-derived Bash `agent_tools`, emitted two usage generations, ended await from the normal `agent_stopped` hook, and returned success. |
| Repeatable real-backend runner | `run-smoke.sh`, `runs/real-backend-smoke/summary.txt`, `scripts/langfuse-local.sh` | Passed through `scripts/langfuse-local.sh smoke` using the ignored local Compose override/env generated under `.agentic/langfuse/`. |

## Local Synthetic Trace

- Run id: see `runs/local-trace-summary.json`
- Span count: 4
- Root span: `agentic_primitives.synthetic_run`
- Child spans: `session_started`, `tool_execution_started`,
  `tool_execution_completed`
- Required local attributes present: `session.id`, `service.name`,
  `langfuse.environment`

## Real Backend Smoke

The local Docker Compose LangFuse backend accepted the current `itmux`
exporter path.

Current key evidence from `runs/real-backend-smoke/summary.txt`:

- Run id: `run-08ac78b8`
- Trace id: `a7d70dbd4b8024793804ebf8a7b35050`
- Exporter status: `ok`
- Events exported: `6`
- Legacy trace-query exit: `0`
- Backend observation count: `7`
- Root span start time: `2026-07-08T01:12:42.000Z`
- Model names: `gpt-4o-mini`
- Native token count: `13`
- Calculated total cost: `3.299999e-06`
- Harness values: `codex`
- Trace UI status: `200`

The root span timestamp is important empirical feedback from the real backend:
an earlier run showed the root span at Unix epoch. The exporter now timestamps
the root span from the first normalized run event.

The cost/model fields are also important empirical feedback. Earlier backend
runs showed token counts only as custom `agentic.*` metadata, which left the
LangFuse cost dashboard blank. The exporter now emits GenAI OTEL usage/model
attributes for `token_usage` events. LangFuse v3 maps those observations to
native `GENERATION` rows with `promptTokens`, `completionTokens`,
`totalTokens`, `model`, `costDetails`, and `calculatedTotalCost`.

## Claude Transcript Smoke

The same local Docker Compose LangFuse backend accepted normalized Claude
transcript telemetry through `itmux claude-transcript`.

Current key evidence from `runs/claude-transcript-langfuse/summary.txt`:

- Run id: `run-claude-fixture-redacted`
- Trace id: `78568acaeec8a7753be1d3228546d9a6`
- Exporter status: `ok`
- Events exported: `13`
- Backend observation count: `14`
- Observation types: `GENERATION`, `SPAN`
- Model names: `claude-haiku-4-5-20251001`,
  `claude-sonnet-4-5-20250929`
- Native input tokens: `1348`
- Native output tokens: `2218`
- Native total tokens: `122272`
- Calculated total cost: `0.09459785`
- Harness values: `claude`
- Provider values: `anthropic`

The Claude transcript path maps assistant `tool_use` items to `tool_start`,
user `tool_result` items to `tool_end`, and transcript `result.modelUsage`
entries to the shared `token_usage` contract. LangFuse classifies the usage
observations as native generations with model, token, and cost fields. This
proves the reusable exporter contract for Claude-shaped transcript data. The
committed evidence is redacted: tool input values preserve only shape metadata,
tool result content is summarized by length, and `result.json` omits the raw
transcript from `session_log`.

After this backend smoke, `itmux run` was wired to drain Claude transcript files
when the Claude hook stream reports a `transcript_path`. Unit evidence now
covers hook-path extraction, redacted transcript normalization, and
`result.modelUsage` availability through the workspace-run path.

## Learning-Loop Query Shape

The agent-facing `itmux langfuse-trace` summary now includes a deterministic,
redacted tool-call summary derived from LangFuse observation metadata. Current
evidence from `runs/claude-transcript-langfuse/learning-loop-summary.txt`:

- Trace id: `78568acaeec8a7753be1d3228546d9a6`
- Harness/provider: `claude` / `anthropic`
- Models: `claude-haiku-4-5-20251001`,
  `claude-sonnet-4-5-20250929`
- Total tokens: `122272`
- Calculated total cost: `0.09459785`
- Tool starts: `5`
- Tool ends: `5`
- Tool successes: `5`
- Tool failures: `0`
- Tool names: `Bash`, `TodoWrite`, `Write`

The full JSON summary in
`runs/claude-transcript-langfuse/langfuse-trace-query-learning-loop.json`
includes `tools.by_name` counts, a compact `tools.sequence`, and a compact
run-level `events.sequence` sorted by `agentic.event.seq` when present, with
observation timestamp/id only as a fallback for older traces. It also separates
the legacy `tools` view into `operations` for driver lifecycle phases,
`agent_tools` for harness-observed agent work, and `harness_tools` for harness
plumbing such as Codex thread/turn events. Tool inputs and outputs remain
redacted in the underlying observations.

For agent learning loops that do not need the raw LangFuse trace payload,
`itmux langfuse-trace --output summary` returns only `{ok, request, summary}`.
The command now defaults its bounded query window to
`2020-01-01T00:00:00Z..2100-01-01T00:00:00Z`, so agents can query by run id
without carrying time-window arguments. Current evidence from
`runs/langfuse-trace-compact-summary/summary.txt`:

- Codex command:
  `itmux langfuse-trace --api legacy-trace --output summary --run-id run-f7ae62c8`
- Codex result: no raw `response`, harness `codex`, total tokens `15932`,
  calculated cost `0.07996`, agent tool `codex_exec.item.agent_message`
- Claude command:
  `itmux langfuse-trace --api legacy-trace --output summary --run-id run-f07cba88`
- Claude result: no raw `response`, harness `claude`, total tokens `31789`,
  calculated cost `0.001767`, agent tool `Bash`

Agents can discover candidate runs before drilling into a single trace with
`itmux langfuse-traces`. Current evidence from
`runs/langfuse-traces-discovery/summary.txt`:

- Recent command: `itmux langfuse-traces --limit 5`
- Recent result: no raw `response`, 5 traces returned out of 17 backend traces,
  harnesses `claude,codex`, aggregate listed cost `0.16830399999900003`, run ids
  `run-f7ae62c8,run-f07cba88,run-2e3c7c48,run-40ceea48,run-00411d68`
- Codex filter: `itmux langfuse-traces --limit 10 --harness codex` returned 3
  Codex traces; first run `run-f7ae62c8`, cost `0.07996`
- Claude filter: `itmux langfuse-traces --limit 10 --harness claude` returned
  6 Claude traces; first run `run-f07cba88`, cost `0.001767`

Agents can also write learning-loop feedback back to LangFuse with
`itmux langfuse-score` and read it with `itmux langfuse-scores`. Current
evidence from `runs/langfuse-score-feedback/`:

- Write command: `itmux langfuse-score --run-id run-f7ae62c8 --score-id agentic-learning-loop-probe-run-f7ae62c8 --name agentic.learning_loop_probe --value 1 --data-type boolean`
- Write result: score id `agentic-learning-loop-probe-run-f7ae62c8`, trace id
  `fe7564993ed4fa5634428123b0f44ccf`, data type `BOOLEAN`, created `true`
- Read command: `itmux langfuse-scores --run-id run-f7ae62c8 --score-ids agentic-learning-loop-probe-run-f7ae62c8 --name agentic.learning_loop_probe --data-type boolean`
- Read result: one score returned with value `1`, string value `True`,
  source `API`, score environment `local`, trace environment `local-macbook`,
  and trace tags `agentic-primitives`, `harness:codex`, `itmux`

## Live Codex Exec Smoke

The local Docker Compose LangFuse backend accepted a real `codex exec --json`
run through `itmux codex-exec` after the CLI resolved the effective Codex
model from the user's Codex config for telemetry annotation.

Current key evidence from
`runs/codex-live-real-langfuse-token-total-fixed/summary.txt`:

- Run id: `run-f7ae62c8`
- Trace id: `fe7564993ed4fa5634428123b0f44ccf`
- Exporter status: `ok`
- Events exported: `6`
- Backend observation count: `7`
- Event types: `session_end`, `token_usage`, `tool_end`, `tool_start`
- Event sequence source: `agentic.event.seq`
- Event sequence seqs: `0,1,2,3,4,5`
- Tool sequence source: `agentic.event.seq`
- Tool sequence seqs: `0,1,2,3`
- Event categories: `agent_tool:1`, `harness_tool:3`, `root:1`, `session:1`,
  `usage:1`
- Agent tool names: `codex_exec.item.agent_message`
- Harness tool names: `codex_exec.thread`, `codex_exec.turn`
- Model names: `gpt-5.5`
- Native input tokens: `15920`
- Native output tokens: `12`
- Native total tokens: `15932`
- Calculated total cost: `0.07996`
- Harness values: `codex`
- Provider values: `openai`

The first live default-model run showed the exporter could reach LangFuse but
left LangFuse cost/model fields empty because Codex's JSON stream reports usage
without the model name. `itmux codex-exec` now annotates usage with an explicit
`--model` when supplied, else `CODEX_MODEL`, else top-level
`CODEX_HOME/config.toml` or `~/.codex/config.toml` `model`. This only annotates
telemetry; it does not change the model passed to Codex unless `--model` is
explicitly supplied.

An independent PR review also caught that OpenAI/Codex `cached_input_tokens`
and `reasoning_output_tokens` are breakdown fields rather than additive totals.
The exporter now uses provider-aware token totals: OpenAI totals are
`input_tokens + output_tokens`, while Anthropic totals keep cache fields
additive. The corrected live Codex run above proves LangFuse now reports
`15920 + 12 = 15932` total tokens while preserving `cached_input_tokens=9600`
as metadata.

## Live Claude Workspace Smoke

The local Docker Compose LangFuse backend also accepted a real recipe-driven
Claude `itmux run` after the terminalization drain was wired.

Current key evidence from `runs/claude-live-itmux-run/summary.txt`:

- Run id: `run-0b3f4760`
- Trace id: `8603e096fe56957c7683d7114499702d`
- Exporter status: `ok`
- Events exported: `15`
- Backend observation count: `16`
- Observation types: `GENERATION`, `SPAN`
- Event names: hook events, `tool_start`, `tool_end`, `token_usage`,
  `session_end`
- Model names: `claude-sonnet-4-6`
- Native input tokens: `3`
- Native output tokens: `15`
- Native total tokens: `15737`
- Calculated total cost: `0.000234`
- Harness values: `claude`
- Provider values: `anthropic`

The first live attempt exposed two useful misses: live Claude transcript lines
can use string `message.content`, and parse errors could leak that string if
they were forwarded verbatim. The parser now treats string content as valid but
non-observable content, redacts parse-error summaries, and enables
assistant-message usage only for the workspace-run drain path. The committed
live evidence has its pane `session_log` redacted and scans clean for the prompt
text, hook preview fields, auth headers, and secret-like test strings.

## Live Claude Agent Tool Smoke

The local Docker Compose LangFuse backend accepted a real Claude workspace run
that used Bash during the session. The first attempt captured all useful
telemetry but timed out because the TUI readiness heuristic did not settle even
after the hook stream reported `agent_stopped` with `reason=normal`. The
workspace executor now treats that hook as an await completion signal after
draining hook/transcript deltas, so tool-using live runs can finish cleanly.

Current key evidence from
`runs/claude-live-agent-tool-itmux-run/summary.txt`:

- Run id: `run-f07cba88`
- Trace id: `ca9adeba40ddbc919e94aec818894214`
- Exit code: `0`
- Exporter status: `ok`
- Events exported: `20`
- Backend observation count: `21`
- Observed events before `await` ended: `16`
- Token usage events: `2`
- Event categories: `agent_tool:2`, `hook:5`, `operation:10`, `root:1`,
  `session:1`, `usage:2`
- Operation names: `await`, `capture`, `launch`, `provision`, `submit`
- Agent tool names: `Bash`
- Model names: `claude-sonnet-4-6`
- Native total tokens: `31789`
- Calculated total cost: `0.001767`
- Harness values: `claude`
- Provider values: `anthropic`

The evidence includes both hook-level tool execution events
(`tool_execution_started`, `tool_execution_completed`) and transcript-derived
`agent_tools.Bash` start/end spans. Tool input/output values are redacted in the
committed JSONL and LangFuse query artifacts; `result.json` keeps the pane
transcript redacted.

## Live Claude Poll-Time Streaming Smoke

The local Docker Compose LangFuse backend also accepted a real Claude run with
poll-time hook/transcript delta draining enabled.

Current key evidence from
`runs/claude-live-streaming-dedupe-itmux-run/summary.txt`:

- Run id: `run-ab55ce30`
- Trace id: `93268b3ab949a092fc5131ab224367ef`
- Events exported: `15`
- Backend observation count: `16`
- Observed events before `await` ended: `4`
- Token usage events: `1`
- Tool sequence source: `agentic.event.seq`
- Tool sequence seqs: `0,1,2,3,4,5,6,11,12,13`
- Observation types: `GENERATION`, `SPAN`
- Model names: `claude-sonnet-4-6`
- Native input tokens: `3`
- Native output tokens: `14`
- Native total tokens: `15735`
- Calculated total cost: `0.000219`
- Harness values: `claude`
- Provider values: `anthropic`

The event-order evidence shows `session_started`, `user_prompt_submitted`,
`agent_stopped`, and one transcript-derived `token_usage` event emitted before
the `await` phase ended. A longer exploratory run exposed duplicate
message-level usage during live transcript polling; the observer now
deduplicates assistant message usage by message id, with a conservative usage
fingerprint fallback. The short smoke confirms one token usage event for the
live run.
