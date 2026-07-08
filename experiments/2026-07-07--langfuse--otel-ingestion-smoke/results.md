# Results

| Probe | Evidence | Result |
|---|---|---|
| Local synthetic trace | `runs/synthetic-trace-source.json`, `runs/local-trace-summary.json` | Generated one root span plus three child spans with required local attributes. |
| LangFuse OTLP export | `runs/real-backend-smoke/summary.txt`, `runs/real-backend-smoke/result.json`, `runs/real-backend-smoke/events.jsonl` | Passed against local LangFuse Docker Compose: exporter status `ok`, `events_exported=6`, trace link emitted. |
| Trace queryability | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `runs/real-backend-smoke/langfuse-trace-query-v2.json` | Passed through `itmux langfuse-trace --api legacy-trace`: trace returned with 7 observations. Observations v2 returns 404 on LangFuse v3 Docker Compose because it requires v4 write mode. |
| Trace UI link | `runs/real-backend-smoke/trace-ui-response.txt`, `runs/real-backend-smoke/trace-ui.html` | Passed: trace URL returned HTTP 200. |
| Native usage/cost/model fields | `runs/real-backend-smoke/summary.txt`, `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `/tmp/langfuse-playwright/dashboard-rich.har` | Passed: LangFuse classified `token_usage` as a `GENERATION`, set `model=gpt-4o-mini`, recorded 13 tokens, calculated `$0.000003299999`, and dashboard cost/model queries returned non-null values. |
| Live Codex exec export | `runs/codex-live-real-langfuse-model-resolved/summary.txt`, `runs/codex-live-real-langfuse-model-resolved/events.jsonl`, `runs/codex-live-real-langfuse-model-resolved/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose with the real Codex CLI: model `gpt-5.5`, harness `codex`, provider `openai`, 26450 total tokens, calculated cost `0.084525`, event/tool sequences ordered by `agentic.event.seq`, and `agent_tool` vs `harness_tool` grouping. |
| Agent-facing trace summary | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `/tmp/langfuse-playwright/trace-rich-summary.json`, `runs/claude-transcript-langfuse/langfuse-trace-query-learning-loop.json`, `runs/claude-transcript-langfuse/learning-loop-summary.txt`, `runs/codex-live-real-langfuse-model-resolved/langfuse-trace-query-legacy.json` | Passed: `itmux langfuse-trace --api legacy-trace --run-id ...` reports harness/provider/model/token/cost summary fields, a redacted tool-call summary, a compact full event sequence, and separate `operations`, `agent_tools`, and `harness_tools` groups for learning loops. |
| Claude transcript export | `runs/claude-transcript-langfuse/summary.txt`, `runs/claude-transcript-langfuse/events.jsonl`, `runs/claude-transcript-langfuse/result.json`, `runs/claude-transcript-langfuse/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose: Claude transcript tool use became spans, model usage became `GENERATION` observations, and the agent-facing summary reports harness `claude`, provider `anthropic`, both Claude model names, token totals, and calculated cost. |
| Live Claude `itmux run` export | `runs/claude-live-itmux-run/summary.txt`, `runs/claude-live-itmux-run/events.jsonl`, `runs/claude-live-itmux-run/result.json`, `runs/claude-live-itmux-run/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose: a real Claude workspace run exported hooks, transcript-derived tool spans, transcript-derived token usage, and LangFuse classified usage as `GENERATION` with model `claude-sonnet-4-6`, token totals, and calculated cost. |
| Live Claude poll-time streaming | `runs/claude-live-streaming-dedupe-itmux-run/summary.txt`, `runs/claude-live-streaming-dedupe-itmux-run/event-order.json`, `runs/claude-live-streaming-dedupe-itmux-run/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose: hook and transcript-derived token usage events streamed before `await` ended, message-level usage was deduplicated to one event, and LangFuse classified usage as `GENERATION` with model, token totals, and calculated cost. |
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

## Live Codex Exec Smoke

The local Docker Compose LangFuse backend accepted a real `codex exec --json`
run through `itmux codex-exec` after the CLI resolved the effective Codex
model from the user's Codex config for telemetry annotation.

Current key evidence from
`runs/codex-live-real-langfuse-model-resolved/summary.txt`:

- Run id: `run-40ceea48`
- Trace id: `edc4d1b77ac6b59a530c5a0014a0707b`
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
- Native total tokens: `26450`
- Calculated total cost: `0.084525`
- Harness values: `codex`
- Provider values: `openai`

The first live default-model run showed the exporter could reach LangFuse but
left LangFuse cost/model fields empty because Codex's JSON stream reports usage
without the model name. `itmux codex-exec` now annotates usage with an explicit
`--model` when supplied, else `CODEX_MODEL`, else top-level
`CODEX_HOME/config.toml` or `~/.codex/config.toml` `model`. This only annotates
telemetry; it does not change the model passed to Codex unless `--model` is
explicitly supplied.

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
