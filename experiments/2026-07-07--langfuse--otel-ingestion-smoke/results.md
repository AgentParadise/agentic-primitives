# Results

| Probe | Evidence | Result |
|---|---|---|
| Local synthetic trace | `runs/synthetic-trace-source.json`, `runs/local-trace-summary.json` | Generated one root span plus three child spans with required local attributes. |
| LangFuse OTLP export | `runs/real-backend-smoke/summary.txt`, `runs/real-backend-smoke/result.json`, `runs/real-backend-smoke/events.jsonl` | Passed against local LangFuse Docker Compose: exporter status `ok`, `events_exported=6`, trace link emitted. |
| Trace queryability | `runs/real-backend-smoke/langfuse-trace-query-legacy.json`, `runs/real-backend-smoke/langfuse-trace-query-v2.json` | Passed through `itmux langfuse-trace --api legacy-trace`: trace returned with 7 observations. Observations v2 returns 404 on LangFuse v3 Docker Compose because it requires v4 write mode. |
| Trace UI link | `runs/real-backend-smoke/trace-ui-response.txt`, `runs/real-backend-smoke/trace-ui.html` | Passed: trace URL returned HTTP 200. |
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

Key evidence from `runs/real-backend-smoke/summary.txt`:

- Run id: `run-223bc2a0`
- Trace id: `e8ec439f180e38c5bcb34c1baad4f978`
- Exporter status: `ok`
- Events exported: `6`
- Legacy trace-query exit: `0`
- Backend observation count: `7`
- Root span start time: `2026-07-07T23:50:27.000Z`
- Trace UI status: `200`

The root span timestamp is important empirical feedback from the real backend:
an earlier run showed the root span at Unix epoch. The exporter now timestamps
the root span from the first normalized run event.
