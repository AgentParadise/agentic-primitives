# Results

| Probe | Evidence | Result |
|---|---|---|
| Local synthetic trace | `runs/synthetic-trace-source.json`, `runs/local-trace-summary.json` | Generated one root span plus three child spans with required local attributes. |
| LangFuse OTLP export | `runs/real-backend-smoke/summary.txt`, `runs/real-backend-smoke/result.json`, `runs/real-backend-smoke/events.jsonl` | Passed against local LangFuse Docker Compose: exporter status `ok`, `events_exported=6`, trace link emitted. |
| Trace queryability | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `runs/real-backend-smoke/langfuse-trace-query-v2.json` | Passed through `itmux langfuse-trace --api legacy-trace`: trace returned with 7 observations. Observations v2 returns 404 on LangFuse v3 Docker Compose because it requires v4 write mode. |
| Trace UI link | `runs/real-backend-smoke/trace-ui-response.txt`, `runs/real-backend-smoke/trace-ui.html` | Passed: trace URL returned HTTP 200. |
| Native usage/cost/model fields | `runs/real-backend-smoke/summary.txt`, `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `/tmp/langfuse-playwright/dashboard-rich.har` | Passed: LangFuse classified `token_usage` as a `GENERATION`, set `model=gpt-4o-mini`, recorded 13 tokens, calculated `$0.000003299999`, and dashboard cost/model queries returned non-null values. |
| Agent-facing trace summary | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `/tmp/langfuse-playwright/trace-rich-summary.json` | Passed: `itmux langfuse-trace --api legacy-trace --run-id ...` reports harness/provider/model/token/cost summary fields for learning loops. |
| Claude transcript export | `runs/claude-transcript-langfuse/summary.txt`, `runs/claude-transcript-langfuse/events.jsonl`, `runs/claude-transcript-langfuse/result.json`, `runs/claude-transcript-langfuse/langfuse-trace-query-legacy.json` | Passed against local LangFuse Docker Compose: Claude transcript tool use became spans, model usage became `GENERATION` observations, and the agent-facing summary reports harness `claude`, provider `anthropic`, both Claude model names, token totals, and calculated cost. |
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

- Run id: `run-claude-fixture-rich`
- Trace id: `41eedb37a10d825b0522048e8ea119a0`
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
proves the reusable exporter contract for Claude-shaped transcript data; it does
not yet prove live transcript tailing from an interactive Claude workspace.
