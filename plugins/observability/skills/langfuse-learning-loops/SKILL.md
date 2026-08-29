---
name: langfuse-learning-loops
description: Query LangFuse traces and session cohorts, inspect costs and tool behavior, and write trace-scoped feedback through the packaged agentic-langfuse MCP server. Use for retrospectives, experiment analysis, evaluation handoffs, and learning-loop reports.
---

# LangFuse Learning Loops

Use LangFuse's project API through the packaged `agentic-langfuse` MCP server
or the `itmux langfuse-*` commands. This is the agent-facing data plane: it
uses `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, and
`LANGFUSE_SECRET_KEY` rather than a browser login.

## Required Client Contract

- Use the same central endpoint and project keys as the Claude/Codex tracing
  plugins.
- Preserve the trace identity contract: an `environment` per machine or
  workspace class plus `harness:<name>` and `host:<name>` tags.
- Keep API keys in Keychain, a host secret store, or runtime-only container
  environment. Never place them in a repository, image, or transcript.
- Use `uv run --script` for the MCP server. Do not invoke it with `python3`.

## Query Before You Judge

Start with a bounded cohort, then drill down:

1. Discover recent traces by harness and environment.
2. Inspect trace summaries for model, cost, token, tool, error, and score
   signals.
3. Use the session index to discover sessions by harness, host, environment,
   project, cost, and score coverage; then drill into the relevant session.
4. Write a trace-scoped score only when the criterion and evidence are clear.
5. Record the trace/session IDs in the experiment or retrospective artifact.

The `agentic-langfuse` MCP server provides:

- `agentic_langfuse_trace_discovery`
- `agentic_langfuse_trace_summary`
- `agentic_langfuse_session_report`
- `agentic_langfuse_session_index`
- `agentic_langfuse_scores`
- `agentic_langfuse_score_feedback`
- `agentic_langfuse_learning_loop_report`

The equivalent CLI path is:

```bash
itmux langfuse-traces --limit 20 --output summary
itmux langfuse-traces --harness codex --environment flywheel-vps
itmux langfuse-trace --trace-id <trace-id> --include-scores --output summary
itmux langfuse-sessions --harness claude --environment local-macbook
itmux langfuse-score --trace-id <trace-id> --name learning-loop-quality --value 1
```

## Dashboard Boundary

Do not block a learning loop on a LangFuse browser session. The project API
and MCP are sufficient to query traces, sessions, prompts, datasets, and
scores programmatically.

LangFuse v3.212 exposes an unstable public API for creating *reusable
dashboard widgets*. That API does **not** place widgets on a dashboard grid,
and it supports only observation/scores views, not absolute trace or session
counts. It therefore cannot faithfully create a dashboard requiring:

- absolute total traces;
- absolute total sessions; or
- a harness-by-host matrix from separate tags.

Create and place those widgets in the LangFuse UI, or build an external
metrics view from the public API. Do not scrape or transfer browser cookies.
Use the public API/MCP for automated learning-loop analysis and evaluation
work; use the dashboard UI for human-operated visual composition.

## Interpretation Rules

- A LangFuse session groups per-turn traces. It is not the raw transcript or
  replay store.
- The native Sessions UI is intentionally sparse. Use
  `agentic_langfuse_session_index` for the operational view of which harness
  and host produced a session; it derives those dimensions from canonical
  trace tags and metadata without changing native session IDs.
- Session-index rollups are bounded to the requested trace page. Use a narrow
  cohort for discovery, then inspect the session's trace links before treating
  a rollup as a complete historical session total.
- When filtering by harness, environment, provider, or model, the index
  scans up to five bounded 100-trace candidate pages before applying the
  requested result cap. Increase `scan_pages` (maximum 20) or page through
  older cohorts when the desired harness is absent.
- Missing cost can mean a missing model definition or unfinalized model rate,
  not missing trace telemetry.
- Compare like with like: filter on environment and harness before comparing
  models, recipes, or time periods.
- Prefer stable, evidence-backed score names such as `learning-loop-quality`
  over ad hoc comments with no criterion.
